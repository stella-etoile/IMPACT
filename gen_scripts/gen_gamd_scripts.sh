#!/bin/bash

# Usage: ./gen_namd_scripts.sh <prefix> <text_chunk_file>
# Example: ./gen_namd_scripts.sh TCR_08 text_chunk.txt

# Base directory names:
# Example:
#GEN_SCRIPTS_DIR="/scratch/midway3/lwu12/TCR_Project/TCR-complex/gen_scripts"
#PARAM_DIR="/scratch/midway3/lwu12/TCR_Project/TCR-complex/param"
GEN_SCRIPTS_DIR="$(pwd)/../../../IMPACT/gen_scripts/gamd"
PARAM_DIR="$(pwd)/../../../IMPACT/param"

# Parameters
PREFIX=$1
TEXT_CHUNK_FILE=$2

# Check if the text chunk file exists
if [ ! -f "$TEXT_CHUNK_FILE" ]; then
  echo "Error: Text chunk file '$TEXT_CHUNK_FILE' not found!"
  exit 1
fi

# Create directory
mkdir -p gamd

for f in "$GEN_SCRIPTS_DIR"/*.conf; do
	[ -e "$f" ] || continue
	NEW_CONFIG_FILE="gamd/${PREFIX}-$(basename "$f")"

	# Copy and modify the configuration file
	cp "$f" "$NEW_CONFIG_FILE"
	
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
	
	echo "Processed $f into $NEW_CONFIG_FILE"
done

for f in "$GEN_SCRIPTS_DIR"/*.sh; do
  [ -e "$f" ] || continue  
  NEW_JOB_SUBMIT_FILE="gamd/${PREFIX}-$(basename "$f")"

  cp "$f" "$NEW_JOB_SUBMIT_FILE"

  # Replace placeholders
  sed -i "	s|TCR_##|$PREFIX|g; 
			s|CONF_FILE|${PREFIX}-$(basename "$f" .sh).conf|g" "$NEW_JOB_SUBMIT_FILE"

  echo "Processed $f into $NEW_JOB_SUBMIT_FILE"
done









