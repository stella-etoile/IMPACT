import os
import curses
from curses import textpad, ascii
from datetime import datetime

CONF_BASENAME = "IMPACT.conf"
BACKUP_DIR = "conf_backups"

# ---------------------------- FS helpers ----------------------------

def find_conf():
    cwd = os.getcwd()
    p = os.path.join(cwd, CONF_BASENAME)
    return p

def load_conf_lines(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()

def parse_lines(lines):
    out = []
    for i, raw in enumerate(lines):
        s = raw.rstrip("\n")
        stripped = s.strip()
        if not stripped or stripped.startswith("#"):
            out.append({"idx": i, "raw": s, "is_kv": False})
            continue
        if "=" in stripped:
            k, v = stripped.split("=", 1)
            out.append({"idx": i, "raw": s, "is_kv": True, "key": k.strip(), "value": v.strip()})
        else:
            out.append({"idx": i, "raw": s, "is_kv": False})
    return out

def rebuild_lines(entries):
    out = []
    for e in entries:
        if e.get("is_kv"):
            k = e.get("key", "").strip()
            v = e.get("value", "")
            out.append(f"{k} = {v}")
        else:
            out.append(e.get("raw", ""))
    return [ln + "\n" for ln in out]

# ---------------------------- UI helpers ----------------------------

def init_colors():
    err_attr = curses.A_BOLD
    hint_attr = curses.A_DIM
    ok_attr = curses.A_BOLD
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
        except Exception:
            pass
        curses.init_pair(1, curses.COLOR_RED, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        err_attr = curses.color_pair(1) | curses.A_BOLD
        ok_attr = curses.color_pair(2) | curses.A_BOLD
        if getattr(curses, "COLORS", 8) >= 256:
            curses.init_pair(10, 244, -1)
            hint_attr = curses.color_pair(10)
    return err_attr, hint_attr, ok_attr

def safe_addstr(stdscr, y, x, text, attr=0):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass

def center(stdscr, y, text, attr=0):
    h, w = stdscr.getmaxyx()
    x = max(0, (w - len(text)) // 2)
    if 0 <= y < h:
        safe_addstr(stdscr, y, x, text[: max(0, w)], attr)

# ---------------------------- Backups ----------------------------

def backup_files(path):
    if not path:
        return []
    base_dir = os.path.dirname(path) or "."
    bdir = os.path.join(base_dir, BACKUP_DIR)
    if not os.path.isdir(bdir):
        return []
    base = os.path.basename(path)
    pref = base + ".bak."
    cand = []
    for f in os.listdir(bdir):
        if f.startswith(pref):
            full = os.path.join(bdir, f)
            try:
                mtime = os.path.getmtime(full)
            except Exception:
                mtime = 0
            cand.append((full, mtime))
    cand.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in cand]

def pick_backup(stdscr, path, hint_attr):
    files = []
    if path and os.path.exists(path):
        try:
            files.append(("cur", path, os.path.getmtime(path)))
        except Exception:
            files.append(("cur", path, 0))
    for fp in backup_files(path):
        try:
            mtime = os.path.getmtime(fp)
        except Exception:
            mtime = 0
        files.append(("bak", fp, mtime))
    
    head = [f for f in files if f[0] == "cur"]
    tail = sorted([f for f in files if f[0] == "bak"], key=lambda x: x[2], reverse=True)
    files = head + tail
    if not files:
        return None, None

    idx = 0
    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        center(stdscr, 1, "Select config or backup (Enter=load • Esc=cancel)", curses.A_BOLD)
        start_y = 3
        max_rows = max(3, h - start_y - 2)
        for i, (kind, fp, _) in enumerate(files[:max_rows]):
            name = os.path.basename(fp)
            label = f"cur  — {name}" if kind == "cur" else name
            attr = curses.A_REVERSE if i == idx else 0
            safe_addstr(stdscr, start_y + i, 2, label[: max(0, w - 4)], attr)
        stdscr.refresh()

        k = stdscr.getch()
        if k in (27,):  # Esc
            return None, None
        if k in (curses.KEY_UP, ord('k')):
            idx = (idx - 1) % len(files)
        elif k in (curses.KEY_DOWN, ord('j')):
            idx = (idx + 1) % len(files)
        elif k in (10, 13, curses.KEY_ENTER):
            return files[idx][0], files[idx][1]

def save_conf(path, entries):
    if not path:
        return False, "No config file path"
    base_dir = os.path.dirname(path) or "."
    os.makedirs(base_dir, exist_ok=True)

    bdir = os.path.join(base_dir, BACKUP_DIR)
    os.makedirs(bdir, exist_ok=True)
    backup = os.path.join(bdir, f"{os.path.basename(path)}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}")

    try:
        if os.path.exists(path):
            with open(backup, "w", encoding="utf-8") as b:
                with open(path, "r", encoding="utf-8", errors="replace") as cur:
                    b.write(cur.read())
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(rebuild_lines(entries))
        return True, f"Saved. Backup: {os.path.basename(backup)}"
    except Exception as e:
        return False, f"Save failed: {e}"

def backup_current_only(path):
    if not path:
        return False, "No config file path"
    if not os.path.exists(path):
        return True, "No current file to back up"
    base_dir = os.path.dirname(path) or "."
    bdir = os.path.join(base_dir, BACKUP_DIR)
    os.makedirs(bdir, exist_ok=True)
    backup = os.path.join(bdir, f"{os.path.basename(path)}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    try:
        with open(backup, "w", encoding="utf-8") as b:
            with open(path, "r", encoding="utf-8", errors="replace") as cur:
                b.write(cur.read())
        return True, f"Backed up current to {os.path.basename(backup)}"
    except Exception as e:
        return False, f"Backup failed: {e}"

def restore_backup(path, selected_fp):
    if not path or not selected_fp:
        return False, "Missing path/backup"
    ok, msg = backup_current_only(path)
    if not ok:
        return False, msg
    try:
        with open(selected_fp, "r", encoding="utf-8", errors="replace") as src, \
             open(path, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        return True, f"Restored {os.path.basename(selected_fp)} → {os.path.basename(path)}"
    except Exception as e:
        return False, f"Restore failed: {e}"

# ---------------------------- Drawing & Edit ----------------------------

def draw(stdscr, title, path, entries, cursor, top, err_attr, hint_attr, ok_attr,
         footer_cursor, focus, msg="", msg_attr=0):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    center(stdscr, 1, title, curses.A_BOLD)
    safe_addstr(stdscr, 3, 2, f"Config: {path or '(not found)'}", hint_attr)
    safe_addstr(stdscr, 4, 2, "Tab switches focus • ↑/↓ move • PgUp/PgDn scroll • Enter edit", hint_attr)

    header_y = 6
    safe_addstr(stdscr, header_y, 2, "Parameters:", curses.A_UNDERLINE)

    view_y = header_y + 1
    footer_y = h - 2
    view_h = max(1, footer_y - view_y - 1)
    kvs = [i for i, e in enumerate(entries) if e.get("is_kv")]
    if not kvs:
        safe_addstr(stdscr, view_y, 2, "(no parameters found)")
    else:
        top = max(0, min(top, max(0, len(kvs) - view_h)))
        cur_vis = kvs[top: top + view_h]
        for row, idx in enumerate(cur_vis):
            e = entries[idx]
            line = f"{e['key']:<24} = {e['value']}"
            attr = curses.A_REVERSE if (focus == "list" and idx == cursor) else 0
            safe_addstr(stdscr, view_y + row, 2, line[: max(0, w - 4)], attr)

    if msg:
        safe_addstr(stdscr, h - 3, 2, msg[: max(0, w - 4)], msg_attr)

    buttons = ["[ Back ]", "[ Save ]", "[ Reload ]", "[ Backups ]"]
    x = 2
    for i, b in enumerate(buttons):
        attr = curses.A_REVERSE if (focus == "footer" and footer_cursor == i) else 0
        safe_addstr(stdscr, footer_y, x, b, attr)
        x += len(b) + 2

    stdscr.refresh()
    return top, view_h

def prompt_edit(stdscr, key, old_value, hint_attr):
    h, w = stdscr.getmaxyx()
    y = h - 6
    for i in range(4):
        stdscr.move(y + i, 0); stdscr.clrtoeol()
    safe_addstr(stdscr, y, 2, f"Edit {key} (Esc=cancel):", hint_attr)
    safe_addstr(stdscr, y + 1, 2, "> ")
    tb = curses.newwin(1, max(1, w - 6), y + 1, 4)
    curses.curs_set(1)
    box = textpad.Textbox(tb)
    cancelled = {"v": False}
    def validate(ch):
        if ch == 27:
            cancelled["v"] = True
            return ascii.BEL
        return ch
    try:
        tb.addstr(0, 0, str(old_value))
    except curses.error:
        pass
    s = box.edit(validate).strip()
    curses.curs_set(0)
    if cancelled["v"]:
        return None
    return s

# ---------------------------- Main UI ----------------------------

def run_config_editor(stdscr, inherited_hint_attr=None):
    curses.curs_set(0)
    stdscr.keypad(True)
    err_attr, hint_attr_local, ok_attr = init_colors()
    hint_attr = inherited_hint_attr if inherited_hint_attr is not None else hint_attr_local

    path = find_conf()
    lines = load_conf_lines(path)
    entries = parse_lines(lines)
    kv_indices = [i for i, e in enumerate(entries) if e.get("is_kv")]
    cursor = kv_indices[0] if kv_indices else 0
    top = 0
    msg = ""; msg_attr = 0

    focus = "list"
    footer_cursor = 0  # 0 Back, 1 Save, 2 Reload, 3 Backups

    while True:
        kv_indices = [i for i, e in enumerate(entries) if e.get("is_kv")]
        top, view_h = draw(
            stdscr,
            "Change config",
            path,
            entries,
            cursor,
            top,
            err_attr,
            hint_attr,
            ok_attr,
            footer_cursor,
            focus,
            msg,
            msg_attr
        )
        msg = ""; msg_attr = 0
        k = stdscr.getch()

        if focus == "list":
            if k in (9, curses.KEY_BTAB, curses.KEY_RIGHT, curses.KEY_LEFT):
                focus = "footer"; continue
            if k in (ord('0'), 27):
                return
            if k in (curses.KEY_UP, ord('k')):
                prev = [i for i in range(cursor - 1, -1, -1) if entries[i].get("is_kv")]
                if prev: cursor = prev[0]
            elif k in (curses.KEY_DOWN, ord('j')):
                if kv_indices and cursor == kv_indices[-1]:
                    focus = "footer"; footer_cursor = 0
                else:
                    nxt = [i for i in range(cursor + 1, len(entries)) if entries[i].get("is_kv")]
                    if nxt: cursor = nxt[0]
            elif k == curses.KEY_PPAGE:
                for _ in range(view_h):
                    prev = [i for i in range(cursor - 1, -1, -1) if entries[i].get("is_kv")]
                    if not prev: break
                    cursor = prev[0]
                top = max(0, top - view_h)
            elif k == curses.KEY_NPAGE:
                for _ in range(view_h):
                    nxt = [i for i in range(cursor + 1, len(entries)) if entries[i].get("is_kv")]
                    if not nxt:
                        focus = "footer"; footer_cursor = 0
                        break
                    cursor = nxt[0]
                else:
                    top = top + view_h
            elif k in (10, 13, curses.KEY_ENTER):
                if not entries or not (0 <= cursor < len(entries)) or not entries[cursor].get("is_kv"):
                    continue
                key = entries[cursor]["key"]
                old = entries[cursor]["value"]
                newv = prompt_edit(stdscr, key, old, hint_attr)
                if newv is not None:
                    entries[cursor]["value"] = newv
                    msg, msg_attr = f"Updated {key}", ok_attr
                else:
                    msg, msg_attr = "Edit cancelled", hint_attr
            else:
                continue

        else:
            if k in (9, curses.KEY_BTAB):
                focus = "list"; continue
            if k in (curses.KEY_LEFT, ord('h')):
                footer_cursor = (footer_cursor - 1) % 4
            elif k in (curses.KEY_RIGHT, ord('l')):
                footer_cursor = (footer_cursor + 1) % 4
            elif k in (curses.KEY_UP, ord('k')):
                if kv_indices:
                    cursor = kv_indices[-1]
                    focus = "list"
            elif k in (10, 13, curses.KEY_ENTER):
                if footer_cursor == 0:
                    return
                elif footer_cursor == 1:
                    ok, m = save_conf(path, entries)
                    msg = m; msg_attr = ok_attr if ok else err_attr
                elif footer_cursor == 2:
                    path = find_conf()
                    lines = load_conf_lines(path)
                    entries = parse_lines(lines)
                    kv_indices = [i for i, e in enumerate(entries) if e.get("is_kv")]
                    cursor = kv_indices[0] if kv_indices else 0
                    top = 0
                    msg, msg_attr = "Reloaded", ok_attr
                elif footer_cursor == 3:
                    kind, fp = pick_backup(stdscr, path, hint_attr)
                    if fp:
                        if kind == "cur":
                            lines = load_conf_lines(path)
                            entries = parse_lines(lines)
                            kv_indices = [i for i, e in enumerate(entries) if e.get("is_kv")]
                            cursor = kv_indices[0] if kv_indices else 0
                            top = 0
                            msg, msg_attr = "Loaded current", ok_attr
                        else:
                            ok, m = restore_backup(path, fp)
                            msg, msg_attr = m, ok_attr if ok else err_attr
                            lines = load_conf_lines(path)
                            entries = parse_lines(lines)
                            kv_indices = [i for i, e in enumerate(entries) if e.get("is_kv")]
                            cursor = kv_indices[0] if kv_indices else 0
                            top = 0
                    else:
                        msg, msg_attr = "Backup load cancelled", hint_attr
            elif k in (ord('0'), 27):
                return
            elif k in (curses.KEY_DOWN, ord('j')):
                pass
            else:
                continue

if __name__ == "__main__":
    curses.wrapper(run_config_editor)