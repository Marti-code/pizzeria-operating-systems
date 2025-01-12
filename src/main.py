#!/usr/bin/env python3
import os
import time
import signal
import random
import traceback
import queue as queue_module
from multiprocessing import Process, Queue, Event

FIRE_SIGNAL = signal.SIGUSR1 if hasattr(signal, 'SIGUSR1') else signal.SIGINT
SHUTDOWN_SIGNAL = signal.SIGINT

# Stoliki: X1, X2, X3, X4
TABLE_COUNTS = {
    1: 2,  # X1
    2: 2,  # X2
    3: 2,  # X3
    4: 2   # X4
}

# Grupa min 1 osoba, max 3 osoby
MIN_GROUP_SIZE = 1  
MAX_GROUP_SIZE = 3  
CLOSURE_DURATION_AFTER_FIRE = 10 # na ile sekund pizzeria się zamyka po pożarze


###############################################################################
# (Manager/Cashier Process)
###############################################################################
def manager_process(queue: Queue, fire_event: Event, close_event: Event):
    pizzeria_open = True
    total_profit = 0  # będziemy zliczać pieniążki

    def initialize_tables():
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
                            return table['table_id'], old_seats, table['used_seats']
        return None

    # Sygnały
    def handle_signal(signum, frame):
        nonlocal pizzeria_open
        if signum == FIRE_SIGNAL:
            print(f"[Manager] Otrzymałem sygnał pożaru. Ewakuacja pizzeri!")
            fire_event.set()
            pizzeria_open = False
        elif signum == SHUTDOWN_SIGNAL:
            print(f"[Manager] Otrzymałem sygnał zakończenia symulacji. Zakańczanie symulacji.")
            close_event.set()

    signal.signal(FIRE_SIGNAL, handle_signal)
    signal.signal(SHUTDOWN_SIGNAL, handle_signal)

    print("[Manager] Proces rozpoczęty.")
    print("[Manager] Stoliki:", tables)

    try:
        while not close_event.is_set():
            if fire_event.is_set():
                # Ewakuacja
                flush_requests(queue)
                print(f"[Manager] Pizzeria zamknięta na {CLOSURE_DURATION_AFTER_FIRE} sekund (pożar).")
                time.sleep(CLOSURE_DURATION_AFTER_FIRE)

                print("[Manager] Otwieranie pizzerii po pożarze.")
                pizzeria_open = True
                fire_event.clear()
                tables = initialize_tables()  # reset stolików możnaby zrobić
                print("[Manager] Reinicjalizacja stolików zakończona.")


            try:
                msg_type, data = queue.get(timeout=0.1)
            except queue_module.Empty:
                continue

            if msg_type == "REQUEST_SEAT":
                group_size, customer_id = data
                if not pizzeria_open:
                    # Manager informuje klienktów by wyszli
                    print(f"[Manager] Pizzeria zamknięta. Informowanie klienta {customer_id} by wyszedł.")
                    queue.put(("REJECTED", customer_id))
                    continue

                seat_result = seat_customer_group(group_size)
                if seat_result:
                    table_id, seats_before, seats_after = seat_result
                    
                    group_profit = group_size * 10 # na razie profit to rozmiar grupy * 10, może coś bardziej fancy wymyślę później
                    total_profit += group_profit
                    print(
                        f"[Manager] Klient {customer_id} zajął miejsce (ilość osób={group_size}) "
                        f"Stolik {table_id}, ilość miejsc zajętych przed:{seats_before} -> ilość miejsc zajętych teraz:{seats_after}. "
                        f"Profit+={group_profit}, Całkowity profit={total_profit}"
                    )
                    queue.put(("SEATED", customer_id))
                else:
                    print(
                        f"[Manager] Klient {customer_id} nie mógł usiąść (ilość osób={group_size}). Brak miejsca."
                    )
                    queue.put(("REJECTED", customer_id))

            elif msg_type == "CUSTOMER_DONE":
                # Grupa wychodzi, zwalniamy miejsca
                group_size, customer_id, table_id = data

                for size_arr in tables.values():
                    for table in size_arr:
                        if table['table_id'] == table_id:
                            print(
                                f"[Manager] Klient {customer_id} wychodzi. Zwolniło się {group_size} miejsca ze stolika {table_id}."
                            )
                            table['used_seats'] -= group_size
                            if table['used_seats'] < 0:
                                table['used_seats'] = 0
                            if table['used_seats'] == 0:
                                table['group_size'] = None
                            break

            else:
                print(f"[Manager] Nieznana wiadomość: {msg_type}, ignoruj.")
            

        # Na razie zamykamy i tyle, nie wznawiamy, testujemy czy to będzie działać
        print(f"[Manager] Pizzeria zamknięta. Całkowity profit = {total_profit}")
        print("[Manager] Manager - zakańczanie.")

    except Exception as e:
        print("[Manager] ERROR:", e)
        traceback.print_exc()
    finally:
        print("[Manager] Manager - proces się zakończył.")


def flush_requests(queue: Queue):
    while True:
        try:
            msg_type, data = queue.get_nowait()
        except queue_module.Empty:
            break
        if msg_type == "REQUEST_SEAT":
            _, customer_id = data
            # zmuszamy klientów do wyjścia
            queue.put(("LEAVE", customer_id))
        # jeśli "CUSTOMER_DONE", to ignorujemy no bo i tak wychodzą

###############################################################################
# (Customer/Group Process)
###############################################################################
def customer_process(queue: Queue, fire_event: Event, close_event: Event, group_size: int, customer_id: int):
    print(f"[Customer-{customer_id}] Klient (ilość osób={group_size}). Prośba o stolik.")
    queue.put(("REQUEST_SEAT", (group_size, customer_id)))

    table_id = None

    try:
        while not close_event.is_set():
            # Fire check
            if fire_event.is_set():
                print(f"[Customer-{customer_id}] Pożar! Klient ucieka.")
                return

            try:
                msg_type, data = queue.get(timeout=0.1)
            except queue_module.Empty:
                continue

            if data == customer_id:
                if msg_type == "SEATED":
                    table_id = random.randint(1000, 2000)# na razie takie, manager wie jakie stoliki są zajęte
                    print(f"[Customer-{customer_id}] Miejsce znalezione. Delektuje się pizzą...")
                    
                    time.sleep(random.uniform(1.0, 3.0))

                    print(f"[Customer-{customer_id}] Pizza zjedzona. Klient wychodzi.")
                    queue.put(("CUSTOMER_DONE", (group_size, customer_id, table_id)))
                    return
                
                elif msg_type == "REJECTED" and data == customer_id:
                    print(f"[Customer-{customer_id}] Brak miejsc. Klient wychodzi.")
                    return

                elif msg_type == "LEAVE" and data == customer_id:
                    print(f"[Customer-{customer_id}] Manager powiedział że jest pożar. Klient wychodzi.")
                    return

    except Exception as e:
        print(f"[Customer-{customer_id}] ERROR: {e}")
        traceback.print_exc()
    finally:
        print(f"[Customer-{customer_id}] Zakańczanie.")


###############################################################################
# (Firefighter Process)
###############################################################################
def firefighter_process(manager_pid: int, queue: Queue, fire_event: Event, close_event: Event):
    print("[Firefighter] Rozpoczynanie. Będzie wysyłać sygnały co 30 - 60 sekund.")
    try:
        while not close_event.is_set():
            delay = random.randint(30, 60)
            print(f"[Firefighter] Następny pożar za ~{delay} sekund...")
            time.sleep(delay)
            if close_event.is_set():
                break

            # Wysyłanie sygnału do manager
            try:
                os.kill(manager_pid, FIRE_SIGNAL)
                print("[Firefighter] Wysyłanie sygnału pożaru.")
            except ProcessLookupError:
                print("[Firefighter] Manager nie istnieje.")
                break
            except AttributeError:
                # Jak SIGUSR1 nie zadziała
                print("[Firefighter] Ustawianie fire_event.")
                fire_event.set()

    except Exception as e:
        print("[Firefighter] ERROR:", e)
        traceback.print_exc()
    finally:
        print("[Firefighter] Zakańczanie.")


###############################################################################
# main
###############################################################################
def main():
    queue = Queue()
    fire_event = Event()
    close_event = Event()

    # Manager - start
    manager_proc = Process(
        target=manager_process,
        args=(queue, fire_event, close_event),
        name="ManagerProcess"
    )
    manager_proc.start()
    manager_pid = manager_proc.pid # będzie potrzebny do Firefighter
    
    # Strażak - start
    firefighter_proc = Process(
        target=firefighter_process,
        args=(manager_pid, queue, fire_event, close_event),
        name="FirefighterProcess"
    )
    firefighter_proc.start()

    # Klienci - start
    customer_procs = []
    customer_id_counter = 0

    # Rozpoczynamy symulacje
    try:
        while True:
            if close_event.is_set():
                break

            group_size = random.randint(MIN_GROUP_SIZE, MAX_GROUP_SIZE)
            p = Process(
                target=customer_process,
                args=(queue, fire_event, close_event, group_size, customer_id_counter),
                name=f"Customer-{customer_id_counter}"
            )
            p.start()
            customer_procs.append(p)
            customer_id_counter += 1

            # Wyczyść tych klientów którzy skończyli
            alive = []
            for cp in customer_procs:
                if cp.is_alive():
                    alive.append(cp)
                else:
                    cp.join()
            customer_procs = alive

            # Nowy klient co 1..3 sekundy
            time.sleep(random.uniform(1.0, 3.0))

    except KeyboardInterrupt:
        print("\n[Main] Ctrl+C => zakańczanie.")
        close_event.set()
    except Exception as e:
        print("[Main] ERROR:", e)
        traceback.print_exc()
        close_event.set()
    finally:
        # Czekamy aż wszystkie procesy się zakończą
        print("[Main] Czekam na zakończenie wszystkich procesów...")
        for cp in customer_procs:
            cp.join()

        firefighter_proc.join()
        manager_proc.join()
        print("[Main] Symulacja zakończona pomyślnie.")

if __name__ == "__main__":
    main()