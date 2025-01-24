import signal

FIRE_SIGNAL = signal.SIGUSR1 if hasattr(signal, 'SIGUSR1') else signal.SIGINT
SHUTDOWN_SIGNAL = signal.SIGINT
SERVER_FIFO = "manager_fifo"

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

MAX_CONCURRENT_CUSTOMERS = 30 # limity aktywnych na raz klientów
