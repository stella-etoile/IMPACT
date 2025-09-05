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

PDB_PROC_DIR_REL="$(get_conf 'PDB_PROC_DIR')"
input_src_root="$(abspath "${PDB_PROC_DIR_REL:-1_output}")"

NAMD_PROC_DIR_REL="$(get_conf 'NAMD_PROC_DIR')"
namd_root="$(abspath "${NAMD_PROC_DIR_REL:-2_output}")"

script_dir="$(abspath "gen_scripts")"
aux_dir="$(abspath "aux")"
run_gen_namd="${aux_dir}/run_gen_namd.sh"

SLURM_ACCOUNT_VAL="$(get_conf 'SLURM_ACCOUNT')"
SLURM_PARTITION_VAL="$(get_conf 'SLURM_PARTITION')"

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

# -------------------- helpers --------------------
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

inject_slurm_headers() {
  local file="$1"
  local part="$2"
  local acct="$3"

  local tmpf="${file}.tmp"
  awk -v part="$part" -v acct="$acct" '
    NR==1{
      print $0
      printed=0
      # only add if not already present
      p_seen=0; a_seen=0
      next
    }
    {
      body = body $0 ORS
    }
    END{
      # Re-scan first few lines of body to detect existing lines
      split(body, L, ORS)
      for(i=1;i<=length(L)&&i<=10;i++){
        if(L[i] ~ /^#SBATCH[[:space:]]+--partition=/) p_seen=1
        if(L[i] ~ /^#SBATCH[[:space:]]+--account=/)   a_seen=1
      }
      if(part != "" && p_seen==0) print "#SBATCH --partition=" part
      if(acct != "" && a_seen==0) print "#SBATCH --account=" acct
      printf "%s", body
    }
  ' "$file" > "$tmpf"
  mv "$tmpf" "$file"
}

# -------------------- main (local) --------------------
echo "==> Trial: ${TRIAL}"
echo "==> PDB_PROC_DIR (input): ${input_src_root}"
echo "==> NAMD_PROC_DIR (output root): ${namd_root}"
echo "==> Prefixes: ${selections[*]}"
echo

for prefix in "${selections[@]}"; do
  echo "---- Processing: ${prefix} (trial ${TRIAL}) ----"

  combined_prefix="${prefix}_${TRIAL}"
  src_dir="${input_src_root}/${prefix}"
  dest_dir="${namd_root}/${combined_prefix}"

  mkdir -p "${dest_dir}/mini"

  copy_required "${src_dir}/${combined_prefix}_pbc.txt"                        "${dest_dir}/${combined_prefix}_pbc.txt"                             || { echo "  Skipping ${prefix} due to missing files."; echo; continue; }
  copy_required "${src_dir}/${combined_prefix}_ionized.psf"                    "${dest_dir}/${combined_prefix}_ionized.psf"                         || { echo "  Skipping ${prefix} due to missing files."; echo; continue; }
  copy_required "${src_dir}/${combined_prefix}_solvated_ionized_centered.pdb"  "${dest_dir}/mini/${combined_prefix}_solvated_ionized_centered.pdb" || { echo "  Skipping ${prefix} due to missing files."; echo; continue; }
  copy_required "${src_dir}/${combined_prefix}_restrain.pdb"                   "${dest_dir}/mini/${combined_prefix}_restrain.pdb"                   || { echo "  Skipping ${prefix} due to missing files."; echo; continue; }

  cp -f "$run_gen_namd" "${dest_dir}/"
  (
    cd "${dest_dir}"
    chmod +x run_gen_namd.sh
    ./run_gen_namd.sh "${script_dir}" "${prefix}" "${TRIAL}"

    for f in *.sh; do
      [[ -f "$f" ]] || continue
      first="$(head -n1 "$f")"
      if [[ "$first" != "#!"* ]]; then
        printf '#!/bin/bash\n%s\n' "$(cat "$f")" > "$f"
      fi
      inject_slurm_headers "$f" "${SLURM_PARTITION_VAL}" "${SLURM_ACCOUNT_VAL}"
    done

    rm -f run_gen_namd.sh
  )

  echo "  [✓] Generated NAMD job files in ${dest_dir}"
  echo
done

echo "All done."