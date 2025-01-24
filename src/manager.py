from config import TABLE_COUNTS, FIRE_SIGNAL, SHUTDOWN_SIGNAL, CLOSURE_DURATION_AFTER_FIRE, SERVER_FIFO
from utils import flush_requests
import signal
import time
import traceback
from multiprocessing import Queue, Event
import queue as queue_module
import random
from setproctitle import setproctitle
import os
import sys

"""
Moduł manager: główny proces zarządzający pizzerią.

Odpowiedzialności:
1. Obsługa żądań o stolik ("REQUEST_SEAT") od klientów (customer_process)
2. Ustalanie, czy pizzeria jest otwarta (pizzeria_open) lub zamknięta (podczas pożaru)
3. Selekcja i przydzielanie miejsc przy stolikach (seat_customer_group)
4. Reagowanie na zakończenie jedzenia klientów ("CUSTOMER_DONE") – zwalnianie miejsc
5. Ewentualna ewakuacja przy pożarze (fire_event) na określony czas (CLOSURE_DURATION_AFTER_FIRE)
6. Aktualizacja informacji w GUI (gui_queue) – np. PROFI_UPDATE, TABLE_UPDATE, TABLE_FIRE
7. Przy zakończeniu (close_event) lub sygnale SHUTDOWN_SIGNAL, loguje statystyki do pliku (pizzeria_log.txt) i kończy działanie
"""

def manager_process(gui_queue: Queue, fire_event: Event, close_event: Event, start_time: float):
    setproctitle("ManagerProcess")
    pizzeria_open = True
    total_profit = 0  # będziemy zliczać pieniążki

    # dane do statystyk
    group_accepted = {1: 0, 2: 0, 3: 0} # liczba przyjętych grup danego rozmiaru
    group_rejected = {1: 0, 2: 0, 3: 0} # liczba odrzuconych grup (z powodu braku miejsc, nie pożaru)
    table_usage = {1: 0, 2: 0, 3: 0, 4: 0} # ile razy stolik danej pojemności został wykorzystany

    def initialize_tables():
        """
        Tworzy słownik 'tables' na podstawie TABLE_COUNTS.
        Struktura: tables[size] -> lista obiektów-stolików, np.:
        { 1: [ {table_id:1, capacity:1, used_seats:0, group_size:None}, {table_id:2,...} ], ... }
        """

        tables = {}
        table_id_counter = 1
        for size, count in TABLE_COUNTS.items():
            tables[size] = []
            for _ in range(count):
                tables[size].append({
                    'table_id': table_id_counter,
                    'capacity': size,
                    'used_seats': 0,
                    'group_size': None, # jaka grupa używa stołu, by ewentualnie grupa o tej samej ilości osób mogła się dosiąść
                })
                table_id_counter += 1
        return tables

    tables = initialize_tables()

    # trzeba ustalić gdzie kto będzie siedział
    def seat_customer_group(group_size):
        # Szukamy najmniejszego stołu na początek
        for size in sorted(tables.keys()):
            if size >= group_size:
                # Ewentualnie sprawdzamy czy nie ma wolnego miejsca przy stole gdzie ktoś już siedzi
                for table in tables[size]:
                    # No i oczywiście czy się zmieści ta grupa
                    if table['group_size'] in (None, group_size):
                        free = table['capacity'] - table['used_seats']
                        if free >= group_size:
                            # Jeśli wszystko się zgadza to zajmujemy miejsce
                            old_seats = table['used_seats']
                            table['used_seats'] += group_size
                            if table['group_size'] is None:
                                table['group_size'] = group_size
                            # Zwraca obiekt 'table' (dict) jeśli się uda, None w przeciwnym wypadku
                            return table
        return None

    # Sygnały
    def handle_signal(signum, frame):
        """
        Obsługa sygnałów przychodzących do procesu Manager.
        - FIRE_SIGNAL: pożar => ustawia fire_event i pizzeria_open=False,
        - SHUTDOWN_SIGNAL: zakończenie => ustawia close_event.
        """

        nonlocal pizzeria_open
        if signum == FIRE_SIGNAL:
            print(f"[Manager] Otrzymałem sygnał pożaru. Ewakuacja pizzeri!")
            fire_event.set()
            pizzeria_open = False
        elif signum == SHUTDOWN_SIGNAL:
            print(f"[Manager] Otrzymałem sygnał zakończenia symulacji. Zakańczanie symulacji.")
            close_event.set()

    # Przypisujemy funkcje do obsługi sygnałów
    signal.signal(FIRE_SIGNAL, handle_signal)
    signal.signal(SHUTDOWN_SIGNAL, handle_signal)

    print("[Manager] Proces rozpoczęty.")
    print("[Manager] Stoliki:", tables)

    try:
        os.mkfifo(SERVER_FIFO)
    except FileExistsError:
        pass
    
    try:
        while not close_event.is_set():
            if fire_event.is_set():
                # Ewakuacja
                print(f"[Manager] Pizzeria zamknięta na {CLOSURE_DURATION_AFTER_FIRE} sekund (pożar).")

                # Powiadamiamy GUI, że stoliki mają być 'czarne' (TABLE_FIRE)
                for size_list in tables.values():
                    for t in size_list:
                        gui_queue.put(("TABLE_FIRE", t['table_id']))

                # Zamykamy pizzerię na ustalony czas
                time.sleep(CLOSURE_DURATION_AFTER_FIRE)

                # Ponowne otwarcie po pożarze
                print("[Manager] Otwieranie pizzerii po pożarze.", flush=True)
                pizzeria_open = True
                fire_event.clear()
                tables = initialize_tables()
                
                # Wysyłamy do GUI aktualizacje na zielono (0 seats)
                for size_list in tables.values():
                    for t in size_list:
                        gui_queue.put(("TABLE_UPDATE", (t['table_id'], 0, t['capacity'])))
                
                print("[Manager] Reinicjalizacja stolików zakończona.")

            # Próbujemy odebrać wiadomość od klientów z kolejki
            try:
                with open(SERVER_FIFO, "r") as f:
                    while True:
                        line = f.readline()
                        if not line:
                            break

                        line = line.strip()
                        if not line:
                            continue

                        # Format: "client_fifo_name:REQUEST_SEAT group_size customer_id"
                        #    lub: "client_fifo_name:CUSTOMER_DONE group_size table_id"
                        try:
                            fifo_part, message_part = line.split(":", 1)
                        except ValueError:
                            print("[Manager] Ignorowanie wiadomości w złym formacie:", line)
                            continue

                        client_fifo = fifo_part.strip()
                        msg_tokens = message_part.strip().split()
                        if len(msg_tokens) < 3:
                            print("[Manager] Ignorowanie niepełnej wiadomości:", msg_tokens)
                            continue
                        msg_type = msg_tokens[0]
                        group_size = int(msg_tokens[1])
                        customer_id = msg_tokens[2]

                        if msg_type == "REQUEST_SEAT":
                            if not pizzeria_open:
                                print(f"[Manager] Pizzeria zamknięta. Informowanie klienta {customer_id} by wyszedł.")
                                with open(client_fifo, "w") as cf:
                                    cf.write(f"REJECTED {group_size} {customer_id}\n")
                                continue
                            tbl = seat_customer_group(group_size)

                            if tbl:
                                table_id = tbl['table_id']
                                # Udało się usiąść => SEATED     
                                group_profit = group_size * random.randint(10,25)
                                total_profit += group_profit

                                # Informacja do GUI o wzroście zysku
                                gui_queue.put(("PROFIT_UPDATE", total_profit))

                                # Statystyki do pliku
                                if group_size in group_accepted:
                                    group_accepted[group_size] += 1

                                table_usage[tbl['capacity']] += 1

                                print(
                                    f"[Manager] Klient {customer_id} zajął miejsce (ilość osób={group_size}) przy stoliku {table_id} "
                                    f"Profit+={group_profit}, Całkowity profit={total_profit}", flush=True
                                )

                                # update GUI o ilości osób przy stoliku
                                gui_queue.put(("TABLE_UPDATE", (table_id, tbl['used_seats'], tbl['capacity'])))

                                with open(client_fifo, "w") as cf:
                                    cf.write(f"SEATED {group_size} {table_id}\n")
                            else:
                                print(
                                    f"[Manager] Klient {customer_id} nie mógł usiąść (ilość osób={group_size}). Brak miejsca.", flush=True
                                )

                                # Statystyki do pliku
                                if group_size in group_rejected:
                                    group_rejected[group_size] += 1

                                with open(client_fifo, "w") as cf:
                                    cf.write(f"REJECTED {group_size} {customer_id}\n")

                        elif msg_type == "CUSTOMER_DONE":
                            # Szukamy "tego" stolika w 'tables'
                            for size_arr in tables.values():
                                for table in size_arr:
                                    if table['table_id'] == table_id:
                                        print(
                                            f"[Manager] Zwolniło się {group_size} miejsca ze stolika {table_id}.", flush=True
                                        )
                                        # Aktualizujemy liczbę zajętych miejsc
                                        table['used_seats'] -= group_size
                                        if table['used_seats'] < 0:
                                            table['used_seats'] = 0
                                        # Jeśli stolik jest całkowicie pusty, resetujemy group_size
                                        if table['used_seats'] == 0:
                                            table['group_size'] = None
                                        
                                        # update GUI
                                        gui_queue.put(("TABLE_UPDATE", (table['table_id'], table['used_seats'], table['capacity'])))
                                        
                                        break

                        else:
                            print("[Manager] Nieznana wiadomość msg_type:", msg_type)
            except queue_module.Empty:
                continue
            except InterruptedError:
                print("[Manager] Proces przerwany => Zakańczanie...")
                break
            except KeyboardInterrupt:
                print("[Manager] KeyboardInterrupt => Zakańczanie...")
                break

        # Koniec pętli – zamykamy pizzerię
        try:
            os.remove(SERVER_FIFO)
        except:
            pass
        print(f"[Manager] Pizzeria zamknięta. Całkowity profit = {total_profit}")
        print("[Manager] Manager - zakańczanie.")

    except Exception as e:
        print("[Manager] ERROR:", e)
        traceback.print_exc()
    finally:
        # Na końcu zapisujemy statystyki do pliku
        try:
            with open("pizzeria_log.txt", "a", encoding="utf-8") as f:
                end_time = time.time()
                simu_sec_count = end_time - start_time

                f.write(f"\n=== Symulacja rozpoczęta o: {time.ctime(start_time)} ===\n")
                f.write(f"=== Pizzeria zamknięta o {time.ctime(end_time)} ===\n")
                f.write(f"=== Symulacja trwała: {simu_sec_count:.2f} sekund ===\n")

                f.write("Całkowity profit: {}\n".format(total_profit))

                f.write("\n--- Statystyki grup klientów ---\n")
                for gsize in sorted(group_accepted.keys()):
                    acc = group_accepted[gsize]
                    rej = group_rejected[gsize]
                    f.write(f"  Grupa rozmiaru {gsize}: przyjęta={acc}, odrzucona={rej}\n")

                f.write("\n--- Statystyki stolików ---\n")
                for tsize in sorted(table_usage.keys()):
                    usage_count = table_usage[tsize]
                    f.write(f"  Stolik rozmiaru {tsize}: {usage_count} razy zajęty\n")

                f.write("=======================================\n\n")
        except Exception as file_err:
            print("[Manager] Błąd zapisu do pizzeria_log.txt:", file_err)

        print("[Manager] Manager - proces się zakończył.")

