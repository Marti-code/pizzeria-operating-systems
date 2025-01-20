import time
import threading
import traceback
from multiprocessing import Queue, Event
import queue as queue_module


def person_in_group(thread_id: int, customer_id: int):
    print(f"    [Customer-{customer_id} thread-{thread_id}] Jem...")
    time.sleep(5)

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
