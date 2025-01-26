import time
import random
import traceback
from multiprocessing import Event
from setproctitle import setproctitle
from config import CLOSURE_DURATION_AFTER_FIRE, FIRE_SIGNAL
import os

"""
Moduł firefighter:
- wywołuje pożary w pizzerii co pewien losowy czas
"""

def firefighter_process(manager_pid: int, fire_event: Event, close_event: Event):
    setproctitle(f"FirefighterProcess")
    print("[Firefighter] Rozpoczynanie. Będzie wysyłać sygnały co 30 - 45 sekund.")
    
    kill_firefighter = False
    try:
        while not close_event.is_set():
            delay = random.randint(30,45)
            print(f"[Firefighter] Następny pożar za ~{delay} sekund...")
            time.sleep(delay)
            
            ctime = time.time()

            kill_firefighter = False
            while True:
                if close_event.is_set():
                    # w czasie trwania delay poleciał close_event więc zamykamy process
                    kill_firefighter = True
                    break
                if time.time() - ctime > delay:
                    # delay minął
                    break
            
            if kill_firefighter:
                break

            # wysyłanie sygnału do managera
            os.kill(manager_pid, FIRE_SIGNAL) # informacja dla maina
            fire_event.set() # informacja dla pozostałych
            print("[Firefighter] Wysłano sygnału pożaru.", flush=True)

            # aktualny czas w sekundach
            ctime = time.time()

            kill_firefighter = False
            while True:
                if close_event.is_set():
                    # w czasie trwania delay poleciał close_event więc zamykamy process
                    kill_firefighter = True
                    break
                if time.time() - ctime > CLOSURE_DURATION_AFTER_FIRE:
                    # delay minął
                    break
            
            if kill_firefighter:
                break
            
            #gasi pozar
            print("[Firefighter] Pożar ugaszony.")
            fire_event.clear()

    except Exception as e:
        print("[Firefighter] ERROR:", e)
        traceback.print_exc()
    finally:
        print("[Firefighter] Zakańczanie.")
