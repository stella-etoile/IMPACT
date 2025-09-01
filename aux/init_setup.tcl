# inputs output dir
set cur_dir [lindex $argv 0]
set gen_sys_dir [lindex $argv 1]
set index [lindex $argv 2]
set trial_num [lindex $argv 3]

cd ${cur_dir}

set pdb_file "${cur_dir}/${index}.pdb"

mol new $pdb_file
source "$gen_sys_dir"
gen_system 0 "${index}_${trial_num}"
quit

