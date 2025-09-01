#!/bin/bash

# Usage: ./run_gen_namd.sh <script_dir> <prefix> <trial_num>

# Arguments
script_dir=$1
prefix=$2
trial_num=$3

# Derived values
full_prefix="${prefix}_${trial_num}"
pbc_file="${full_prefix}_pbc.txt"

# Run the command
"${script_dir}/gen_namd_scripts.sh" "$full_prefix" "$pbc_file"
