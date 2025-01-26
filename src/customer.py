import time
import threading
from config import SERVER_FIFO, CUSTOMER_FIFO_DIR, MAX_EAT_TIME
import traceback
from multiprocessing import Event
from setproctitle import setproctitle
import os

"""
Moduł customer: 
- person_in_group() – funkcja wątku symulującego jedną osobę przy stole
- customer_process() – główna funkcja procesu klienta, który komunikuje się z Managerem przez kolejkę i reaguje na event pożaru
"""


def person_in_group(thread_id: int, customer_id: int, close_event: Event, fire_event: Event):
    print(f"    [Customer-{customer_id} thread-{thread_id}] Jem...")
    ctime = time.time()

    while True:
        if close_event.is_set() or fire_event.is_set():
            # w czasie jedzenia polecial event, ktory zmusza do wyjscia
            return
        if time.time() - ctime > MAX_EAT_TIME:
            # delay minął
            return

def customer_process( fire_event: Event, close_event: Event, group_size: int, customer_id: int):
    
    """
    1. Wysyła ("REQUEST_SEAT", (group_size, customer_id)) do managera, by poprosić o stolik
    2. Czeka na "SEATED", "LEAVE" lub "REJECTED" z kolejki
    3. Jeśli "SEATED", tworzy wątki (person_in_group) dla każdej osoby w grupie
       Każdy wątek 'je' (sleep). Następnie wysyła ("CUSTOMER_DONE", ...) do managera
    4. Jeśli "REJECTED", kończy proces a klient 'wychodzi'
    5. Jeśli "LEAVE" (pożar) lub fire_event.is_set() – klient 'ucieka'
    """
    
    setproctitle(f"CustomerProcess-{customer_id}-pid({os.getpid()})")
    
    my_fifo = CUSTOMER_FIFO_DIR + f"Customer_fifo_{customer_id}"
    if not os.path.exists(my_fifo):
        os.remove(my_fifo)
    os.mkfifo(my_fifo)

    req_line = f"{my_fifo}:REQUEST_SEAT {group_size} {customer_id}\n"
    write_to_server_fifo(req_line)

    print(f"[Customer-{customer_id}] Klient (ilość osób={group_size}). Prośba o stolik.")

    mf = os.open(my_fifo, os.O_RDONLY | os.O_NONBLOCK)
    mff = os.fdopen(mf, "r")

    try:
        while not close_event.is_set():
            # łapiemy fifo jako plik
            line = None
            line = mff.readline()
            
            if line == None: continue
            
            line = line.strip()

            if line == "": continue
            print(f"[Customer-{customer_id}] Odebrano: {line}.")

            tokens = line.split()
            resp_type = tokens[0]
            table_id = tokens[2]

            if resp_type == "SEATED":
                print(f"[Customer-{customer_id}] Miejsce znalezione. Delektuje się pizzą...")
                
                # Każdy proces (grupa) ma wątki (osoby)
                threads = []
                for person_i in range(1, group_size + 1):
                    t = threading.Thread(target=person_in_group, args=(person_i,customer_id, close_event, fire_event))
                    threads.append(t)

                # Wątki jedzą
                for t in threads:
                    t.start()

                # Czekamy aż wszyscy z grupy zjedzą
                for t in threads:
                    t.join()

                if close_event.is_set():
                    break

                if fire_event.is_set():
                    print(f"[Customer-{customer_id}] Pożar! Klient ucieka.")
                    break

                done_line = f"{my_fifo}:CUSTOMER_DONE {group_size} {table_id}\n"
                write_to_server_fifo(done_line)

                print(f"[Customer-{customer_id}] Pizza zjedzona. Klient wychodzi.")
                return
            
            elif resp_type == "REJECTED":
                print(f"[Customer-{customer_id}] Brak miejsc. Klient wychodzi.")
                return
                    
            elif resp_type == "LEAVE":
                print(f"[Customer-{customer_id}] Manager powiedział że jest pożar. Klient wychodzi.")
                return
            
        # usuwamy fifo managera
        try:
            mff.close()
            os.close(mf)
        except:
            pass
        print(f"[Customer-{customer_id}] Wychodzi.")
    except Exception as e:
        print(f"[Customer-{customer_id}] ERROR: {e}")
        traceback.print_exc()
        remove_my_fifo(customer_id, my_fifo)
    finally:
        remove_my_fifo(customer_id, my_fifo)
        print(f"[Customer-{customer_id}] Zakańczanie.")

def write_to_server_fifo(req_line):
    sf = os.open(SERVER_FIFO, os.O_WRONLY | os.O_NONBLOCK)
    os.write(sf, bytes(req_line, "utf-8"))
    os.close(sf)

def remove_my_fifo(customer_id, name):
    print(f"[Customer-{customer_id}] Usuwam fifo ->{name}")
    if os.path.exists(name):
        os.remove(name)