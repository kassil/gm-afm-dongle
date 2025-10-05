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
    (0x7E8, 0x22, 0x1236, "Battery Volt", "System voltage", decode_percent, True),
    (0x7E8, 0x22, 0x1237, "Fuel Level", "Fuel tank level", decode_percent, True),
    (0x7E8, 0x22, 0x1238, "Manifold Temp", "Air manifold temperature", decode_temp, False),
    (0x7E8, 0x22, 0x1239, "Oil Temp", "Engine oil temperature", decode_temp, False),
    (0x7E8, 0x22, 0x1240, "Torque", "Delivered engine torque", decode_percent, True),
    (0x7E8, 0x22, 0x1241, "MAP", "Manifold absolute pressure", decode_percent, True),
]

# ------------------ RENDERING FUNCTIONS ------------------

def render_view(stdscr, scroll_offset):
    stdscr.clear()
    stdscr.addstr(0, 0, "VIEW MODE  (↑↓ scroll, 'c'=configure, 'q'=quit)")
    row = 2
    visible_rows = curses.LINES - 3
    active = [e for e in master_list if e[-1]]
    visible = active[scroll_offset: scroll_offset + visible_rows]
    for ecu, sid, pid, label, desc, fn, enabled in visible:
        msg = bytes([random.randint(0, 255) for _ in range(2)])
        val = fn(msg)
        stdscr.addstr(row, 0, f"{ecu:04X}  SID:{sid:02X} PID:{pid:04X}  {label:12} {val}")
        row += 1
    stdscr.refresh()

def render_configure(stdscr, selected, scroll_offset):
    stdscr.clear()
    stdscr.addstr(0, 0, "CONFIGURE MODE  (↑↓/j/k move, space=toggle, v=view, q=quit)")
    row = 2
    visible_rows = curses.LINES - 3
    visible = master_list[scroll_offset: scroll_offset + visible_rows]

    for i, entry in enumerate(visible):
        ecu, sid, pid, label, desc, fn, enabled = entry
        mark = "[X]" if enabled else "[ ]"
        line = f"{mark} {ecu:04X} SID:{sid:02X} PID:{pid:04X}  {label:12}  {desc}"

        global_index = scroll_offset + i
        if global_index == selected:
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
    scroll_offset = 0

    while True:
        visible_rows = curses.LINES - 3
        if not mode_configure:
            render_view(stdscr, scroll_offset)
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('c'):
                mode_configure = True
                selected = 0
                scroll_offset = 0
            elif key in (curses.KEY_DOWN, ord('j')):
                active = [e for e in master_list if e[-1]]
                if scroll_offset + visible_rows < len(active):
                    scroll_offset += 1
            elif key in (curses.KEY_UP, ord('k')):
                if scroll_offset > 0:
                    scroll_offset -= 1
            else:
                time.sleep(0.1)
        else:
            render_configure(stdscr, selected, scroll_offset)
            key = stdscr.getch()
            if key == ord('q'):
                break
            elif key == ord('v'):
                mode_configure = False
                scroll_offset = 0
            elif key in (curses.KEY_UP, ord('k')):
                if selected > 0:
                    selected -= 1
                    if selected - scroll_offset < 2 and scroll_offset > 0:
                        scroll_offset -= 1
            elif key in (curses.KEY_DOWN, ord('j')):
                if selected < len(master_list) - 1:
                    selected += 1
                    if selected - scroll_offset > visible_rows - 3:
                        scroll_offset += 1
            elif key == ord(' '):
                ecu, sid, pid, label, desc, fn, enabled = master_list[selected]
                master_list[selected] = (ecu, sid, pid, label, desc, fn, not enabled)

# ------------------ RUN ------------------

if __name__ == "__main__":
    curses.wrapper(main)
