#!/bin/bash
set -euo pipefail

# -------------------- arg parsing --------------------
MODE="local"
CONF_PATH="./IMPACT.conf"
SELECTION_FILE=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "${1}" in
    --slurm) MODE="slurm"; shift ;;
    --local) MODE="local"; shift ;;
    --conf)  CONF_PATH="${2:-./IMPACT.conf}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    *)       SELECTION_FILE="${1}"; shift ;;
  esac
done

SELECTION_ENV="${SELECTION:-}"

# -------------------- config & paths --------------------
if [[ ! -f "$CONF_PATH" ]]; then
  echo "Missing IMPACT.conf at $CONF_PATH" >&2
  exit 1
fi
conf_abs="$(cd "$(dirname "$CONF_PATH")" && pwd)/$(basename "$CONF_PATH")"
conf_dir="$(dirname "$conf_abs")"

get_conf() {
  awk -v k="$1" -F'=' '
    $0 ~ "^[[:space:]]*"k"[[:space:]]*=" {
      sub(/^[[:space:]]*[^=]+=[[:space:]]*/,"",$0);
      gsub(/^["'"'"']|["'"'"']$/,"",$0);
      gsub(/^[[:space:]]+|[[:space:]]+$/,"",$0);
      print $0; exit
    }' "$conf_abs"
}

PDB_DIR_REL="$(get_conf 'PDB_DIR')"
PDB_PROC_DIR_REL="$(get_conf 'PDB_PROC_DIR')"
SLURM_ACCOUNT="$(get_conf 'SLURM_ACCOUNT')"
SLURM_PARTITION="$(get_conf 'SLURM_PARTITION')"
SLURM_CMD="$(get_conf 'SLURM_CMD')"

abspath() {
  case "$1" in
    /*) printf "%s\n" "$1" ;;
    *)  printf "%s\n" "$conf_dir/$1" ;;
  esac
}

pdb_dir="$(abspath "${PDB_DIR_REL:-.}")"
pdb_proc_dir="$(abspath "${PDB_PROC_DIR_REL:-.}")"
gen_sys_dir="$(abspath "NAMD/gen_system.tcl")"
aux_dir="$(abspath "aux")"
log_dir="$(abspath "log")"
mkdir -p "$pdb_proc_dir" "$log_dir"

# -------------------- selection list --------------------
declare -a selections
if [[ -n "$SELECTION_FILE" ]]; then
  if [[ ! -f "$SELECTION_FILE" ]]; then
    echo "Selection file not found: $SELECTION_FILE" >&2
    exit 1
  fi
  mapfile -t selections < <(grep -v '^\s*#' "$SELECTION_FILE" | awk 'NF{print $1}')
elif [[ -n "$SELECTION_ENV" ]]; then
  SELECTION_ENV="${SELECTION_ENV//,/ }"
  selections=($SELECTION_ENV)
else
  echo "Provide selection file as arg or SELECTION env" >&2
  exit 1
fi

for n in "${selections[@]}"; do
  if [[ ! -f "$pdb_dir/${n}.pdb" ]]; then
    echo "Missing PDB: $pdb_dir/${n}.pdb" >&2
    exit 1
  fi
done

# -------------------- SLURM checks (honor --force) --------------------
if [[ "$MODE" == "slurm" && $FORCE -eq 0 ]]; then
  if [[ -z "${SLURM_ACCOUNT:-}" || -z "${SLURM_PARTITION:-}" || -z "${SLURM_CMD:-}" ]]; then
    echo "SLURM not configured in IMPACT.conf" >&2
    exit 1
  fi
fi

# -------------------- local mode --------------------
if [[ "$MODE" == "local" ]]; then
  module load vmd || true
  for name in "${selections[@]}"; do
    base_dir="${pdb_proc_dir}/${name}"
    mkdir -p "$base_dir"
    cp -f "$pdb_dir/${name}.pdb" "$base_dir/"
    vmd -dispdev text -e "$aux_dir/init_setup.tcl" -args "$base_dir" "$gen_sys_dir" "$name" "1"
  done
  exit 0
fi

# -------------------- slurm mode (one job per selection) --------------------
: "${SLURM_CMD:=sbatch}"

for name in "${selections[@]}"; do
  job_name="IMPACT_${name}"
  "$SLURM_CMD" <<EOF
#!/bin/bash
#SBATCH --job-name=${job_name}
#SBATCH --time=00:10:00
#SBATCH --partition=${SLURM_PARTITION:-caslake}
#SBATCH --account=${SLURM_ACCOUNT:-unknown}
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=24
#SBATCH --output=${log_dir}/%x.out
#SBATCH --error=${log_dir}/%x.err
set -euo pipefail
module load vmd || true
pdb_dir="${pdb_dir}"
pdb_proc_dir="${pdb_proc_dir}"
gen_sys_dir="${gen_sys_dir}"
aux_dir="${aux_dir}"
name="${name}"
base_dir="\${pdb_proc_dir}/\${name}"
mkdir -p "\${base_dir}"
cp -f "\${pdb_dir}/\${name}.pdb" "\${base_dir}/"
vmd -dispdev text -e "\${aux_dir}/init_setup.tcl" -args "\${base_dir}" "\${gen_sys_dir}" "\${name}" "1"
EOF
done

exit 0