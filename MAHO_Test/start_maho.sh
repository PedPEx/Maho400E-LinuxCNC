#!/bin/bash

# Checks the output of "ethercat slaves".
# Searches for a line that begins with (optional spaces and) the number 13 
# and contains the string "IHSV57/60-EC".
if ethercat slaves | grep -qE '^[[:space:]]*13[[:space:]].*IHSV57/60-EC'; then
    echo "Slave 13 (IHSV57/60-EC) found. Starting 4-axis configuration..."
    /usr/bin/linuxcnc /home/cnc/linuxcnc/configs/Maho400E-LinuxCNC/MAHO_Test/Maho_4_axes.ini
else
    echo "Slave 13 not found. Starting 3-axis configuration..."
    /usr/bin/linuxcnc /home/cnc/linuxcnc/configs/Maho400E-LinuxCNC/MAHO_Test/Maho_3_axes.ini
fi