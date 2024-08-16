# Maho400E-LinuxCNC (WIP!)
LinuxCNC Maho400E configuration (EtherCAT IO)

## Slaves
0. Beckhoff [EK1100]() EtherCAT Coupler
1. Beckhoff [EM7004]() 4-axis analog input/output module
2. [Danfoss FC302]() with [MCA124 EtherCAT]() module

## Connecting the analog motor drivers and glass scales
I'm currently designing an adaptor board to reuse the factory module. The seperate project can be found [here](https://github.com/PedPEx/EM7004-Maho-Philips-432).