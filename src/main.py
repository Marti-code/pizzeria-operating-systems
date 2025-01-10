#!/usr/bin/env python3
import os
import time
import random
import signal
import traceback
from multiprocessing import Process, Queue, Event

# Sygnał dla alarmu pożarowego
FIRE_SIGNAL = signal.SIGUSR1 if hasattr(signal, 'SIGUSR1') else signal.SIGINT
SHUTDOWN_SIGNAL = signal.SIGINT

TABLE_COUNTS = {
    1: 2,  # X1
    2: 2,  # X2
    3: 2,  # X3
    4: 2   # X4
}

NUM_CUSTOMERS = 5
MAX_GROUP_SIZE = 3
SIMULATION_DURATION = 30 # na razie symulacja trwa 30 sekund dla testu
FIRE_RANDOM_DELAY = (5, 15)  # Alarm pożarowy losowo co 5-15 sekund


def manager_process(queue: Queue, close_event: Event):
    tables = {size: [{'table_id': i, 'capacity': size, 'used_seats': 0, 'group_size': None} for i in range(2)] for size in TABLE_COUNTS}
    total_profit = 0

    def seat_customer_group(group_size):
        for size, table_list in tables.items():
            if size >= group_size:
                for table in table_list:
                    if table['group_size'] in (None, group_size) and table['capacity'] - table['used_seats'] >= group_size:
                        table['used_seats'] += group_size
                        table['group_size'] = group_size
                        return table['table_id']
        return None
    
    def handle_signal(signum, frame):
        if signum == FIRE_SIGNAL:
            print(f"[Manager] Otrzymałem sygnał pożaru! Ewakuacja pizzerii!")
            fire_event.set()

    signal.signal(FIRE_SIGNAL, handle_signal)

    print("[Manager] Proces rozpoczęty.")
    
    while not close_event.is_set():
        time.sleep(0.1)
        if not queue.empty():
            msg_type, data = queue.get_nowait()
            if msg_type == "REQUEST_SEAT":
                group_size, customer_id = data
                if fire_event.is_set():
                    print(f"[Manager] Pożar! Klient {customer_id} musi opuścić lokal.")
                    queue.put(("LEAVE", customer_id))
                    continue


                table_id = seat_customer_group(group_size)
                if table_id is not None:
                    total_profit += group_size * 10
                    print(f"[Manager] Klient {customer_id} zajął miejsce (grupa {group_size}). Stolik {table_id}.")
                    queue.put(("SEATED", customer_id))
                else:
                    print(f"[Manager] Brak miejsca dla grupy {customer_id} ({group_size} osób).")
                    queue.put(("REJECTED", customer_id))
            elif msg_type == "CUSTOMER_DONE":
                group_size, customer_id, table_id = data
                print(f"[Manager] Klient {customer_id} wychodzi (grupa {group_size}). Zwolniono stolik {table_id}.")
                for size in tables.values():
                    for table in size:
                        if table['table_id'] == table_id:
                            table['used_seats'] -= group_size
                            if table['used_seats'] == 0:
                                table['group_size'] = None
    print(f"[Manager] Pizzeria zamknięta. Profit: {total_profit}")


def customer_process(queue: Queue, close_event: Event, group_size: int, customer_id: int):
    print(f"[Customer-{customer_id}] Grupa {group_size} prosi o stolik.")
    queue.put(("REQUEST_SEAT", (group_size, customer_id)))
    while not close_event.is_set():
        time.sleep(0.1)
        if fire_event.is_set():
            print(f"[Customer-{customer_id}] Pożar! Klient ucieka.")
            return
        
        if not queue.empty():
            msg_type, data = queue.get_nowait()
            if msg_type == "SEATED" and data == customer_id:
                print(f"[Customer-{customer_id}] Jedzenie pizzy...")
                time.sleep(1)
                print(f"[Customer-{customer_id}] Pizza zjedzona. Klient wychodzi.")
                queue.put(("CUSTOMER_DONE", (group_size, customer_id, 9999)))  # na razie takie, manager wie jakie stoliki są zajęte
                return
            elif msg_type == "REJECTED" and data == customer_id:
                print(f"[Customer-{customer_id}] Brak miejsc. Klient wychodzi.")
                return

def firefighter_process(fire_event: Event):
    delay = random.randint(*FIRE_RANDOM_DELAY)
    print(f"[Firefighter] Pożar za {delay} sekund...")
    time.sleep(delay)

    print("[Firefighter] Alarm pożarowy! Wysyłanie sygnału do menedżera.")
    os.kill(os.getppid(), FIRE_SIGNAL)


def main():
    queue = Queue()
    close_event = Event()
    fire_event = Event()

    manager_proc = Process(target=manager_process, args=(queue, close_event))
    manager_proc.start()

    firefighter_proc = Process(target=firefighter_process, args=(fire_event,))
    firefighter_proc.start()

    customer_procs = [Process(target=customer_process, args=(queue, close_event, random.randint(1, MAX_GROUP_SIZE), i)) for i in range(NUM_CUSTOMERS)]
    for p in customer_procs:
        p.start()

    time.sleep(SIMULATION_DURATION)
    close_event.set()

    for p in customer_procs:
        p.join()
    manager_proc.join()
    print("[Main] Symulacja zakończona.")


if __name__ == "__main__":
    main()
