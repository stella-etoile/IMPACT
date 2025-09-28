import os, re, glob, stat, shutil, subprocess, time, curses
from curses import textpad, ascii
from pathlib import Path
from typing import Optional, List, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DEFAULT_CONF = os.path.join(ROOT_DIR, "IMPACT.conf")

SUBTITLE = "Run GaMD"
EXAMPLES_ADD = "Add: e.g., TCR_06_1 TCR_07_2"
EXAMPLES_REMOVE = "Remove: e.g., TCR_06_1 TCR_07_2"

CFG_KEYS = [
    "NAMD_PROC_DIR",
    "SLURM_ACCOUNT",
    "SLURM_PARTITION",
    "SLURM_CMD",
    "EXCLUDE",
    "NTASKS_PER_NODE",
    "NUM_GPU",
    "QOS",
    "WALL_TIME_GAMD_EQUIL",
    "WALL_TIME_GAMD_PROD",
]

def find_conf():
    if os.path.exists(DEFAULT_CONF):
        return DEFAULT_CONF
    p = os.path.join(os.getcwd(), "IMPACT.conf")
    return p if os.path.exists(p) else None

def read_config():
    conf = find_conf()
    namd_proc_dir = os.path.join(ROOT_DIR, "2_output")
    if conf and os.path.exists(conf):
        base = os.path.dirname(conf)
        with open(conf) as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("NAMD_PROC_DIR"):
                    _, v = s.split("=", 1)
                    namd_proc_dir = os.path.abspath(os.path.join(base, v.strip().strip('"').strip("'")))
    return namd_proc_dir, (conf if conf else DEFAULT_CONF)

def tokens_from(s):
    s = s.replace(",", " ")
    return [t.strip() for t in s.split() if t.strip()]

def init_colors():
    err_attr = curses.A_BOLD
    hint_attr = curses.A_DIM
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
        except Exception:
            pass
        curses.init_pair(1, curses.COLOR_RED, -1)
        err_attr = curses.color_pair(1) | curses.A_BOLD
        if getattr(curses, "COLORS", 8) >= 256:
            curses.init_pair(10, 244, -1)
            hint_attr = curses.color_pair(10)
        curses.init_pair(11, curses.COLOR_YELLOW, -1)
    return err_attr, hint_attr

def wrap_line(s, w):
    if w <= 0:
        return [""]
    out, cur = [], ""
    for tok in s.split():
        if len(cur) + len(tok) + (1 if cur else 0) <= w:
            cur = (cur + " " + tok).strip()
        else:
            out.append(cur)
            cur = tok
    if cur:
        out.append(cur)
    return out or [""]

def wrap_tokens(stdscr, y, x, w, tokens, hi_idx=None, attr_hi=0, attr_norm=0):
    if w <= 4:
        return 0
    cx, cy = x, y
    used = 1
    for i, tok in enumerate(tokens):
        t = tok + " "
        if cx + len(t) > w - 2:
            cy += 1
            cx = x
            used += 1
        attr = attr_hi if (hi_idx is not None and i == hi_idx) else attr_norm
        try:
            stdscr.addstr(cy, cx, t, attr)
        except curses.error:
            pass
        cx += len(t)
    return used

def tail_lines(path, n=50, w=120):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size <= 0:
                return []
            block = 4096
            chunks = []
            read = 0
            while size > 0 and read < 1024 * 1024 and sum(c.count(b"\n") for c in chunks) <= n + 4:
                to_read = block if size >= block else size
                size -= to_read
                f.seek(size)
                chunks.insert(0, f.read(to_read))
                read += to_read
            data = b"".join(chunks)
            lines = data.decode(errors="ignore").splitlines()[-n:]
            return [ln[: max(0, w - 6)] for ln in lines]
    except Exception:
        return []

def draw_trial_widget(stdscr, y, trial_num, focused, hint_attr):
    h, w = stdscr.getmaxyx()
    label = f"Trial: [{trial_num}]"
    x = max(0, (w - len(label)) // 2)
    if focused and y - 1 >= 0:
        try:
            stdscr.addstr(y - 1, x + len(label)//2, "▲", hint_attr)
        except Exception:
            try: stdscr.addstr(y - 1, x + len(label)//2, "^", hint_attr)
            except curses.error: pass
    attr = curses.A_REVERSE | curses.A_BOLD if focused else curses.A_BOLD
    try:
        stdscr.addstr(y, x, label, attr)
    except curses.error:
        pass
    if focused and y + 1 < h:
        try:
            stdscr.addstr(y + 1, x + len(label)//2, "▼", hint_attr)
        except Exception:
            try: stdscr.addstr(y + 1, x + len(label)//2, "v", hint_attr)
            except curses.error: pass

def list_gamd_candidates(namd_proc_dir):
    items = []
    root = Path(namd_proc_dir)
    if not root.is_dir():
        return []
    for entry in sorted(os.listdir(root)):
        run_dir = root / entry
        if not run_dir.is_dir():
            continue
        hits = glob.glob(str(run_dir / "NPT2" / "*.dcd"))
        if hits:
            items.append(entry)
    return items

def list_gamd_prepared(namd_proc_dir, names):
    ready = set()
    for n in names:
        gdir = os.path.join(namd_proc_dir, n, "gamd")
        if os.path.isdir(gdir):
            scripts = glob.glob(os.path.join(gdir, f"{n}-gamd-*.sh"))
            if scripts:
                ready.add(n)
    return ready

def safe_addstr(stdscr, y, x, s, attr=0):
    try:
        stdscr.addstr(y, x, s, attr)
    except curses.error:
        pass

def parse_combined(name):
    m = re.match(r"^(.+)_([0-9]+)$", name)
    if not m:
        return None, None
    return m.group(1), m.group(2)

def _chmod_x(path):
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IXUSR)

def _replace_in_file(path, find_pat, repl):
    with open(path, "r", encoding="utf-8") as f:
        s = f.read()
    s2 = re.sub(find_pat, repl, s)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s2)

def _remove_in_file(path, find_pat):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            if not re.search(find_pat, ln):
                f.write(ln)

def _ensure_slurm_header(script_path, account, partition, exclude=None, ntasks_per_node=None, num_gpu=None, qos=None, wall_time=None):
    with open(script_path, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    if not lines:
        return
    shebang_idx = 0 if lines[0].startswith("#!") else None
    def repl_flag(lines, klist, new_line):
        found = False
        for i, ln in enumerate(lines):
            s = ln.strip()
            if s.startswith("#SBATCH"):
                for kk in klist:
                    if re.search(r'(^|\s)(--?%s)(=|\s|$)' % re.escape(kk), s):
                        lines[i] = new_line
                        found = True
                        break
                if found:
                    break
        if not found:
            insert_at = 1 if shebang_idx == 0 else 0
            lines.insert(insert_at, new_line)
    if account:
        repl_flag(lines, ["account","A"], f"#SBATCH --account={account}")
    if partition:
        repl_flag(lines, ["partition","p"], f"#SBATCH --partition={partition}")
    if wall_time:
        repl_flag(lines, ["time"], f"#SBATCH --time={wall_time}")
    if exclude:
        repl_flag(lines, ["exclude"], f"#SBATCH --exclude={exclude}")
    if ntasks_per_node:
        repl_flag(lines, ["ntasks-per-node"], f"#SBATCH --ntasks-per-node={ntasks_per_node}")
    if num_gpu:
        g = str(num_gpu)
        m = re.match(r'^\s*(?:gpu:)?(\d+)\s*$', g)
        gcount = m.group(1) if m else g
        repl_flag(lines, ["gres"], f"#SBATCH --gres=gpu:{gcount}")
    if qos:
        repl_flag(lines, ["qos"], f"#SBATCH --qos={qos}")
    text2 = "\n".join(lines) + ("\n" if not text.endswith("\n") else "")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(text2)

def _ensure_cd(script_path, gamd_dir):
    with open(script_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for ln in lines:
        if re.search(r'^\s*cd\s+', ln) and gamd_dir in ln:
            return
    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    last_sbatch = -1
    for i, ln in enumerate(lines):
        if ln.strip().startswith("#SBATCH"):
            last_sbatch = i
    insert_at = max(insert_at, last_sbatch + 1)
    lines.insert(insert_at, f"cd {gamd_dir}\n")
    with open(script_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

def parse_jobid(s):
    m = re.search(r"\b(\d{3,})\b", (s or "").strip())
    return m.group(1) if m else "?"

def sbatch_submit(sbatch, script_path, extra=None, dependency=None, cwd=None):
    cmd = [sbatch]
    if dependency:
        cmd.append(f"--dependency=afterok:{dependency}")
    if extra:
        cmd += extra
    cmd.append(script_path)
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
    ok = (r.returncode == 0)
    out = r.stdout.strip() if r.stdout else r.stderr.strip()
    return ok, parse_jobid(out), out

def build_gamd_chain(run_dir, combined, base_dir, conf):
    aux_dir = os.path.join(base_dir, "aux")
    script_dir = os.path.join(base_dir, "gen_scripts")
    dest_dir = os.path.join(run_dir)
    src_runner = os.path.join(aux_dir, "run_gen_gamd.sh")
    if not os.path.isfile(src_runner):
        return False, "run_gen_gamd.sh missing", None
    dst_runner = os.path.join(dest_dir, "run_gen_gamd.sh")
    shutil.copy2(src_runner, dst_runner)
    _chmod_x(dst_runner)
    prefix, trial = parse_combined(combined)
    p = subprocess.run([dst_runner, script_dir, prefix, str(trial)], cwd=dest_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        os.remove(dst_runner)
    except Exception:
        pass
    gamd_dir = os.path.join(dest_dir, "gamd")
    if not os.path.isdir(gamd_dir):
        return False, "gamd/ not created", None
    equil_sh = os.path.join(gamd_dir, f"{combined}-gamd-equil.sh")
    prod_sh  = os.path.join(gamd_dir, f"{combined}-gamd-prod.sh")
    if not (os.path.isfile(equil_sh) and os.path.isfile(prod_sh)):
        return False, "equil/prod scripts missing", None
    npt1_sh = os.path.join(gamd_dir, f"{combined}-gamd-npt1.sh")
    shutil.copy2(prod_sh, npt1_sh)
    _replace_in_file(npt1_sh, r'\bgamd-prod\b', 'gamd-npt1')
    for i in range(1, 8):
        cur_conf = os.path.join(gamd_dir, f"{combined}-gamd-npt{i}.conf")
        next_conf = os.path.join(gamd_dir, f"{combined}-gamd-npt{i+1}.conf")
        next_sh = os.path.join(gamd_dir, f"{combined}-gamd-npt{i+1}.sh")
        if not os.path.isfile(cur_conf):
            break
        shutil.copy2(cur_conf, next_conf)
        if os.path.isfile(os.path.join(gamd_dir, f"{combined}-gamd-{i}.sh")):
            shutil.copy2(os.path.join(gamd_dir, f"{combined}-gamd-{i}.sh"), next_sh)
        else:
            shutil.copy2(npt1_sh, next_sh)
        _replace_in_file(next_conf, rf'\bnpt{i}\b', f"npt{i+1}")
        _replace_in_file(next_sh, rf'\bnpt{i}\b', f"npt{i+1}")
        if i == 1:
            _replace_in_file(next_conf, r'\bequil\b', 'npt1')
        else:
            _replace_in_file(next_conf, rf'\bnpt{i-1}\b', f"npt{i}")
        if i >= 2:
            _remove_in_file(next_conf, r'\breinitvels\s+\$temperature\b')
    account   = conf.get("SLURM_ACCOUNT", "").strip()
    part      = conf.get("SLURM_PARTITION", "").strip()
    exclude   = conf.get("EXCLUDE", "").strip()
    ntasks    = conf.get("NTASKS_PER_NODE", "").strip()
    num_gpu   = conf.get("NUM_GPU", "").strip()
    qos       = conf.get("QOS", "").strip()
    wall_eq   = conf.get("WALL_TIME_GAMD_EQUIL", "").strip()
    wall_pr   = conf.get("WALL_TIME_GAMD_PROD", "").strip()
    _ensure_slurm_header(equil_sh, account, part, exclude=exclude, ntasks_per_node=ntasks, num_gpu=num_gpu, qos=qos, wall_time=wall_eq or None)
    _ensure_slurm_header(prod_sh,  account, part, exclude=exclude, ntasks_per_node=ntasks, num_gpu=num_gpu, qos=qos, wall_time=wall_pr or None)
    _ensure_slurm_header(npt1_sh,  account, part, exclude=exclude, ntasks_per_node=ntasks, num_gpu=num_gpu, qos=qos, wall_time=wall_pr or None)
    for i in range(2, 9):
        sh = os.path.join(gamd_dir, f"{combined}-gamd-npt{i}.sh")
        if os.path.isfile(sh):
            _ensure_slurm_header(sh, account, part, exclude=exclude, ntasks_per_node=ntasks, num_gpu=num_gpu, qos=qos, wall_time=wall_pr or None)
    for sh in [equil_sh, prod_sh, npt1_sh] + [os.path.join(gamd_dir, f"{combined}-gamd-npt{i}.sh") for i in range(2, 9) if os.path.isfile(os.path.join(gamd_dir, f"{combined}-gamd-npt{i}.sh"))]:
        if os.path.isfile(sh):
            _ensure_cd(sh, gamd_dir)
    scripts = {"equil": equil_sh, "prod": prod_sh, "npt": [os.path.join(gamd_dir, f"{combined}-gamd-npt{i}.sh") for i in range(1, 9) if os.path.isfile(os.path.join(gamd_dir, f"{combined}-gamd-npt{i}.sh"))], "dir": gamd_dir}
    return True, "ok", scripts

def submit_gamd_chain(sbatch, sbatch_extra, scripts):
    ok1, jid1, out1 = sbatch_submit(sbatch, scripts["equil"], extra=sbatch_extra, cwd=os.path.dirname(scripts["equil"]))
    if not ok1:
        return False, f"equil submit failed: {out1}"
    ok2, jid2, out2 = sbatch_submit(sbatch, scripts["prod"], extra=sbatch_extra, dependency=jid1, cwd=os.path.dirname(scripts["prod"]))
    if not ok2:
        return False, f"prod submit failed: {out2}"
    dep = jid2
    jids = [("equil", jid1), ("prod", jid2)]
    for i, sh in enumerate(scripts["npt"], start=1):
        ok, jid, out = sbatch_submit(sbatch, sh, extra=sbatch_extra, dependency=dep, cwd=os.path.dirname(sh))
        if not ok:
            return False, f"npt{i} submit failed: {out}"
        jids.append((f"npt{i}", jid))
        dep = jid
    return True, ", ".join([f"{k}={v}" for k, v in jids])

def compute_input_y(stdscr, names, ready, selection):
    h, w = stdscr.getmaxyx()
    names_lines = max(1, len(wrap_line(" ".join(names), max(10, w - 4))))
    ready_line = " ".join(sorted(set(names) & set(ready))) or "(none)"
    ready_lines = max(1, len(wrap_line(ready_line, max(10, w - 4))))
    sel_line = " ".join(sorted(selection)) if selection else "(empty)"
    sel_lines = max(1, len(wrap_line(sel_line, max(10, w - 4))))
    cur_y = 11 + names_lines
    cur2_y = cur_y + 1 + ready_lines + 1
    menu_y = cur2_y + 2 + sel_lines + 1
    return menu_y + 10

def draw(stdscr, title, hint_attr, namd_proc_dir, names, ready, selection, cursor_idx, focus, menu_cursor, trial_num, cfgs, msg="", msg_attr=0, err_attr=0):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    tx = max(0, (w - len(title)) // 2)
    try:
        stdscr.addstr(1, tx, title, curses.A_BOLD)
        draw_trial_widget(stdscr, 2, trial_num, focused=(focus == "trial"), hint_attr=hint_attr)
        stdscr.addstr(4, 2, "Focus: Tab switches • Esc/0 Back • Enter activates", hint_attr)
        stdscr.addstr(5, 2, "Menu: ↑/↓ or j/k move • 1–6 shortcuts • At trial: ↑/↓ to change", hint_attr)
        stdscr.addstr(6, 2, "Systems: ←/→ move • Enter toggles add/remove • ←/→ moves between systems ⇄ trial ⇄ menu", hint_attr)
        y = 8
        for k in CFG_KEYS:
            v = cfgs.get(k, "")
            s = f"{k}: {v}"
            stdscr.addstr(y, 2, s[: max(0, w - 4)], hint_attr)
            y += 1
        y += 1
        stdscr.addstr(y, 2, "GaMD-eligible systems (NPT2 detected):", curses.A_UNDERLINE)
        y += 1
    except curses.error:
        y = 12
    hi_idx = cursor_idx if (names and focus == "proc") else None
    lines_used = wrap_tokens(stdscr, y, 2, w, names, hi_idx=hi_idx, attr_hi=curses.A_REVERSE, attr_norm=0)
    cur_y = y + max(1, lines_used)
    try:
        stdscr.addstr(cur_y, 2, "Already GaMD-prepared:", curses.A_UNDERLINE)
    except curses.error:
        pass
    shown_ready = sorted(set(names) & set(ready))
    ready_line = " ".join(shown_ready) if shown_ready else "(none)"
    for j, line in enumerate(wrap_line(ready_line, max(10, w - 4))):
        try: stdscr.addstr(cur_y + 1 + j, 2, line)
        except curses.error: pass
    cur2_y = cur_y + 2 + max(1, len(wrap_line(ready_line, max(10, w - 4))))
    try: stdscr.addstr(cur2_y, 2, "Current selection:", curses.A_UNDERLINE)
    except curses.error: pass
    sel_line = " ".join(sorted(selection)) if selection else "(empty)"
    for k, line in enumerate(wrap_line(sel_line, max(10, w - 4))):
        try: stdscr.addstr(cur2_y + 1 + k, 2, line)
        except curses.error: pass
    menu_y = cur2_y + 3 + max(1, len(wrap_line(sel_line, max(10, w - 4))))
    options = [
        "1) Add all nonprocessed (recommended)",
        "2) Add all detected",
        "3) Add selection",
        "4) Remove selection",
        "5) Remove all",
        "6) Submit current selection",
        "0) Back",
    ]
    for idx, opt in enumerate(options):
        attr = curses.A_REVERSE if (focus == "menu" and idx == menu_cursor) else 0
        try: stdscr.addstr(menu_y + idx, 2, opt, attr)
        except curses.error: pass
    info_y = menu_y + len(options) + 1
    if msg:
        try: stdscr.addstr(info_y, 2, msg[: max(0, w - 4)], msg_attr)
        except curses.error: pass
    stdscr.refresh()
    return menu_y, len(options)

def prompt(stdscr, top_line, hint_attr, y_start=None):
    h, w = stdscr.getmaxyx()
    if y_start is None:
        y_start = h - 6
    try:
        stdscr.addstr(y_start, 2, top_line, hint_attr)
        stdscr.addstr(y_start + 1, 2, "Separate by space or comma • Esc=Back", hint_attr)
        stdscr.addstr(y_start + 3, 2, "> ")
    except curses.error:
        pass
    tb_win = curses.newwin(1, max(1, w - 6), y_start + 3, 4)
    curses.curs_set(1)
    box = textpad.Textbox(tb_win)
    cancelled = {"v": False}
    def validate(ch):
        if ch == 27:
            cancelled["v"] = True
            return ascii.BEL
        return ch
    s = box.edit(validate).strip()
    curses.curs_set(0)
    if cancelled["v"]:
        return None
    return s

def run_run_gamd(stdscr, inherited_hint_attr=None):
    namd_proc_dir, conf_path = read_config()
    conf = {}
    if os.path.exists(conf_path):
        with open(conf_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                conf[k.strip()] = v.strip()
    sbatch = conf.get("SLURM_CMD", "sbatch").strip() or "sbatch"
    extra = conf.get("SBATCH_EXTRA", "").strip()
    sbatch_extra = extra.split() if extra else []
    base_dir = ROOT_DIR
    curses.curs_set(0)
    stdscr.keypad(True)
    err_attr, hint_attr_local = init_colors()
    hint_attr = inherited_hint_attr if inherited_hint_attr is not None else hint_attr_local
    selection = set()
    focus = "menu"
    menu_cursor = 0
    proc_cursor = 0
    trial_num = 1
    while True:
        names = list_gamd_candidates(namd_proc_dir)
        ready = list_gamd_prepared(namd_proc_dir, names)
        if proc_cursor >= len(names):
            proc_cursor = max(0, len(names) - 1)
        cfgs = {}
        cfgs["NAMD_PROC_DIR"] = namd_proc_dir
        for k in CFG_KEYS:
            if k == "NAMD_PROC_DIR":
                continue
            cfgs[k] = conf.get(k, "")
        _, options_len = draw(stdscr, SUBTITLE, hint_attr, namd_proc_dir, names, ready, selection, proc_cursor, focus, menu_cursor, trial_num, cfgs)
        k = stdscr.getch()
        choice = None
        if k in (9, curses.KEY_BTAB):
            focus = "proc" if focus == "menu" else ("trial" if focus == "proc" else "menu")
        elif k in (curses.KEY_UP, ord('k')):
            if focus == "menu":
                if menu_cursor == 0:
                    focus = "proc"
                else:
                    menu_cursor = (menu_cursor - 1) % options_len
            elif focus == "trial":
                trial_num = max(1, trial_num - 1)
        elif k in (curses.KEY_DOWN, ord('j')):
            if focus == "menu":
                menu_cursor = (menu_cursor + 1) % options_len
            elif focus == "trial":
                trial_num = max(1, trial_num + 1)
            elif focus == "proc":
                focus = "menu"
        elif k in (curses.KEY_LEFT, ord('h')):
            if focus == "menu":
                focus = "trial"
            elif focus == "trial":
                trial_num = max(1, trial_num - 1)
            elif focus == "proc":
                proc_cursor = max(0, proc_cursor - 1) if names else 0
        elif k in (curses.KEY_RIGHT, ord('l')):
            if focus == "proc":
                if names:
                    proc_cursor = min(len(names) - 1, proc_cursor + 1)
            elif focus == "trial":
                trial_num = max(1, trial_num + 1)
        elif k in (10, 13, curses.KEY_ENTER):
            if focus == "menu":
                choice = menu_cursor
            elif focus == "proc":
                if names:
                    n = names[proc_cursor]
                    if n in selection:
                        selection.discard(n)
                    else:
                        selection.add(n)
        elif k in (ord('0'),):
            focus = "menu"
            choice = options_len - 1
        elif k in (ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6')):
            if focus != "trial":
                focus = "menu"
                desired = int(chr(k)) - 1
                if desired < options_len:
                    choice = desired
        elif k in (27, ord('q')):
            focus = "menu"
            choice = options_len - 1
        if choice is None:
            continue
        if choice == 0:
            nonprepared = [t for t in names if t not in ready]
            if not nonprepared:
                draw(stdscr, SUBTITLE, hint_attr, namd_proc_dir, names, ready, selection, proc_cursor, focus, menu_cursor, trial_num, cfgs, "All detected appear GaMD-prepared", err_attr, err_attr)
                stdscr.getch()
            else:
                selection.update(nonprepared)
        elif choice == 1:
            selection = set(names)
        elif choice == 2:
            y_in = compute_input_y(stdscr, names, ready, selection)
            s = prompt(stdscr, EXAMPLES_ADD, hint_attr, y_start=y_in)
            if s:
                toks = tokens_from(s)
                invalid = [t for t in toks if t not in names]
                valid = [t for t in toks if t in names]
                if valid:
                    selection.update(valid)
                if invalid:
                    draw(stdscr, SUBTITLE, hint_attr, namd_proc_dir, names, ready, selection, proc_cursor, focus, menu_cursor, trial_num, cfgs, "Invalid: " + ", ".join(invalid), err_attr, err_attr)
                    stdscr.getch()
        elif choice == 3:
            y_in = compute_input_y(stdscr, names, ready, selection)
            s = prompt(stdscr, EXAMPLES_REMOVE, hint_attr, y_start=y_in)
            if s:
                toks = tokens_from(s)
                not_in_list = [t for t in toks if t not in names]
                not_selected = [t for t in toks if t in names and t not in selection]
                to_remove = [t for t in toks if t in selection]
                for t in to_remove:
                    selection.discard(t)
                msgs = []
                if not_in_list:   msgs.append("Not found: " + ", ".join(not_in_list))
                if not_selected:  msgs.append("Not in selection: " + ", ".join(not_selected))
                if msgs:
                    draw(stdscr, SUBTITLE, hint_attr, namd_proc_dir, names, ready, selection, proc_cursor, focus, menu_cursor, trial_num, cfgs, " | ".join(msgs), err_attr, err_attr)
                    stdscr.getch()
        elif choice == 4:
            selection = set()
        elif choice == 5:
            if not selection:
                draw(stdscr, SUBTITLE, hint_attr, namd_proc_dir, names, ready, selection, proc_cursor, focus, menu_cursor, trial_num, cfgs, "Selection is empty", err_attr, err_attr)
                stdscr.getch()
            else:
                okc = 0
                failc = 0
                last = ""
                for combined in sorted(selection):
                    run_dir = os.path.join(namd_proc_dir, combined)
                    ok_b, det_b, scripts = build_gamd_chain(run_dir, combined, base_dir, conf)
                    if not ok_b:
                        failc += 1
                        last = f"{combined}: {det_b}"
                        continue
                    ok_s, det_s = submit_gamd_chain(sbatch, sbatch_extra, scripts)
                    if ok_s:
                        okc += 1
                        last = f"{combined}: {det_s}"
                    else:
                        failc += 1
                        last = f"{combined}: {det_s}"
                draw(stdscr, SUBTITLE, hint_attr, namd_proc_dir, names, ready, selection, proc_cursor, focus, menu_cursor, trial_num, cfgs, f"Chains submitted={okc} failed={failc}. {last}", 0 if failc==0 else err_attr, err_attr)
                stdscr.getch()
        elif choice == options_len - 1:
            return

def main():
    curses.wrapper(run_run_gamd)

if __name__ == "__main__":
    main()
