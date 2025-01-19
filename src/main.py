import os
import time
import signal
import random
import traceback
import queue as queue_module
from multiprocessing import Process, Queue, Event
import threading
import tkinter as tk # ty się dobrze zastanów czy ty chcesz to zrobić

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

MAX_CONCURRENT_CUSTOMERS = 20 # nie mam dinero na nowego kompa więc trzeba sobie jakoś radzić

###############################################################################
# GUI Process
###############################################################################
def gui_process(gui_queue: Queue, close_event: Event):
    all_tables = []
    table_id_counter = 1
    for size, count in TABLE_COUNTS.items():
        for _ in range(count):
            all_tables.append({
                'table_id': table_id_counter,
                'capacity': size,
                'used_seats': 0,
            })
            table_id_counter += 1

    root = tk.Tk()
    root.title("Pizzeria Wizualizacja")

    root.configure(bg="#0a0a2b") # NAVY bg yess sir

    # Zielony tekst na total_profit
    profit_label = tk.Label(root, text="Total Profit: 0", fg="green", bg="#0a0a2b", font=("Arial", 14, "bold"))
    profit_label.pack(pady=10)

    canvas = tk.Canvas(root, width=380, height=300, bg="#0a0a2b", highlightthickness=0)
    canvas.pack()

    # table_id -> (circle_id, text_id)
    circle_map = {}

    # Koła będą w gridzie
    spacing_x = 90
    spacing_y = 90
    start_x = 60
    start_y = 60
    per_row = 4 

    def color_for_table(used, cap):
        if used == 0:
            return "green" # wolne
        elif used >= cap:
            return "red" # zajęte
        else:
            return "orange" # częściowo zajęte

    # Stoły reprezentowane przez koła
    for i, tbl in enumerate(all_tables):
        row = i // per_row
        col = i % per_row
        x = start_x + col * spacing_x
        y = start_y + row * spacing_y
        r = 30 

        c_id = canvas.create_oval(x-r, y-r, x+r, y+r, fill="green", outline="#0a0a2b")
        t_id = canvas.create_text(x, y, text=f"ID:{tbl['table_id']}\n0/{tbl['capacity']}", fill="white", font=("Arial", 10, "bold"))

        circle_map[tbl['table_id']] = (c_id, t_id)

    # Na razie sprawdzamy qui_queue co 100ms
    def poll_queue():
        while True:
            try:
                msg_type, data = gui_queue.get_nowait()
            except queue_module.Empty:
                break

            if msg_type == "TABLE_UPDATE":
                table_id, used_seats, capacity = data
                # Aktualizujemy kolor i liczbe w kole
                if table_id in circle_map:
                    c_id, t_id = circle_map[table_id]
                    fill_color = color_for_table(used_seats, capacity)
                    canvas.itemconfig(c_id, fill=fill_color)
                    canvas.itemconfig(t_id, text=f"ID:{table_id}\n{used_seats}/{capacity}")
            elif msg_type == "PROFIT_UPDATE":
                # data = total_profit
                profit_label["text"] = f"Profit: {data}"
            elif msg_type == "TABLE_FIRE":
                table_id = data
                if table_id in circle_map:
                    c_id, t_id = circle_map[table_id]
                    canvas.itemconfig(c_id, fill="black")
                    canvas.itemconfig(t_id, text=f"ID:{table_id}\nPOŻAR")
                
        if not close_event.is_set():
            root.after(100, poll_queue)
        else:
            # Jak close_event no to zamykamy
            root.destroy()

    # start polling
    root.after(100, poll_queue)

    root.mainloop()

###############################################################################
# (Manager/Cashier Process)
###############################################################################
def manager_process(queue: Queue, gui_queue: Queue, fire_event: Event, close_event: Event, start_time: float):
    pizzeria_open = True
    total_profit = 0  # będziemy zliczać pieniążki

    # dane do statystyk
    group_accepted = {1: 0, 2: 0, 3: 0}
    group_rejected = {1: 0, 2: 0, 3: 0} # tylko ci co nie mieli miejsca (pożar się nie liczy)
    table_usage = {1: 0, 2: 0, 3: 0, 4: 0}

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
                            return table
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

                for size_list in tables.values():
                    for t in size_list:
                        gui_queue.put(("TABLE_FIRE", t['table_id']))

                time.sleep(CLOSURE_DURATION_AFTER_FIRE)

                print("[Manager] Otwieranie pizzerii po pożarze.")
                pizzeria_open = True
                fire_event.clear()
                tables = initialize_tables()
                
                # jak reinicjalizacja stolików to i update gui
                for size_list in tables.values():
                    for t in size_list:
                        gui_queue.put(("TABLE_UPDATE", (t['table_id'], 0, t['capacity'])))
                
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

                tbl = seat_customer_group(group_size) # jak None to reject, jak nie to udało się usiąść
                if tbl:                    
                    group_profit = group_size * random.randint(10,25) # bardzo fancy żeś wymyśliła nie ma co
                    total_profit += group_profit

                    # update GUI    
                    gui_queue.put(("PROFIT_UPDATE", total_profit))

                    if group_size in group_accepted:
                        group_accepted[group_size] += 1

                    table_usage[tbl['capacity']] += 1

                    print(
                        f"[Manager] Klient {customer_id} zajął miejsce (ilość osób={group_size}) przy stoliku {tbl['table_id']} "
                        f"Profit+={group_profit}, Całkowity profit={total_profit}"
                    )

                    # update GUI
                    gui_queue.put(("TABLE_UPDATE", (tbl['table_id'], tbl['used_seats'], tbl['capacity'])))

                    queue.put(("SEATED", (customer_id, tbl['table_id'])))  
                else:
                    print(
                        f"[Manager] Klient {customer_id} nie mógł usiąść (ilość osób={group_size}). Brak miejsca."
                    )

                    if group_size in group_rejected:
                        group_rejected[group_size] += 1

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

                            # update GUI
                            gui_queue.put(("TABLE_UPDATE", (table['table_id'], table['used_seats'], table['capacity'])))
                            
                            break

        print(f"[Manager] Pizzeria zamknięta. Całkowity profit = {total_profit}")
        print("[Manager] Manager - zakańczanie.")

    except Exception as e:
        print("[Manager] ERROR:", e)
        traceback.print_exc()
    finally:
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
def person_in_group(thread_id: int, customer_id: int):
    print(f"    [Customer-{customer_id} thread-{thread_id}] Jem...")
    time.sleep(3)

def customer_process(queue: Queue, fire_event: Event, close_event: Event, group_size: int, customer_id: int):
    print(f"[Customer-{customer_id}] Klient (ilość osób={group_size}). Prośba o stolik.")
    queue.put(("REQUEST_SEAT", (group_size, customer_id)))

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

            if msg_type == "SEATED":
                c_id, real_table_id = data
                if c_id == customer_id:
                    table_id = real_table_id
                    print(f"[Customer-{customer_id}] Miejsce znalezione. Delektuje się pizzą...")
                    
                    # Każdy proces (grupa) ma wątki (osoby)
                    threads = []
                    for person_i in range(1, group_size + 1):
                        t = threading.Thread(target=person_in_group, args=(person_i,customer_id))
                        t.start()
                        threads.append(t)

                    # Czekamy aż wszyscy z grupy zjedzą
                    for t in threads:
                        t.join()

                    # time.sleep(random.uniform(1.0, 3.0))

                    print(f"[Customer-{customer_id}] Pizza zjedzona. Klient wychodzi.")
                    queue.put(("CUSTOMER_DONE", (group_size, customer_id, table_id)))

                    return

            if msg_type == "REJECTED":
                c_id = data
                if c_id == customer_id:
                    print(f"[Customer-{customer_id}] Brak miejsc. Klient wychodzi.")
                    return
            elif msg_type == "LEAVE":
                c_id = data
                if c_id == customer_id:
                    print(f"[Customer-{customer_id}] Manager powiedział że jest pożar. Klient wychodzi.")
                    return

    except KeyboardInterrupt:
        print(f"[Customer-{customer_id}] KeyboardInterrupt => zakańczanie.")
    except Exception as e:
        print(f"[Customer-{customer_id}] ERROR: {e}")
        traceback.print_exc()
    finally:
        print(f"[Customer-{customer_id}] Zakańczanie.")


###############################################################################
# (Firefighter Process)
###############################################################################
def firefighter_process(manager_pid: int, queue: Queue, fire_event: Event, close_event: Event):
    print("[Firefighter] Rozpoczynanie. Będzie wysyłać sygnały co 15 - 30 sekund.")
    try:
        while not close_event.is_set():
            delay = random.randint(30, 45)
            print(f"[Firefighter] Następny pożar za ~{delay} sekund...")
            time.sleep(delay)
            if close_event.is_set():
                break

            # Wysyłanie sygnału do manager
            try:
                # os.kill(manager_pid, FIRE_SIGNAL) # na windows nie zadziała bo ACCESS DENIED
                fire_event.set()
                print("[Firefighter] Wysyłanie sygnału pożaru.")
            except ProcessLookupError:
                print("[Firefighter] Manager nie istnieje.")
                break
            except AttributeError:
                # Jak SIGUSR1 nie zadziała
                print("[Firefighter] Ustawianie fire_event.")
                fire_event.set()

    except KeyboardInterrupt:
        print("[Firefighter] KeyboardInterrupt => zakańczanie.")
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

    gui_queue = Queue()
    
    start_time = time.time()

    # Manager - start
    manager_proc = Process(
        target=manager_process,
        args=(queue, gui_queue, fire_event, close_event, start_time),
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
        while not close_event.is_set():
            # Wyczyść tych klientów którzy skończyli, by sprawdzać tylko ile jest aktywnych
            alive = []
            for cp in customer_procs:
                if cp.is_alive():
                    alive.append(cp)
                else:
                    cp.join()
            customer_procs = alive

            if fire_event.is_set():
                print("[Main] Jest pożar, nowi klienci nie są generowani.")
                while fire_event.is_set() and not close_event.is_set():
                    time.sleep(0.1)
                continue

            # limity bo CPU nie wydoli
            if len(customer_procs) >= MAX_CONCURRENT_CUSTOMERS:
                while len(customer_procs) >= MAX_CONCURRENT_CUSTOMERS and not close_event.is_set():
                    new_list = []
                    for cp in customer_procs:
                        if cp.is_alive():
                            new_list.append(cp)
                        else:
                            cp.join()
                    customer_procs = new_list
                    time.sleep(0.05)

            group_size = random.choices([1, 2, 3], weights=[0.4, 0.4, 0.2])[0] # by częściej się pojawiały mniejsze grupy

            p = Process(
                target=customer_process,
                args=(queue, fire_event, close_event, group_size, customer_id_counter),
                name=f"Customer-{customer_id_counter}"
            )
            p.start()
            customer_procs.append(p)
            customer_id_counter += 1

            # Nowy klient co 0.5..1 sekundy
            time.sleep(random.uniform(0.5, 1.0))

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
        gui_proc.join()
        print("[Main] Symulacja zakończona pomyślnie.")

if __name__ == "__main__":
    main()