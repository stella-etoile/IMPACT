import curses

def main(stdscr):
    curses.curs_set(0)
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    stdscr.addstr(0, 0, f"Terminal size: {w} cols x {h} rows")
    stdscr.addstr(2, 0, "Resize your terminal window and press any key to update.")
    stdscr.addstr(3, 0, "Press q to quit.")
    stdscr.refresh()
    while True:
        k = stdscr.getch()
        if k in (ord('q'), 27):
            break
        elif k == curses.KEY_RESIZE or k != -1:
            stdscr.clear()
            h, w = stdscr.getmaxyx()
            stdscr.addstr(0, 0, f"Terminal size: {w} cols x {h} rows")
            stdscr.addstr(2, 0, "Resize your terminal window and press any key to update.")
            stdscr.addstr(3, 0, "Press q to quit.")
            stdscr.refresh()

if __name__ == "__main__":
    curses.wrapper(main)
