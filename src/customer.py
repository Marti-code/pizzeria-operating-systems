import time
import threading
import traceback
from multiprocessing import Queue, Event
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

def customer_process(queue: Queue, fire_event: Event, close_event: Event, group_size: int, customer_id: int):
    
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
    queue.put(("REQUEST_SEAT", (group_size, customer_id)))

    try:
        while not close_event.is_set():
            # Reakcja na pożar
            if fire_event.is_set():
                print(f"[Customer-{customer_id}] Pożar! Klient ucieka.")
                return

            # Odbieranie komunikatów z kolejki
            try:
                msg_type, data = queue.get_nowait()
                print(f"Klient{customer_id} zbiera z kolejki: {msg_type}, {data}")
            except queue_module.Empty:
                continue

            if msg_type not in ["SEATED", "REJECTED", "LEAVE"]:
                queue.put((msg_type, data))
                continue

            if data[0] == customer_id:
                if msg_type == "SEATED":
                    c_id, real_table_id = data
                    print(f"customer_id = {data[0]}")
                    print(f"customer_id = {customer_id}")
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

                        print(f"[Customer-{customer_id}] Pizza zjedzona. Klient wychodzi.")
                        queue.put(("CUSTOMER_DONE", (group_size, customer_id, table_id)))

                        return
                elif msg_type == "REJECTED":
                    c_id = data[0]
                    print(f"customer_id = {c_id}")
                    print(f"customer_id = {customer_id}")
                    if c_id == customer_id:
                        print(f"[Customer-{customer_id}] Brak miejsc. Klient wychodzi.")
                        return
                elif msg_type == "LEAVE":
                    c_id = data[0]
                    print(f"customer_id = {c_id}")
                    print(f"customer_id = {customer_id}")
                    if c_id == customer_id:
                        print(f"[Customer-{customer_id}] Manager powiedział że jest pożar. Klient wychodzi.")
                        return
            else:
                queue.put((msg_type, data))

    except KeyboardInterrupt:
        print(f"[Customer-{customer_id}] KeyboardInterrupt => zakańczanie.")
    except Exception as e:
        print(f"[Customer-{customer_id}] ERROR: {e}")
        traceback.print_exc()
    finally:
        print(f"[Customer-{customer_id}] Zakańczanie.")
