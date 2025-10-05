# liveview.py
import curses
import time
from enum import Enum

class Mode(Enum):
    VIEW = 0
    CONFIG = 1

class LiveViewer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.mode = Mode.VIEW
        self.cursor = 0

        # Example table of possible IDs
        self.did_table = [
            {"ecu": "7E0", "label": "RPM",        "desc": "Engine speed"},
            {"ecu": "7E0", "label": "CoolantTemp","desc": "Engine coolant temp"},
            {"ecu": "7E0", "label": "ThrottlePos","desc": "Throttle position"},
            {"ecu": "7E1", "label": "TransTemp",  "desc": "Transmission temp"},
        ]

        # Initially active (tuples of arb_id, sid, pid)
        self.active_ids = [
            (0x7E0, 0x01, 0x0C),
            (0x7E0, 0x01, 0x05)
        ]

        # Placeholder values — later replaced by CAN polling
        self.data_values = { (r["ecu"], r["label"]): "—" for r in self.did_table }

    def run(self):
        curses.curs_set(0)
        self.stdscr.nodelay(True)
        while True:
            self.draw()
            self.handle_input()
            if self.mode == Mode.VIEW:
                self.poll_data()
            time.sleep(0.2)

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        title = f"[{self.mode.name}]  c:configure, q:quit"
        self.stdscr.addstr(0, 0, title)

        for i, row in enumerate(self.did_table):
            y = i + 2
            if y >= h - 1:
                break

            ecu = row["ecu"].ljust(6)
            label = row["label"].ljust(12)
            key = (row["ecu"], row["label"])
            if self.mode == Mode.VIEW:
                value = str(self.data_values.get(key, "")).rjust(10)
            else:
                # configuration mode: show description + [x]/[ ]
                active = self.is_active(row)
                mark = "[x]" if active else "[ ]"
                value = f"{mark} {row['desc']}"
            line = f"{ecu} {label} {value}"
            if i == self.cursor:
                self.stdscr.attron(curses.A_REVERSE)
                self.stdscr.addstr(y, 0, line[:w-1])
                self.stdscr.attroff(curses.A_REVERSE)
            else:
                self.stdscr.addstr(y, 0, line[:w-1])
        self.stdscr.refresh()

    def handle_input(self):
        try:
            ch = self.stdscr.getkey()
        except Exception:
            return
        if ch in ('q', 'Q'):
            raise SystemExit
        elif ch in ('c', 'C'):
            self.mode = Mode.CONFIG if self.mode == Mode.VIEW else Mode.VIEW
        elif ch in ('KEY_UP', 'k'):
            self.cursor = max(0, self.cursor - 1)
        elif ch in ('KEY_DOWN', 'j'):
            self.cursor = min(len(self.did_table) - 1, self.cursor + 1)
        elif self.mode == Mode.CONFIG and ch == ' ':
            self.toggle_active(self.did_table[self.cursor])

    def toggle_active(self, row):
        ecu = int(row["ecu"], 16)
        sid = 0x01
        pid = 0x0C  # placeholder; in real use each row stores its own PID
        tup = (ecu, sid, pid)
        if tup in self.active_ids:
            self.active_ids.remove(tup)
        else:
            self.active_ids.append(tup)

    def is_active(self, row):
        ecu = int(row["ecu"], 16)
        return any(a[0] == ecu for a in self.active_ids)

    def poll_data(self):
        # Placeholder: simulate data changing
        for key in self.data_values:
            if "RPM" in key[1]:
                self.data_values[key] = f"{int(time.time()*10)%4000} rpm"
            elif "Temp" in key[1]:
                self.data_values[key] = f"{80 + int(time.time())%20} °C"
            elif "Throttle" in key[1]:
                self.data_values[key] = f"{int(time.time()*7)%100}%"

def main():
    curses.wrapper(LiveViewer)

if __name__ == "__main__":
    curses.wrapper(lambda stdscr: LiveViewer(stdscr).run())
