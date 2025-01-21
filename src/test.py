import unittest
import subprocess
import sys
import time
import os


class TestPizzeriaIntegration(unittest.TestCase):
    """
    Uruchamianie: python -m unittest test.py
    """

    def test_max_processes_not_exceeded(self):
        """
        Test: Czy nie przekraczamy MAX_CONCURRENT_CUSTOMERS (zdefiniowane w config.py) w main

        Założenie:
        - W main.py (lub manager) wypisujemy liczbę aktywnych klientów
        - Tutaj czytamy stdout i sprawdzamy, czy liczba aktywnych klientów kiedykolwiek > MAX_CONCURRENT_CUSTOMERS
        """

        proc = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        start_time = time.time()
        limit_exceeded = False
        MAX_LIMIT = 20  # bo w config.py => MAX_CONCURRENT_CUSTOMERS = 20

        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                # Proces się zakończył
                break

            if line:
                # Szukamy w linii informacji o CustomerProcs
                if "[Main]" in line and "CustomerProcs=" in line:
                    # np. "[Main] Obecnie CustomerProcs=12 aktywnych."
                    parts = line.strip().split("CustomerProcs=")
                    if len(parts) > 1:
                        try:
                            number_part = parts[1].split()[0]  # np. "12"
                            current_count = int(number_part)
                            if current_count > MAX_LIMIT:
                                limit_exceeded = True
                                break
                        except ValueError:
                            pass

            if time.time() - start_time > 15:
                # Po 15 sekundach przerywamy test
                break

        # Zamykamy proces
        proc.terminate()
        try:
            proc.stdout.close()
            proc.stderr.close()
            proc.wait(timeout=5)
        except:
            proc.kill()

        self.assertFalse(limit_exceeded, "Przekroczono MAX_CONCURRENT_CUSTOMERS w logach main.py!")

    def test_no_deadlock_in_fire_scenario(self):
        """
        Test: Sprawdza, czy przy wywołaniu pożaru (Firefighter) symulacja nie wisi w zakleszczeniu

        Założenie:
          - Uruchamiamy main.py, czekamy, aż Firefighter ustawi event pożaru
          - Obserwujemy czy Manager otwiera ponownie pizzerię (log "[Manager] Otwieranie pizzerii po pożarze.")
          - Jeśli w 80s nie zobaczymy tego loga => prawdopodobnie mamy blokadę
        """

        proc = subprocess.Popen(
            [sys.executable, "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        start_time = time.time()
        manager_reopened = False
        # Firefighter generuje pożar w 30..45 sekund, plus 10 sekund Manager odczekuje zanim otworzy ponownie pizzerie
        TIME_LIMIT = 80 

        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                # koniec
                break
            if line:
                if "[Manager] Reinicjalizacja stolików zakończona." in line:
                    manager_reopened = True
                    break
            if time.time() - start_time > TIME_LIMIT:
                break

        proc.terminate()
        try:
            proc.stdout.close()
            proc.stderr.close()
            proc.wait(timeout=5)
        except:
            proc.kill()

        self.assertTrue(manager_reopened, f"Nie znaleziono w logach '[Manager] Reinicjalizacja stolików zakończona.' w {TIME_LIMIT}s => możliwe zakleszczenie!")

if __name__ == "__main__":
    # Uruchamianie testów
    unittest.main()
