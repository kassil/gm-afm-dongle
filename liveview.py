import curses
import random
import time

# ------------------ DATA DEFINITIONS ------------------

def decode_temp(msg):
    return f"{20 + (msg[0] % 80):.1f} °C"

def decode_percent(msg):
    return f"{(msg[0] % 100):.1f} %"

def decode_rpm(msg):
    val = (msg[0] << 8) | msg[1]
    return f"{val % 8000} rpm"

# master_list: (ecu_id, sid, pid, label, description, decode_fn, enabled)
master_list = [
    (0x7E0, 0x01, 0x0C, "Engine RPM", "Engine speed in revolutions per minute", decode_rpm, True),
    (0x7E0, 0x01, 0x05, "Coolant Temp", "Engine coolant temperature", decode_temp, True),
    (0x7E8, 0x22, 0x1234, "Oil Pressure", "Measured oil pressure", decode_percent, False),
    (0x7E8, 0x22, 0x1235, "Throttle", "Throttle position", decode_percent, True),
]

# ------------------ RENDERING FUNCTIONS ------------------

def render_view(stdscr):
    stdscr.clear()
    stdscr.addstr(0, 0, "VIEW MODE  (press 'c' to configure, 'q' to quit)")
    row = 2
    for ecu, sid, pid, label, desc, fn, enabled in master_list:
        if not enabled:
            continue
        msg = bytes([random.randint(0, 255) for _ in range(2)])
        val = fn(msg)
        stdscr.addstr(row, 0, f"{ecu:04X}  SID:{sid:02X} PID:{pid:04X}  {label:12} {val}")
        row += 1
    stdscr.refresh()

def render_configure(stdscr, selected):
    stdscr.clear()
    stdscr.addstr(0, 0, "CONFIGURE MODE  (↑↓ or j/k move, space=toggle, v=view, q=quit)")
    row = 2
    for i, (ecu, sid, pid, label, desc, fn, enabled) in enumerate(master_list):
        mark = "[X]" if enabled else "[ ]"
        line = f"{mark} {ecu:04X} SID:{sid:02X} PID:{pid:04X}  {label:12}  {desc}"
        if i == selected:
            stdscr.attron(curses.A_REVERSE)
            stdscr.addstr(row, 0, line)
            stdscr.attroff(curses.A_REVERSE)
        else:
            stdscr.addstr(row, 0, line)
        row += 1
    stdscr.refresh()

# ------------------ MAIN LOOP ------------------

def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(False)
    mode_configure = False
    selected = 0

    while True:
        if not mode_configure:
            render_view(stdscr)
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('c'):
                mode_configure = True
            else:
                time.sleep(0.2)
        else:
            render_configure(stdscr, selected)
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key in (curses.KEY_UP, ord('k')):
                selected = (selected - 1) % len(master_list)
            elif key in (curses.KEY_DOWN, ord('j')):
                selected = (selected + 1) % len(master_list)
            elif key == ord(' '):
                ecu, sid, pid, label, desc, fn, enabled = master_list[selected]
                master_list[selected] = (ecu, sid, pid, label, desc, fn, not enabled)
            elif key == ord('v'):
                mode_configure = False

# ------------------ RUN ------------------

if __name__ == "__main__":
    curses.wrapper(main)
