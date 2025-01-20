from multiprocessing import Queue
import queue as queue_module

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
