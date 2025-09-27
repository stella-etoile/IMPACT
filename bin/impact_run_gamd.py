import os, re, shutil, stat, subprocess, curses, glob
from pathlib import Path

def _read_conf(conf_path):
    d = {}
    if os.path.exists(conf_path):
        with open(conf_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"): continue
                m = re.match(r'^([A-Za-z0-9_]+)\s*=\s*(.*)$', s)
                if m:
                    k, v = m.group(1).strip(), m.group(2).strip()
                    d[k] = v
    return d

def _ensure_slurm_header(script_path, account, partition):
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
                if found: break
        if not found:
            insert_at = 1 if shebang_idx == 0 else 0
            lines.insert(insert_at, new_line)
    if account:
        repl_flag(lines, ["account","A"], f"#SBATCH --account={account}")
    if partition:
        repl_flag(lines, ["partition","p"], f"#SBATCH --partition={partition}")
    text2 = "\n".join(lines) + ("\n" if not text.endswith("\n") else "")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(text2)

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

def _submit(stdscr, cmd):
    script_dir = os.path.dirname(cmd[-1]) if cmd else None
    p = subprocess.run(cmd, cwd=script_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    jid = None
    if out:
        m = re.search(r'(\d+)\s*$', out)
        if m: jid = m.group(1)
    if stdscr:
        stdscr.clear()
        stdscr.addstr(0, 0, f"$ {' '.join(cmd)}")
        if out: stdscr.addstr(1, 0, out[:2000])
        if err: stdscr.addstr(2, 0, err[:2000])
        stdscr.refresh()
    return jid, out, err, p.returncode

def _scan_candidates(namd_proc_dir):
    home_dir = Path.cwd()
    root = home_dir / namd_proc_dir.strip("/")
    pattern = str(root / "*/NPT2/*.dcd")
    paths = glob.glob(pattern)
    found = {}
    for p in sorted(paths):
        d = Path(p).resolve()
        npt2 = d.parent
        combo = npt2.parent.name
        found[combo] = True
    return sorted(found.keys())

def _select_item(stdscr, title, items):
    idx = 0
    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        t = title
        x = max(0, (w - len(t)) // 2)
        if h > 0: stdscr.addstr(0, x, t, curses.A_BOLD)
        if not items:
            stdscr.addstr(2, 2, "No candidates found.")
            stdscr.addstr(4, 2, "Esc to go back")
            stdscr.refresh()
            k = stdscr.getch()
            if k in (27, ord('q')): return None
            continue
        start = 0
        per_page = max(1, h - 6)
        if idx >= start + per_page: start = idx - per_page + 1
        if idx < start: start = idx
        end = min(len(items), start + per_page)
        for i in range(start, end):
            y = 2 + (i - start)
            a = curses.A_REVERSE if i == idx else 0
            s = f"{i+1}. {items[i]}"
            stdscr.addstr(y, 2, s[:max(0, w-4)], a)
        stdscr.addstr(h-2, 2, "↑/↓ move  Enter select  Esc back")
        stdscr.refresh()
        k = stdscr.getch()
        if k in (curses.KEY_UP, ord('k')): idx = (idx - 1) % len(items)
        elif k in (curses.KEY_DOWN, ord('j')): idx = (idx + 1) % len(items)
        elif k in (10, 13, curses.KEY_ENTER): return items[idx]
        elif k in (27, ord('q')): return None

def run_run_gamd(stdscr, hint_attr):
    base = Path(__file__).resolve().parent.parent
    conf = _read_conf(str(base / "IMPACT.conf"))
    namd_proc_dir = conf.get("NAMD_PROC_DIR", "2_output/").strip()
    slurm_account = conf.get("SLURM_ACCOUNT", "").strip()
    slurm_partition = conf.get("SLURM_PARTITION", "").strip()
    slurm_cmd = conf.get("SLURM_CMD", "sbatch").strip() or "sbatch"

    candidates = _scan_candidates(namd_proc_dir)
    choice = _select_item(stdscr, "Select GaMD target (detected by NPT2/*.dcd)", candidates)
    if not choice:
        return

    if "_" in choice:
        prefix = "_".join(choice.split("_")[:-1])
        trial_num = choice.split("_")[-1]
    else:
        prefix = choice
        trial_num = "1"

    home_dir = Path.cwd()
    script_dir = home_dir / "gen_scripts"
    aux_dir = home_dir / "aux"
    combined_prefix = choice
    dest_dir = home_dir / namd_proc_dir.strip("/") / combined_prefix
    
    if not dest_dir.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)

    src_runner = aux_dir / "run_gen_gamd.sh"
    if not src_runner.exists():
        raise FileNotFoundError(str(src_runner))
    dst_runner = dest_dir / "run_gen_gamd.sh"
    shutil.copy2(src_runner, dst_runner)
    _chmod_x(dst_runner)

    p = subprocess.run([str(dst_runner), str(script_dir), prefix, str(trial_num)],
                       cwd=str(dest_dir),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    gen_out = (p.stdout or "").strip()
    gen_err = (p.stderr or "").strip()

    stdscr.clear()
    stdscr.addstr(0, 0, f"Ran: {dst_runner}", curses.A_BOLD)
    if gen_out: stdscr.addstr(2, 0, gen_out[:2000])
    if gen_err: stdscr.addstr(3, 0, gen_err[:2000])
    stdscr.refresh()

    try:
        os.remove(dst_runner)
    except Exception:
        pass

    gamd_dir = dest_dir / "gamd"
    if not gamd_dir.exists():
        raise FileNotFoundError(str(gamd_dir))

    equil_sh = gamd_dir / f"{combined_prefix}-gamd-equil.sh"
    prod_sh = gamd_dir / f"{combined_prefix}-gamd-prod.sh"
    if not equil_sh.exists() or not prod_sh.exists():
        raise FileNotFoundError("Missing equil/prod scripts in gamd/")

    _ensure_slurm_header(str(equil_sh), slurm_account, slurm_partition)
    _ensure_slurm_header(str(prod_sh), slurm_account, slurm_partition)

    jid, _, _, rc = _submit(stdscr, [slurm_cmd, str(equil_sh)])
    if rc != 0 or not jid:
        return

    npt1_sh = gamd_dir / f"{combined_prefix}-gamd-npt1.sh"
    shutil.copy2(prod_sh, npt1_sh)
    _replace_in_file(str(npt1_sh), r'\bgamd-prod\b', 'gamd-npt1')
    _ensure_slurm_header(str(npt1_sh), slurm_account, slurm_partition)

    jid, _, _, rc = _submit(stdscr, [slurm_cmd, f"--dependency=afterok:{jid}", str(prod_sh)])
    if rc != 0 or not jid:
        return

    for i in range(1, 8):
        cur_npt = i
        prev_npt = i - 1
        next_npt = i + 1
        cur_conf = gamd_dir / f"{combined_prefix}-gamd-npt{cur_npt}.conf"
        next_conf = gamd_dir / f"{combined_prefix}-gamd-npt{next_npt}.conf"
        next_sh = gamd_dir / f"{combined_prefix}-gamd-npt{next_npt}.sh"

        if not cur_conf.exists():
            break

        shutil.copy2(cur_conf, next_conf)
        if (gamd_dir / f"{combined_prefix}-gamd-{cur_npt}.sh").exists():
            shutil.copy2(gamd_dir / f"{combined_prefix}-gamd-{cur_npt}.sh", next_sh)
        else:
            shutil.copy2(npt1_sh, next_sh)

        _replace_in_file(str(next_conf), rf'\bnpt{cur_npt}\b', f"npt{next_npt}")
        _replace_in_file(str(next_sh), rf'\bnpt{cur_npt}\b', f"npt{next_npt}")
        if i == 1:
            _replace_in_file(str(next_conf), r'\bequil\b', 'npt1')
        else:
            _replace_in_file(str(next_conf), rf'\bnpt{prev_npt}\b', f"npt{cur_npt}")

        if i >= 2:
            _remove_in_file(str(next_conf), r'\breinitvels\s+\$temperature\b')

        _ensure_slurm_header(str(next_sh), slurm_account, slurm_partition)
        jid, _, _, rc = _submit(stdscr, [slurm_cmd, f"--dependency=afterok:{jid}", str(next_sh)])
        if rc != 0 or not jid:
            break
