import time
import threading
from config import SERVER_FIFO, CUSTOMER_FIFO_DIR
import traceback
from multiprocessing import Event
import queue as queue_module
from setproctitle import setproctitle
import os

"""
Moduł customer: 
- person_in_group() – funkcja wątku symulującego jedną osobę przy stole
- customer_process() – główna funkcja procesu klienta, który komunikuje się z Managerem przez kolejkę i reaguje na event pożaru
"""


def person_in_group(thread_id: int, customer_id: int):
    print(f"    [Customer-{customer_id} thread-{thread_id}] Jem...")
    # time.sleep(5)

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
    print(f"[Customer-{customer_id}] Klient (ilość osób={group_size}). Prośba o stolik.")
    
    my_fifo = CUSTOMER_FIFO_DIR + f"Customer_fifo_{customer_id}"
    if not os.path.exists(my_fifo):
        os.remove(my_fifo)
    os.mkfifo(my_fifo)

    req_line = f"{my_fifo}:REQUEST_SEAT {group_size} {customer_id}\n"
    write_to_server_fifo(req_line)

    try:
        while not close_event.is_set():
            # Reakcja na pożar
            if fire_event.is_set():
                print(f"[Customer-{customer_id}] Pożar! Klient ucieka.")
                return

            # Odbieranie komunikatów z kolejki
            with open(my_fifo, "r") as cf:
                resp_line = cf.readline().strip()
            if not resp_line:
                print(f"Brak odpowiedzi. Może manager umarł")
                fifo_cleanup(my_fifo)
                return
            
            tokens = resp_line.split()
            resp_type = tokens[0]
            table_id = tokens[2]

            if resp_type == "SEATED":
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

    except KeyboardInterrupt:
        print(f"[Customer-{customer_id}] KeyboardInterrupt => zakańczanie.")
        fifo_cleanup(my_fifo)
    except Exception as e:
        print(f"[Customer-{customer_id}] ERROR: {e}")
        traceback.print_exc()
    finally:
        print(f"[Customer-{customer_id}] Zakańczanie.")
        fifo_cleanup(my_fifo)

def write_to_server_fifo(req_line):
    with open(SERVER_FIFO, "w") as sf:
        sf.write(req_line)
        sf.flush()


def fifo_cleanup(my_fifo):
    if os.path.exists(my_fifo):
        os.remove(my_fifo)