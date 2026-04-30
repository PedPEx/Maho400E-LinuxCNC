# lcec_danfoss_fc302 – Driver Reference

Driver for the **Danfoss FC302 VFD** with **MCA124 EtherCAT option card** in
[linuxcnc-ethercat](https://github.com/linuxcnc-ethercat/linuxcnc-ethercat).

---

## Table of Contents

1. [Hardware Overview](#1-hardware-overview)
2. [Prerequisites](#2-prerequisites)
3. [ethercat-conf.xml Setup](#3-ethercat-confxml-setup)
4. [HAL Pins](#4-hal-pins)
5. [modParams Reference](#5-modparams-reference)
6. [CiA 402 State Machine](#6-cia-402-state-machine)
7. [Statusword Decoder](#7-statusword-decoder)
8. [Infos-RO SDO Monitoring](#8-infos-ro-sdo-monitoring)
10. [FC302 Front Panel Prerequisites](#9-fc302-front-panel-prerequisites)
11. [Known Limitations & Quirks](#10-known-limitations--quirks)
12. [Troubleshooting](#11-troubleshooting)

---

## 1. Hardware Overview

| Item | Value |
|---|---|
| VendorID | `0x0200008D` |
| ProductCode | `0x00000064` |
| EtherCAT option card | MCA124 |
| CiA 402 profile | VL (velocity) mode (Danfoss offers two additional vendor specific modes) |
| Distributed Clocks | **Not supported** – never add `<dcConf>` |
| EoE | Can be **disabled** in IgH master build (`disable-eoe=yes`) |

### PDO Map

The MCA124 has a **completely fixed, non-configurable PDO layout**.
The IgH master cannot assign additional PDO container indices – any attempt
returns SDO abort `0x06020000 "Object does not exist"`. It just offers plenty of Danfoss own parameters to be read via read-only PDOs by the master.

**SM2 – RxPDO `0x1616` (master → drive):**

| Object | Type | Description |
|---|---|---|
| `0x6040:00` | u16 | ControlWord |
| `0x6042:00` | s16 | Target VL (velocity setpoint) |

**SM3 – TxPDO `0x1A16` (drive → master):**

| Object | Type | Description |
|---|---|---|
| `0x6041:00` | u16 | StatusWord |
| `0x6044:00` | s16 | Actual VL |
| `0x2651:00` | s16 | Speed [RPM] |
| `0x2679:00` | s16 | Feedback [RPM] |
| `0x264A:00` | s16 | Power [kW × 0.01] |
| `0x2650:00` | s16 | Torque [Nm] |
| `0x2655:00` | s16 | Torque [% High Res × 0.1] |
| `0x2661:00` | s16 | Brake Energy Average |
| `0x265E:00` | u16 | DC Link Voltage [V] |
| `0x2667:00`* | u16 | Temperature slot (configurable) |

\* The last slot carries a temperature value whose source is set by FC302 par. 12-22.9
and declared to the driver via the `tempSlotSource` modParam. The value in the modParam is also written to the drive, so no drive configuration is required fot the PDOs, all other motor data has to be configured on the drive itself.

---

## 2. Prerequisites

### linuxcnc-ethercat

Copy file to this location `src/devices/lcec_fc302.c`, then:

```bash
cd ~/src/linuxcnc-ethercat/src
make
sudo make install
```

---

## 3. ethercat-conf.xml Setup

```xml
<masters>
  <master idx="0" appTimePeriod="1000000" refClockSyncCycles="1" name="m0">

    <!-- FC302 must be slave idx="0" -->
    <slave idx="0" type="FC302" name="FC302">

      <!-- ── Velocity ramps (CiA 402) ──────────────────────────────── -->
      <!-- accel = accelDeltaSpeed / accelDeltaTime  [vel-unit / time-unit] -->
      <modParam name="accelDeltaSpeed"   value="5000"/>   <!-- 50.00 Hz span -->
      <modParam name="accelDeltaTime"    value="2000"/>   <!-- 2.000 s       -->
      <modParam name="decelDeltaSpeed"   value="5000"/>
      <modParam name="decelDeltaTime"    value="2000"/>

      <!-- ── VL dimension factor ───────────────────────────────────── -->
      <!-- v_physical = v_raw * vlDimNumerator / vlDimDenominator       -->
      <!-- Default (1/1): 0.01 Hz/digit  →  5000 = 50.00 Hz            -->
      <!-- RPM mode (60/1): 1 RPM/digit  →  3000 = 3000 RPM (2-pole)   -->
      <modParam name="vlDimNumerator"    value="1"/>
      <modParam name="vlDimDenominator"  value="1"/>

      <!-- ── FC302-specific ramp times (par. group 3) ──────────────── -->
      <modParam name="ramp1Up"           value="2000"/>   <!-- par. 3-41 -->
      <modParam name="ramp1Down"         value="2000"/>   <!-- par. 3-42 -->
      <modParam name="ramp2Up"           value="500"/>    <!-- par. 3-51 -->
      <modParam name="ramp2Down"         value="500"/>    <!-- par. 3-52 -->
      <modParam name="jogRampTime"       value="1000"/>   <!-- par. 3-80 -->
      <modParam name="qstopRampTime"     value="200"/>    <!-- par. 3-81 -->

      <!-- ── Bus jog speeds ────────────────────────────────────────── -->
      <modParam name="busJog1Speed"      value="500"/>    <!-- par. 8-90 -->
      <modParam name="busJog2Speed"      value="1000"/>   <!-- par. 8-91 -->

      <!-- ── Digital & Relay bus control (par. 5-90) ───────────────── -->
      <!-- Bit 0=T27, Bit 1=T29, Bit 2=X30/6, Bit 3=X30/7             -->
      <!-- Bit 4=Relay 1, Bit 5=Relay 2                                 -->
      <!-- Requires par. 5-01/5-02 = [13] Bus Control                  -->
      <modParam name="digitalRelayCtrl"  value="0"/>

      <!-- ── Temperature slot (last TxPDO entry) ───────────────────── -->
      <!-- Pass the FC302 par. 12-22.9 readout number (16xx)           -->
      <!-- 1618=motor-thermal  1619=kty  1634=heatsink                 -->
      <!-- 1635=inv-thermal    1639=ctrl-card (DEFAULT)                 -->
      <modParam name="tempSlotSource"    value="1639"/>

      <!-- ── Infos-RO SDO monitoring (acyclic, bitmask) ────────────── -->
      <!-- Bit 0=motor-thermal-pct  Bit 1=kty-temperature              -->
      <!-- Bit 2=heatsink-temp      Bit 3=inverter-thermal-pct         -->
      <!-- Bit 4=kwh-counter        Bit 5=operating-hours              -->
      <!-- Bit 6=running-hours                                          -->
      <!-- 0=disabled (default)   127=all 7 channels                  -->
      <modParam name="sdoReadConfig"     value="0"/>

    </slave>

    <!-- Additional slaves -->
    <slave idx="1" type="EK1101" name="coupler"/>
    <!-- ... -->

  </master>
</masters>
```

> **Note:** Speed limits (`vlMinimum` / `vlMaximum`) are **not writable via SDO**
> on this firmware (abort `0x08000020`). Set them on the FC302 front panel:
> **P4-11** (Motor Speed Low Limit) and **P4-12** (Motor Speed High Limit).

---

## 4. HAL Pins

All pins appear under `lcec.m0.FC302.*` (master name `m0`, slave name `FC302`
as defined in `ethercat-conf.xml`).

### 4.1 CiA 402 Control / Status

| Pin | Type | Dir | Description |
|---|---|---|---|
| `srv-cia-controlword` | u32 | IN | CiA 402 ControlWord |
| `srv-cia-statusword` | u32 | OUT | CiA 402 StatusWord |
| `srv-target-vl` | s32 | IN | Velocity setpoint (unit: see vlDimFactor) |
| `srv-actual-vl` | s32 | OUT | Actual velocity feedback |
| `modes-op-display` | u32 | OUT | Modes of operation display (0x6061) |
| `slave-online` | bit | OUT | TRUE when slave is reachable |
| `slave-oper` | bit | OUT | TRUE when slave is in OP state |
| `slave-state-op` | bit | OUT | TRUE when EtherCAT state = OP |

### 4.2 Infos-RO-PDO (cyclic, every servo cycle)

| Pin | Type | Dir | Object | Unit |
|---|---|---|---|---|
| `Infos-RO-PDO.speed-rpm` | s32 | OUT | `0x2651` | RPM |
| `Infos-RO-PDO.feedback-rpm` | s32 | OUT | `0x2679` | RPM |
| `Infos-RO-PDO.power-kw` | s32 | OUT | `0x264A` | 0.01 kW/digit |
| `Infos-RO-PDO.torque-nm` | s32 | OUT | `0x2650` | Nm |
| `Infos-RO-PDO.torque-pct-highres` | s32 | OUT | `0x2655` | 0.1 %/digit |
| `Infos-RO-PDO.brake-energy-avg` | s32 | OUT | `0x2661` | – |
| `Infos-RO-PDO.dc-link-voltage` | u32 | OUT | `0x265E` | V |
| `Infos-RO-PDO.<temp-slot>` | s32/u32 | OUT | `tempSlotSource` | see below |

**Temperature slot pin names** (set by `tempSlotSource` modParam):

| `tempSlotSource` | Pin name | Type | Object |
|---|---|---|---|
| `1618` | `Infos-RO-PDO.motor-thermal-pct` | u32 [%] | `0x2652` |
| `1619` | `Infos-RO-PDO.kty-temperature` | s32 [°C] | `0x2653` |
| `1634` | `Infos-RO-PDO.heatsink-temp` | s32 [°C] | `0x2662` |
| `1635` | `Infos-RO-PDO.inverter-thermal-pct` | u32 [%] | `0x2663` |
| `1639` | `Infos-RO-PDO.ctrl-card-temp` | s32 [°C] | `0x2667` |

### 4.3 Infos-RO (acyclic SDO, ~2× per second when enabled)

Enabled via `sdoReadConfig` bitmask. No pins are created for disabled bits.

| Bit | Pin | Type | Object | Unit |
|---|---|---|---|---|
| 0 | `Infos-RO.motor-thermal-pct` | u32 | `0x2652` | % |
| 1 | `Infos-RO.kty-temperature` | s32 | `0x2653` | °C |
| 2 | `Infos-RO.heatsink-temp` | s32 | `0x2662` | °C |
| 3 | `Infos-RO.inverter-thermal-pct` | u32 | `0x2663` | % |
| 4 | `Infos-RO.kwh-counter` | u32 | `0x25DE` | kWh |
| 5 | `Infos-RO.operating-hours` | u32 | `0x25DC` | h |
| 6 | `Infos-RO.running-hours` | u32 | `0x25DD` | h |
| – | `Infos-RO.sdo-busy` | bit | – | TRUE while request in flight |

> The `sdo-busy` pin is only created if at least one bit is set.
> `<modParam name="sdoReadConfig" value="127"/>` enables all 7 channels.

---

## 5. modParams Reference

All parameters except `sdoReadConfig` and `tempSlotSource` are written as
**startup SDOs** during the PREOP→SAFEOP transition.

### CiA 402 Velocity Ramps

| modParam | SDO | Type | Description |
|---|---|---|---|
| `accelDeltaSpeed` | `0x6048:01` | u32 | Accel ramp numerator |
| `accelDeltaTime` | `0x6048:02` | u16 | Accel ramp denominator (max 65535) |
| `decelDeltaSpeed` | `0x6049:01` | u32 | Decel ramp numerator |
| `decelDeltaTime` | `0x6049:02` | u16 | Decel ramp denominator (max 65535) |

Ramp rate = `deltaSpeed / deltaTime` in velocity-units per time-unit.

### VL Dimension Factor

| modParam | SDO | Type | Description |
|---|---|---|---|
| `vlDimNumerator` | `0x604C:01` | s32 | Numerator (must not be 0) |
| `vlDimDenominator` | `0x604C:02` | s32 | Denominator (must not be 0) |

`v_physical = v_raw × numerator / denominator`

**Examples:**

| Numerator | Denominator | Unit of srv-target-vl |
|---|---|---|
| 1 | 1 | 0.01 Hz/digit (default) → 5000 = 50.00 Hz |
| 60 | 1 | RPM (2-pole) → 3000 = 3000 RPM |

### FC302-Specific Ramp Times (par. group 3)

| modParam | SDO | FC302 par. | Description |
|---|---|---|---|
| `ramp1Up` | `0x2155:00` | 3-41 | Ramp 1 up time |
| `ramp1Down` | `0x2156:00` | 3-42 | Ramp 1 down time |
| `ramp2Up` | `0x215F:00` | 3-51 | Ramp 2 up time |
| `ramp2Down` | `0x2160:00` | 3-52 | Ramp 2 down time |
| `jogRampTime` | `0x217C:00` | 3-80 | Jog ramp time |
| `qstopRampTime` | `0x217D:00` | 3-81 | Quick-stop ramp time |

### Bus Jog Speeds (par. group 8)

| modParam | SDO | FC302 par. | Description |
|---|---|---|---|
| `busJog1Speed` | `0x237A:00` | 8-90 | Bus jog 1 speed (u16) |
| `busJog2Speed` | `0x237B:00` | 8-91 | Bus jog 2 speed (u16) |

### Temperature Slot Source

| modParam | Type | Description |
|---|---|---|
| `tempSlotSource` | u32 | FC302 par. 12-22.9 readout number (16xx) |

Determines the PDO object index **and** HAL pin name for the last TxPDO entry:

| Value | PDO object | HAL pin | Type |
|---|---|---|---|
| `1618` | `0x2652` | `Infos-RO-PDO.motor-thermal-pct` | u32 [%] |
| `1619` | `0x2653` | `Infos-RO-PDO.kty-temperature` | s32 [°C] |
| `1634` | `0x2662` | `Infos-RO-PDO.heatsink-temp` | s32 [°C] |
| `1635` | `0x2663` | `Infos-RO-PDO.inverter-thermal-pct` | u32 [%] |
| `1639` | `0x2667` | `Infos-RO-PDO.ctrl-card-temp` | s32 [°C] ← **default** |

### SDO Read Config (Infos-RO monitoring)

| modParam | Type | Description |
|---|---|---|
| `sdoReadConfig` | u32 | Bitmask enabling Infos-RO SDO channels |

| Bit | Object | Pin suffix | Unit |
|---|---|---|---|
| 0 | `0x2652` | `motor-thermal-pct` | % |
| 1 | `0x2653` | `kty-temperature` | °C |
| 2 | `0x2662` | `heatsink-temp` | °C |
| 3 | `0x2663` | `inverter-thermal-pct` | % |
| 4 | `0x25DE` | `kwh-counter` | kWh |
| 5 | `0x25DC` | `operating-hours` | h |
| 6 | `0x25DD` | `running-hours` | h |

Common values:

```xml
value="0"    <!-- disabled (default) -->
value="15"   <!-- bits 0-3: all temperatures only -->
value="127"  <!-- 0x7F: all 7 channels -->
```

---

## 6. CiA 402 State Machine

Control the drive via `srv-cia-controlword` and monitor `srv-cia-statusword`.

### Startup Sequence (with 400V power present)

```
CW = 6   (0x06)  →  SW = 0x231  "Ready To Switch On"
CW = 7   (0x07)  →  SW = 0x233  "Switched On"
CW = 15  (0x0F)  →  SW = 0x237  "Operation Enabled"  ← motor runs
```

### Fault Reset

```
CW = 128  (0x80)  →  clears fault
CW = 0    (0x00)  →  returns to "Switch On Disabled"
```

### Quick Stop

```
CW = 2  (0x02)  →  executes quick-stop ramp, then goes to "Switch On Disabled"
```

### CiA 402 State Diagram

```
Power On
  │
  ▼
[Switch On Disabled]  ─── CW=6 ──► [Ready To Switch On]
                                            │
                                          CW=7
                                            │
                                            ▼
                                    [Switched On]
                                            │
                                          CW=15
                                            │
                                            ▼
                                   [Operation Enabled]  ◄─── motor runs
                                            │
                                        Fault!
                                            │
                                            ▼
                                       [Fault]
                                            │
                                         CW=128
                                            │
                                            ▼
                                  [Switch On Disabled]
```

---

## 7. Statusword Decoder

Common statusword values observed on FC302:

| Value (decimal) | Hex | State | Notes |
|---|---|---|---|
| 704 | `0x2C0` | Switch On Disabled | Normal power-on state |
| 689 | `0x2B1` | Ready To Switch On | Remote active ✓ |
| 177 | `0x0B1` | Ready To Switch On | **Remote NOT active** (Hand/Local mode on LCP) |
| 696 | `0x2B8` | Fault + Remote | Send CW=128 to reset |
| 136 | `0x088` | Fault + Warning, no Remote | Check LCP for error code |

### Bit Breakdown

| Bit | Meaning when 1 |
|---|---|
| 0 | Ready to Switch On |
| 1 | Switched On |
| 2 | Operation Enabled |
| 3 | **Fault active** |
| 4 | Voltage Enabled (24V logic present) |
| 5 | Quick Stop NOT active |
| 6 | Switch On Disabled |
| 7 | Warning |
| **9** | **Remote – EtherCAT controls the drive** |

> **Bit 9 = 0 (not Remote)** means the drive ignores ControlWord writes.
> Cause: drive is in Hand/Local mode on the LCP panel.
> Fix: press the **[Auto On]** key on the LCP until the display shows AUTO.

---

## 8. Infos-RO SDO Monitoring

### Mechanism

The driver uses `ecrt_slave_config_create_sdo_request()` to read objects
asynchronously (acyclic). A round-robin scheduler processes one object per
servo cycle:

```
After 5 s startup delay (allows 0x6502 mailbox response to drain):

  Object 0 → wait for response → read value → next object → ...
  Object 6 → wait for response → read value → back to object 0
```

At 1 kHz servo rate with no artificial cooldown (`FC302_MON_COOLDOWN = 0`),
the FC302 mailbox RTT (~30–50 ms) limits the rate naturally.
Each object is updated approximately **twice per second**.

### Enabling Channels

```xml
<!-- All 7 channels: -->
<modParam name="sdoReadConfig" value="127"/>

<!-- Temperatures only (bits 0-3): -->
<modParam name="sdoReadConfig" value="15"/>

<!-- Disable all (no pins created, no SDO traffic): -->
<modParam name="sdoReadConfig" value="0"/>
```

### Monitoring Without HAL (CLI)

```bash
# Motor current (s32, 0.01 A/digit)
ethercat upload -p 0 -t int32 0x264E 0x00

# Heatsink temperature
ethercat upload -p 0 -t int8 0x2662 0x00

# DC link voltage
ethercat upload -p 0 -t uint16 0x265E 0x00

# Operating hours
ethercat upload -p 0 -t uint32 0x25DC 0x00

# Live watch every 2 seconds:
watch -n 2 "ethercat upload -p 0 -t int32 0x264E 0x00"
```

---

## 9. FC302 Front Panel Prerequisites

These settings must be configured on the FC302 itself (via LCP or MCT-10)
**before** running LinuxCNC. They cannot be set via EtherCAT modParams.

| Parameter | Recommended value | Description |
|---|---|---|
| **P1-23** | Motor nameplate value | Motor frequency (Hz) |
| **P4-10** | `[0] Both directions` | Enables forward and reverse |
| **P4-11** | `0` RPM | Motor speed low limit |
| **P4-12** | e.g. `3000` RPM | Motor speed high limit |
| **P8-01** | `0` (EtherCAT control) | Control site |
| **P8-10** | `7` (CiA 402 VL) | Control Word Profile ← **set automatically** |
| **P8-5x** | `1` (Bus) | All set to *1* -> Bus is controling VFD |

> **P8-10** is automatically set to `0x0007` by the driver as a startup SDO
> (`0x232A:00 = 0x0007`). You do **not** need to set it manually.

> **Speed limits** (P4-11 / P4-12): `vlMinimum` / `vlMaximum` are **not
> writable via SDO** on this firmware (abort `0x08000020`). Always configure
> them on the front panel.

### Enabling Bus Control for Terminals 27 / 29

```
P5-01 = [13] Bus Control   ← Terminal 27 output controlled via 0x224E bit 0
P5-02 = [13] Bus Control   ← Terminal 29 output controlled via 0x224E bit 1
```

---

## 10. Known Limitations & Quirks

### Fixed PDO containers
The MCA124 only accepts `0x1616` (RxPDO) and `0x1A16` (TxPDO).
Any other container causes AL error `0x001E "Invalid input configuration"`.

### `0x6502` SDO error at startup
At every startup, two messages appear in `dmesg`:

```
EtherCAT ERROR 0-0: Received mailbox protocol 0x02 as response.
LCEC: slave m0.FC302: Failed to execute SDO upload (0x6502:0x00 ...)
```

This is **harmless**. The lcec_cia402 framework tries to read `0x6502`
(Supported Drive Modes) which the MCA124 does not support. The driver
suppresses these messages using `rtapi_set_msg_level(RTAPI_MSG_NONE)` during
the relevant init call. The `srv-supports-mode-*` pins will always read `0`.

### `0x6046:01 / 0x6046:02` not writable
VL velocity limits (`vlMinimum` / `vlMaximum`) return abort `0x08000020`
regardless of the value. Use FC302 P4-11 / P4-12 instead.

### `0x6060 / 0x6061` have no P-flag
Operating mode objects are not PDO-mappable. `enable_opmode = 0` in the driver.
`modes-op-display` is readable via acyclic SDO only (SDO bit 10, or via `0x6061`
CLI upload).

### Mailbox collision at startup
The FC302 leaves a stale `0x6502` response in its mailbox buffer after init.
The Infos-RO SDO monitoring waits **5 seconds** (`FC302_MON_STARTDELAY = 5000`
cycles at 1 kHz) before issuing the first request to allow the buffer to drain.

### No Distributed Clocks
Never add `<dcConf>` to the XML for this slave. The MCA124 does not support DC.

---

## 11. Troubleshooting

### Drive stays in PREOP E

**Cause:** `0x232A:00` (Control Word Profile) write failed, or the PDO
assignment was rejected.

**Check:**
```bash
ethercat slaves       # must show "OP +"
dmesg | grep EtherCAT | tail -20
```

**Fix:** Ensure `P8-50 = 0` and `P8-10` is not manually set to a conflicting
value. The driver sets `0x232A:00 = 0x0007` automatically.

---

### Statusword bit 9 = 0 (Not Remote)

Drive is in Hand/Local mode. Press **[Auto On]** on the LCP.

---

### Fault in statusword (bit 3 = 1)

```bash
# Send fault reset:
halcmd setp lcec.m0.FC302.srv-cia-controlword 128
halcmd setp lcec.m0.FC302.srv-cia-controlword 0

# Read error code:
ethercat upload -p 0 -t uint16 0x603F 0x00
```

---

### SM Watchdog fault (all slaves drop to SAFEOP)

**Cause:** EtherCAT datagram timeout, typically caused by SDO mailbox
collision during startup.

**Fix:** The 5-second startup delay for Infos-RO monitoring prevents this.
If it still occurs, check `dmesg` for `"wrong SDO response"` messages and
consider increasing `FC302_MON_STARTDELAY` in the driver source.

---

### "Received 4 bytes do not fit into 2 bytes"

**Cause:** A monitored SDO object has a larger native size than declared in
the monitoring table.

**Fix:** Correct the `sz` field in the `all[]` table in
`lcec_danfoss_fc302_init()` for the affected object.

---

### Working counter not reaching 24/24

Verify that all slaves are in OP:

```bash
ethercat slaves
# Should show: OP + for all slaves
```

Working counter `24/24` = all slaves contributing cyclic data.

---

*Driver developed for LinuxCNC 2.9 / linuxcnc-ethercat with IgH EtherCAT Master (EoE disabled for fewer Warnings and Errors). Tested on FC302 (Type: 135N6998; SW: A07.62 M07.61 D07.61) with MCA124 (Type: 130B5646; SW: 05.01), EtherCAT slave
position 0.12 (Master 0, Slave 12)