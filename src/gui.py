import tkinter as tk
from multiprocessing import Queue, Event
from config import TABLE_COUNTS
import queue as queue_module
from setproctitle import setproctitle

"""
Moduł GUI:
- tworzy interfejs graficzny
- odpowiednio maluje stoły na czerwono jeśli są całkowicie zajęte, żółto jeśli po części, zielono jeśli są wolne
- maluje stoły na czarno gdy jest pożar
- wyświetla dotychczasowy profit
"""

def gui_process(gui_queue: Queue, close_event: Event):
    setproctitle(f"GUIProcess")
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

    root.configure(bg="#0a0a2b") # tło okienka

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

    # Na razie sprawdzamy gui_queue co 100ms
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

    root.after(100, poll_queue)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("[GUI] KeyboardInterrupt => Zakańczanie...")
        close_event.set()
        root.destroy()