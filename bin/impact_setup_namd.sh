#!/usr/bin/env bash
set -euo pipefail

# -------------------- arg parsing --------------------
CONF_PATH="./IMPACT.conf"
TRIAL=""
SELECTION_FILE=""

while [[ $# -gt 0 ]]; do
  case "${1}" in
    --conf)     CONF_PATH="${2:-./IMPACT.conf}"; shift 2 ;;
    --trial|-t) TRIAL="${2:-}"; shift 2 ;;
    *)          SELECTION_FILE="${1}"; shift ;;
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

abspath() {
  case "$1" in
    /*) printf "%s\n" "$1" ;;
    "") printf "%s\n" "$conf_dir" ;;
    *)  printf "%s\n" "$conf_dir/$1" ;;
  esac
}

# Inputs (prepared systems) come from PDB_PROC_DIR (default 1_output)
PDB_PROC_DIR_REL="$(get_conf 'PDB_PROC_DIR')"
input_src_root="$(abspath "${PDB_PROC_DIR_REL:-1_output}")"

# Outputs go to NAMD_PROC_DIR (default 2_output)
NAMD_PROC_DIR_REL="$(get_conf 'NAMD_PROC_DIR')"
namd_root="$(abspath "${NAMD_PROC_DIR_REL:-2_output}")"

# Generator support dirs/files:
script_dir="$(abspath "gen_scripts")"
aux_dir="$(abspath "aux")"
run_gen_namd="${aux_dir}/run_gen_namd.sh"

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
  # shellcheck disable=SC2206
  selections=($SELECTION_ENV)
else
  echo "Provide selection file as arg or SELECTION env" >&2
  exit 1
fi

if [[ -z "${TRIAL}" ]]; then
  echo "Trial number is required: --trial N (or -t N)" >&2
  exit 1
fi

# -------------------- sanity checks --------------------
if [[ ! -d "$input_src_root" ]]; then
  echo "Source directory not found (PDB_PROC_DIR): $input_src_root" >&2
  exit 1
fi
if [[ ! -d "$script_dir" ]]; then
  echo "gen_scripts directory not found: $script_dir" >&2
  exit 1
fi
if [[ ! -x "$run_gen_namd" ]]; then
  echo "Helper script not executable: $run_gen_namd" >&2
  exit 1
fi

mkdir -p "$namd_root"

# -------------------- main (local) --------------------
copy_required() {
  local src="$1" dst="$2"
  if [[ ! -f "$src" ]]; then
    echo "  [!] Missing required file: $src" >&2
    return 1
  fi
  mkdir -p "$(dirname "$dst")"
  cp -f "$src" "$dst"
  echo "  [✓] Copied $(basename "$src")"
}

echo "==> Trial: ${TRIAL}"
echo "==> PDB_PROC_DIR (input): ${input_src_root}"
echo "==> NAMD_PROC_DIR (output root): ${namd_root}"
echo "==> Prefixes: ${selections[*]}"
echo

for prefix in "${selections[@]}"; do
  echo "---- Processing: ${prefix} (trial ${TRIAL}) ----"

  combined_prefix="${prefix}_${TRIAL}"
  src_dir="${input_src_root}/${prefix}"       # inputs live in 1_output/<prefix>/
  dest_dir="${namd_root}/${combined_prefix}"  # outputs in 2_output/<prefix>_<trial>/

  mkdir -p "${dest_dir}/mini"

  # required artifacts from 1_output/<prefix>/ (files already suffixed with _<trial>)
  copy_required "${src_dir}/${combined_prefix}_pbc.txt"                        "${dest_dir}/${combined_prefix}_pbc.txt"                             || { echo "  Skipping ${prefix} due to missing files."; echo; continue; }
  copy_required "${src_dir}/${combined_prefix}_ionized.psf"                    "${dest_dir}/${combined_prefix}_ionized.psf"                         || { echo "  Skipping ${prefix} due to missing files."; echo; continue; }
  copy_required "${src_dir}/${combined_prefix}_solvated_ionized_centered.pdb"  "${dest_dir}/mini/${combined_prefix}_solvated_ionized_centered.pdb" || { echo "  Skipping ${prefix} due to missing files."; echo; continue; }
  copy_required "${src_dir}/${combined_prefix}_restrain.pdb"                   "${dest_dir}/mini/${combined_prefix}_restrain.pdb"                   || { echo "  Skipping ${prefix} due to missing files."; echo; continue; }

  # stage & run generator inside destination
  cp -f "$run_gen_namd" "${dest_dir}/"
  (
    cd "${dest_dir}"
    chmod +x run_gen_namd.sh
    ./run_gen_namd.sh "${script_dir}" "${prefix}" "${TRIAL}"
    rm -f run_gen_namd.sh
  )

  echo "  [✓] Generated NAMD job files in ${dest_dir}"
  echo
done

echo "All done."