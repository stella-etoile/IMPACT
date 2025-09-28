#!/bin/bash

# Usage: ./gen_namd_scripts.sh <prefix> <text_chunk_file>
# Example: ./gen_namd_scripts.sh TCR_08 text_chunk.txt

# Base directory names:
# Example:
#GEN_SCRIPTS_DIR="/scratch/midway3/lwu12/TCR_Project/TCR-complex/gen_scripts"
#PARAM_DIR="/scratch/midway3/lwu12/TCR_Project/TCR-complex/param"
GEN_SCRIPTS_DIR="../../gen_scripts/namd"
PARAM_DIR="../../../param"

# Parameters
PREFIX=$1
TEXT_CHUNK_FILE=$2

# Check if the text chunk file exists
if [ ! -f "$TEXT_CHUNK_FILE" ]; then
  echo "Error: Text chunk file '$TEXT_CHUNK_FILE' not found!"
  exit 1
fi

# Create directories
mkdir -p mini equil NPT1 NPT2

# Define the configuration files and corresponding job submission scripts
declare -A FILES
FILES[mini]="$GEN_SCRIPTS_DIR/mini.conf"
FILES[equil]="$GEN_SCRIPTS_DIR/heatup-equil.conf"
FILES[NPT1]="$GEN_SCRIPTS_DIR/npt1.conf"
FILES[NPT2]="$GEN_SCRIPTS_DIR/npt2.conf"

declare -A JOB_SUBMIT_FILES
JOB_SUBMIT_FILES[mini]="$GEN_SCRIPTS_DIR/mini.sh"
JOB_SUBMIT_FILES[equil]="$GEN_SCRIPTS_DIR/equil.sh"
JOB_SUBMIT_FILES[NPT1]="$GEN_SCRIPTS_DIR/NPT1.sh"
JOB_SUBMIT_FILES[NPT2]="$GEN_SCRIPTS_DIR/NPT2.sh"

# Process each directory
for DIR in mini equil NPT1 NPT2; do
  CONFIG_FILE=${FILES[$DIR]}
  JOB_SUBMIT_FILE=${JOB_SUBMIT_FILES[$DIR]}

  # Check if the configuration file exists
  if [ -f "$CONFIG_FILE" ]; then
    # New file name with the specified prefix
    NEW_CONFIG_FILE="$DIR/${PREFIX}-$(basename $CONFIG_FILE)"

    # Copy and modify the configuration file
    cp "$CONFIG_FILE" "$NEW_CONFIG_FILE"
    
    # Modify the configuration file to insert the text chunk and replace "TCR_##"
    awk -v prefix="$PREFIX" -v text_chunk_file="$TEXT_CHUNK_FILE" '
    {
      if ($0 ~ /Periodic boundary Conditions/) {
        print $0;
        while ((getline line < text_chunk_file) > 0) {
          print line;
        }
        next;
      }
      gsub(/TCR_##/, prefix);
      print $0;
    }' "$NEW_CONFIG_FILE" > temp && mv temp "$NEW_CONFIG_FILE"
    
    # Replace ../../param with the absolute path to the param directory
    sed -i "s|../../param|$PARAM_DIR|g" "$NEW_CONFIG_FILE"

    echo "Processed $CONFIG_FILE into $NEW_CONFIG_FILE"
  else
    echo "Configuration file '$CONFIG_FILE' not found, skipping..."
  fi

  # Check if the job submission file exists
  if [ -f "$JOB_SUBMIT_FILE" ]; then
    # New job submission file name
    NEW_JOB_SUBMIT_FILE="$DIR/${PREFIX}-$(basename $JOB_SUBMIT_FILE)"

    # Copy and modify the job submission file
    cp "$JOB_SUBMIT_FILE" "$NEW_JOB_SUBMIT_FILE"
    
    # Modify the job submission file to replace placeholders with the prefix and config file name
    sed -i "s|TCR_##|$PREFIX|g; s|CONF_FILE|${PREFIX}-$(basename $CONFIG_FILE)|g" "$NEW_JOB_SUBMIT_FILE"
    
    echo "Processed $JOB_SUBMIT_FILE into $NEW_JOB_SUBMIT_FILE"
  else
    echo "Job submission file '$JOB_SUBMIT_FILE' not found, skipping..."
  fi
done
