# inputs prefix parameter
set prefix [lindex $argv 0]

set mini_dir "./${prefix}/mini/"
cd ./$mini_dir

set psf_file "../${prefix}_ionized.psf"
set dcd_file "${prefix}-mini.dcd"
set output_file "${prefix}-mini-LF.pdb"

mol new $psf_file
mol addfile $dcd_file waitfor all
animate write pdb $output_file beg 99 end 99
quit

