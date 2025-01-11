#!/usr/bin/env python3
import os
import sys
import time
import signal
import random
import traceback
from multiprocessing import Process, Queue, Event, Manager, current_process

FIRE_SIGNAL = signal.SIGUSR1 if hasattr(signal, 'SIGUSR1') else signal.SIGINT
SHUTDOWN_SIGNAL = signal.SIGINT

# Stoliki: X1, X2, X3, X4
TABLE_COUNTS = {
    1: 2,  # X1
    2: 2,  # X2
    3: 2,  # X3
    4: 2   # X4
}

NUM_CUSTOMERS = 5   # Liczba grup która się pojawi
MAX_GROUP_SIZE = 3  # Grupa min 1 osoba, max 3 osoby
SIMULATION_DURATION = 30  # testowo na razie symulacja będzie działać 30 sekund
FIRE_RANDOM_DELAY = (5, 15)  # Alarm pożarowy losowo co <5,15> sekund


###############################################################################
# (Manager/Cashier Process)
###############################################################################
def manager_process(queue: Queue, fire_event: Event, close_event: Event):
    tables = {}
    table_id_counter = 1

    for size, count in TABLE_COUNTS.items():
        # Inicjalizacja stołów
        tables[size] = []
        for _ in range(count):
            table_info = {
                'table_id': table_id_counter,
                'capacity': size,
                'used_seats': 0,       
                'group_size': None,    # jaka grupa używa stołu, by ewentualnie grupa o tej samej ilości osób mogła się dosiąść
            }
            tables[size].append(table_info)
            table_id_counter += 1

    total_profit = 0  # będziemy zliczać pieniążki

    # trzeba ustalić gdzie kto będzie siedział
    def seat_customer_group(group_size):
        # Szukamy najmniejszego stołu na początek
        for size in sorted(tables.keys()):
            if size >= group_size:
                # Ewentualnie sprawdzamy czy nie ma wolnego miejsca przy stole gdzie ktoś już siedzi
                for table in tables[size]:
                    if table['group_size'] in (None, group_size):
                        # No i oczywiście czy się zmieści ta grupa
                        if table['capacity'] - table['used_seats'] >= group_size:
                            # Jeśli wszystko się zgadza to zajmujemy miejsce
                            seats_before = table['used_seats']
                            table['used_seats'] += group_size
                            if table['group_size'] is None:
                                table['group_size'] = group_size
                            seats_after = table['used_seats']
                            return (table['table_id'], seats_before, seats_after)
        return None

    # Sygnały
    def handle_signal(signum, frame):
        if signum == FIRE_SIGNAL:
            print(f"[Manager] Otrzymałem sygnał pożaru. Ewakuacja pizzeri!")
            fire_event.set()
        elif signum == SHUTDOWN_SIGNAL:
            print(f"[Manager] Otrzymałem sygnał zakończenia symulacji. Zakańczanie symulacji.")
            close_event.set()

    signal.signal(FIRE_SIGNAL, handle_signal)
    signal.signal(SHUTDOWN_SIGNAL, handle_signal)

    print("[Manager] Proces rozpoczęty.")
    print("[Manager] Stoliki:", tables)

    try:
        while not close_event.is_set():
            time.sleep(0.1)

            while not queue.empty():
                try:
                    msg = queue.get_nowait()
                except:
                    continue

                # msg to tuple (msg_type, data)
                msg_type, data = msg

                if msg_type == "REQUEST_SEAT":
                    group_size, customer_id = data
                    if fire_event.is_set():
                        # Manager informuje klienktów by wyszli
                        print(f"[Manager] Jest pożar. Informowanie klienta {customer_id} by wyszedł.")
                        queue.put(("LEAVE", customer_id))
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
                                if table['used_seats'] == 0:
                                    table['group_size'] = None
                                break

                else:
                    print(f"[Manager] Nieznana wiadomość: {msg_type}, ignoruj.")
            
            # Jeśli jest alarm przeciwpożarowy włączony a wszyscy wyszli to zamykamy kasę
            if fire_event.is_set():
                time.sleep(1)
                close_event.set()

        # Na razie zamykamy i tyle, nie wznawiamy, testujemy czy to będzie działać
        print(f"[Manager] Pizzeria zamknięta. Całkowity profit = {total_profit}")
        print("[Manager] Manager - zakańczanie.")

    except Exception as e:
        print("[Manager] ERROR:", e)
        traceback.print_exc()
    finally:
        print("[Manager] Manager - proces się zakończył.")


###############################################################################
# (Customer/Group Process)
###############################################################################
def customer_process(queue: Queue, fire_event: Event, close_event: Event, group_size: int, customer_id: int):
    try:
        print(f"[Customer-{customer_id}] Klient (ilość osób={group_size}). Prośba o stolik.")
        queue.put(("REQUEST_SEAT", (group_size, customer_id)))

        table_id = None

        while not close_event.is_set():
            # Sprawdzamy czy nie ma pożaru przypadkiem
            if fire_event.is_set():
                print(f"[Customer-{customer_id}] Pożar! Klient ucieka.")
                return

            # Klienci będą ustawiać się w kolejeczkę
            time.sleep(0.1)

            while not queue.empty():
                msg_type, data = queue.get_nowait()
                
                if msg_type == "SEATED" and data == customer_id:
                    print(f"[Customer-{customer_id}] Miejsce znalezione. Delektuje się pizzą...")

                    table_id = 9999  # na razie takie, manager wie jakie stoliki są zajęte
                    time.sleep(1 + random.random())  

                    print(f"[Customer-{customer_id}] Pizza zjedzona. Klient wychodzi.")
                    if table_id is not None:
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
def firefighter_process(queue: Queue, fire_event: Event, close_event: Event):
    try:
        delay = random.randint(*FIRE_RANDOM_DELAY)
        print(f"[Firefighter] Pożar za {delay} sekund...")
        time.sleep(delay)
        
        # później można zmienić na sygnał wysyłany do managera, na razie będzię wysyłany taki systemowy, ogólny sygnał
        os.kill(os.getppid(), FIRE_SIGNAL)
        print("[Firefighter] Wysyłanie sygnału pożaru.")
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

    # Klienci - start
    customer_procs = []
    for i in range(NUM_CUSTOMERS):
        group_size = random.randint(1, MAX_GROUP_SIZE)
        p = Process(
            target=customer_process,
            args=(queue, fire_event, close_event, group_size, i),
            name=f"Customer-{i}"
        )
        p.start()
        customer_procs.append(p)

    # Strażak - start
    firefighter_proc = Process(
        target=firefighter_process,
        args=(queue, fire_event, close_event),
        name="FirefighterProcess"
    )
    firefighter_proc.start()

    start_time = time.time()

    # Rozpoczynamy symulacje
    while True:
        time.sleep(0.5)
        if close_event.is_set():
            break
        # Na razie jak minie 30 sekund to zakańczamy
        if (time.time() - start_time) > SIMULATION_DURATION:
            print("[Main] Koniec czasu.")
            os.kill(manager_proc.pid, SHUTDOWN_SIGNAL)
            break

    # Czekamy aż wszystkie procesy się zakończą
    firefighter_proc.join()
    for cp in customer_procs:
        cp.join()
    manager_proc.join()

    print("[Main] Symulacja zakończona pomyślnie.")


if __name__ == "__main__":
    main()