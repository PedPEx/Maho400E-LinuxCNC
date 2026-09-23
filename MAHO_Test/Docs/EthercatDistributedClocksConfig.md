# Distributed Clocks with IgH EtherCAT Master and lcec

Commissioning notes for the MH400E bus (17 slaves, 1 ms cycle). Covers how ESI
DC parameters map to lcec `<dcConf>`, the failure modes encountered, and how to
verify a working configuration.

## Working configuration

Master element — the application sets the DC epoch and pulls the reference
clock along every cycle:

```xml
<master idx="0" appTimePeriod="1000000" refClockSyncCycles="1" refClockSlaveIdx="2" name="m0">
```

Per-slave DC configuration:

| Slave | Terminal | `<dcConf>` |
|---|---|---|
| 2 | EL5002 | `assignActivate="700" sync0Cycle="*1" sync0Shift="0" sync1Cycle="15000" sync1Shift="0"` |
| 3, 4, 5 | EL5021 | `assignActivate="700" sync0Cycle="*1" sync0Shift="-65000" sync1Cycle="25000" sync1Shift="0"` |
| 12 | EL4034 | `assignActivate="700" sync0Cycle="*1" sync0Shift="0" sync1Cycle="100000" sync1Shift="0"` |

The EL5021 `sync0Shift` deviates from the ESI value (-30600) on purpose; see
"SYNC0 margin" below.

## Mapping ESI `<OpMode>` to lcec `<dcConf>`

This is the part that costs the most time. Beckhoff ESI files describe DC
timing like this (EL5021, `OpMode Name="DC"`):

```xml
<AssignActivate>#x700</AssignActivate>
<CycleTimeSync0 Factor="1">0</CycleTimeSync0>
<ShiftTimeSync0 Input="0">-30600</ShiftTimeSync0>
<CycleTimeSync1 Factor="1">0</CycleTimeSync1>
<ShiftTimeSync1>25000</ShiftTimeSync1>
```

The translation is:

| ESI element | lcec attribute |
|---|---|
| `AssignActivate` | `assignActivate` (without the `#x`) |
| `CycleTimeSync0 Factor="n"` | `sync0Cycle="*n"` (n × `appTimePeriod`) |
| `ShiftTimeSync0` | `sync0Shift` |
| **`ShiftTimeSync1`** | **`sync1Cycle`** |
| — | `sync1Shift` stays `0` |

`CycleTimeSync1 Factor="1"` only means "SYNC1 fires once per SYNC0 cycle". The
actual offset lives in `ShiftTimeSync1`, and that value has to be passed as
`sync1Cycle`, because IgH writes `sync1Cycle` verbatim into ESC register 0x09A4
and the ESC interprets that register as the delay from SYNC0 to SYNC1.
`sync1Shift` is not added to it and has no effect on the register.

Consequence: `sync1Cycle="*1"` writes 1 000 000 ns, which makes SYNC1 coincide
with the next SYNC0. An input terminal then never gets its data-ready trigger
in time and refuses OP with AL status 0x002C ("Fatal Sync Error"). This was the
original failure — the SYNC1 offset never reached the terminal.

## Reference clock

`ethercat slaves -v | grep -E "^=== |Distributed clocks|transmission delay"`

Only a slave reporting `Distributed clocks: yes, 64 bit` can serve as reference
clock. On this bus:

- Slaves 0, 1, 6, 10, 13 (EK1914, EL1918, EL9410, 2× EL9110): `delay measurement only`
  — port timestamps for propagation delay, but no system time unit.
- Slave 2 (EL5002): first slave with a full 64-bit DC clock → reference clock.
- Slave 16 (FC302/MCA124): no DC at all, stays SM-synchronous.

The reference clock must be the first DC-capable slave in frame direction,
because `ecrt_master_sync_slave_clocks()` uses an FRMW datagram that reads the
time at the reference slave and writes it into all following slaves.

The transmission delays in `ethercat slaves -v` are counted relative to the
reference clock: slave 2 = 0 ns, then ~145 ns per terminal down the E-bus.

## Verification

```bash
# Activation register: 0x07 on every slave with an active <dcConf>
ethercat reg_read -m 0 -p <n> -t uint8 0x0981

# System time difference to the reference clock
# (bit 31 = sign, bits 0..30 = |difference| in ns)
ethercat reg_read -m 0 -p <n> -t uint32 0x092C

# SYNC1 delay after SYNC0 as actually written
ethercat reg_read -m 0 -p <n> -t uint32 0x09A4

# Configured SYNC0 start time (static, useful to compare phase across slaves)
ethercat reg_read -m 0 -p <n> -t uint64 0x0990

# Master side
ethercat config -v -p <n> | grep -A4 "DC configuration"
```

Achieved on this bus: 2–8 ns system time difference on slaves 2–5.

CoE sync diagnostics per slave (`1C32` = output SM, `1C33` = input SM):

| Subindex | Meaning |
|---|---|
| `:01` | Sync mode — 2 = DC/SYNC0, 3 = DC/SYNC1, 0x22 = SM-synchronous (fallback) |
| `:0B` | SM event missed counter |
| `:0C` | Cycle exceeded counter |
| `:20` | Sync error (reflects the last cycle, not latched) |

Expected result: EL5021 and EL5002 in mode 3, EL4034 in mode 2 (an output
terminal applies its values on SYNC0 and uses SYNC1 only internally), `:0C` at
0 everywhere.

## SYNC0 margin

The ESI value `sync0Shift="-30600"` combined with SYNC1 at +25 µs puts the
data-ready point only ~5.6 µs ahead of the nominal cycle start. Beckhoff sizes
this for TwinCAT, where the frame leaves very close to the cycle start; under
LinuxCNC the actual send time varies with thread wakeup latency and with where
`lcec.write-all` sits in the servo thread.

Symptom of too little margin: one arbitrary EL5021 accumulates `1C33:0B` at
roughly 170 events/s (~17 % of cycles) while its neighbours stay in single
digits. Which terminal is hit is decided at startup and changes across reboots,
which rules out the terminal, the scale and the cable.

`sync0Shift="-65000"` puts the data-ready point 40 µs ahead of the cycle start
and removes the effect; verified stable over several reboots. `-100000` (75 µs)
also works if more reserve is ever needed. Size the margin against the servo
thread's worst-case wakeup latency from `latency-test`, not against
`servo-thread.tmax`, which measures execution time rather than latency.

The dead time costs nothing measurable: 65 µs at 3 m/min rapid is ~3 µm of
measurement lag, identical on all three axes, so it adds to following error but
not to contour error. Constant latency is not jitter.

## Diagnostics perturb the measurement

Every `ethercat` CLI call against a master in OP injects an external request
into the cyclic operation and costs one cycle. Two visible effects:

- Each call produces one `Failed to get reference clock time: Input/output
  error` in the LinuxCNC machine log (`ecrt_master_reference_clock_time()`
  returns EIO because that cycle's sync datagram was not received).
- Every DC slave increments its `1C3x:0B` counter once per disturbed cycle.

The fingerprint is unmistakable: inside a single polling loop the counters rise
monotonically in the order the slaves were read.

So single-digit counter values after a polling loop are an artefact of the
measurement, not a bus problem. For continuous monitoring use the HAL pins
instead, which cost nothing: `lcec.m0.<slave>.enc.sync-error`,
`.enc.txpdo-state`, `.enc.amplitude-error`, `.enc.frequency-error`. Avoid
`ethercat` CLI calls while machining.

## Unrelated messages seen during startup

- `0-12: SDO upload 0x1C13:01 aborted / Subindex does not exist` — EL4034 has
  no input PDO assignment; scan-time only, harmless.
- `0-16: Received unknown response while uploading SDO 0x1C12:00` — known
  stale-mailbox behaviour of the FC302/MCA124 during bus scan; the slave
  reaches OP afterwards.
- `0-2: Slave does not support changing the PDO mapping` — the EL5002 maps its
  9-bit gap as `0x0000:00/9`, while `lcec_el5002.c` declares `0x0010:00/9`.
  Same bit width, so the process image is correct; cosmetic only. Fix by
  changing the gap entry in the driver to `0x0000`.