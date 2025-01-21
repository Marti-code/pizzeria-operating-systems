import time
import random
import traceback
from multiprocessing import Queue, Event

"""
Moduł firefighter:
- wywołuje pożary w pizzerii co pewien losowy czas
"""

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
                print("[Firefighter] Wysyłanie sygnału pożaru.", flush=True)
            except ProcessLookupError:
                print("[Firefighter] Manager nie istnieje.")
                break
            except AttributeError:
                # Zabezpieczenie jak SIGUSR1 nie zadziała
                print("[Firefighter] Ustawianie fire_event.")
                fire_event.set()

    except KeyboardInterrupt:
        print("[Firefighter] KeyboardInterrupt => zakańczanie.")
    except Exception as e:
        print("[Firefighter] ERROR:", e)
        traceback.print_exc()
    finally:
        print("[Firefighter] Zakańczanie.")
