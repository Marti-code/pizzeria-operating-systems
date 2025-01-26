from multiprocessing import Value, Process, Queue, Event
import signal
from config import MAX_CONCURRENT_CUSTOMERS, SHUTDOWN_SIGNAL, FIRE_SIGNAL
from manager import manager_process
from firefighter import firefighter_process
from gui import gui_process
from customer import customer_process
import time
import traceback
import random
import os
from setproctitle import setproctitle

"""
Moduł main:
- tworzy kolejkę (Queue) do komunikacji
- uruchamia procesy: Manager, Firefighter, GUI
- w pętli tworzy procesy-Klientów (customer_process)
- nadzoruje liczbę aktywnych klientów (MAX_CONCURRENT_CUSTOMERS)
- reaguje na sygnał pożaru (fire_event) wstrzymując generowanie nowych klientów
- obsługuje zakończenie poprzez KeyboardInterrupt lub close_event
"""

def main():
    setproctitle("MainProcess")

    fire_event = Event()
    close_event = Event()

    is_running = Value('b', True) # do sprawdzania czy symulacja wciąż żyje

        # obsługa sygnału CTRL + C lub FIRE
    def handle_signal(signum, frame):
        if signum == SHUTDOWN_SIGNAL:
            print(f"[Main] Otrzymałem sygnał zakończenia symulacji. Zakańczanie symulacji.")
            is_running.value = False
        if signum == FIRE_SIGNAL:
            print(f"[Main] Otrzymałem sygnał pożaru.")

    signal.signal(SHUTDOWN_SIGNAL, handle_signal)
    signal.signal(FIRE_SIGNAL, handle_signal)


    gui_queue = Queue()
    
    start_time = time.time()

    # Manager - start
    manager_proc = Process(
        target=manager_process,
        args=(gui_queue, fire_event, close_event, start_time),
        name="ManagerProcess"
    )
    manager_proc.start()
    manager_pid = manager_proc.pid # będzie potrzebny by Firefighter mógł przesłać sygnał do Manager
    
    # Strażak - start
    firefighter_proc = Process(
        target=firefighter_process,
        args=(manager_pid, fire_event, close_event),
        name="FirefighterProcess"
    )
    firefighter_proc.start()

    # GUI - start
    gui_proc = Process(
        target=gui_process,
        args=(gui_queue, close_event),
        name="GUIProcess"
    )
    gui_proc.start()

    # Klienci - start
    customer_procs = []
    customer_id_counter = 0

    # Rozpoczynamy symulacje
    try:
        while is_running.value:
            # Wyczyść tych klientów którzy skończyli, by sprawdzać tylko ile jest aktywnych
            alive = []
            for cp in customer_procs:
                if cp.is_alive():
                    alive.append(cp)
                else:
                    cp.join()
            customer_procs = alive

            # wstrzymaj generowanie nowych klientów jeśli jest pożar
            # idź do następnej iteracji
            if fire_event.is_set():
                print("[Main] Jest pożar, nowi klienci nie są generowani.")
                while fire_event.is_set() and not close_event.is_set():
                    pass
                continue

            # limity bo CPU nie wydoli
            if len(customer_procs) >= MAX_CONCURRENT_CUSTOMERS:
                while len(customer_procs) >= MAX_CONCURRENT_CUSTOMERS and not close_event.is_set():
                    new_list = []
                    # tak długo jak ilosc klientów jest za duża próbkujemy ich stan i czekamy, aż ilość będzie ok
                    for cp in customer_procs:
                        if cp.is_alive():
                            new_list.append(cp)
                        else:
                            cp.join()
                    customer_procs = new_list

            print(f"[Main] Obecnie CustomerProcs={len(customer_procs)} aktywnych.", flush=True) # do testów

            group_size = random.choices([1, 2, 3], weights=[0.4, 0.4, 0.2])[0] # by częściej się pojawiały mniejsze grupy

            # generowanie klientów
            p = Process(
                target=customer_process,
                args=(fire_event, close_event, group_size, customer_id_counter),
                name=f"Customer-{customer_id_counter}"
            )
            p.start()
            customer_procs.append(p)
            customer_id_counter += 1


            # Nowy klient co 0.5..1 sekundy
            time.sleep(random.uniform(0.5, 1))

        # SHUTDOWN_SIGNAL zamyka pętle w MAIN
        # po wyjsciu z ustawiana jest flaga close_event dla pozostałych procesów
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
        print("[Main] Wszyscy klienci wykończeni...")

        if firefighter_proc.is_alive():
            firefighter_proc.join()
        print("[Main] Firefighter wykończony...")

        while not gui_queue.empty(): gui_queue.get()
        if manager_proc.is_alive():
            manager_proc.join()
        print("[Main] Manager wykończony...")
        
        gui_proc.join()
        print("[Main] Symulacja zakończona pomyślnie.")

if __name__ == "__main__":
    main()