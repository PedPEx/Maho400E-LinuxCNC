#!/usr/bin/env python3
"""
el6002_tty_bridge.py — HAL userspace component
================================================
Bridges lcec_el6002 HAL pins ↔ pseudo-terminal (PTY) so any application
that expects /dev/tty can talk to the EL6002 as if it were a real port.

Usage in your HAL file:
    loadusr -Wn el6002_tty python3 /path/to/el6002_tty_bridge.py --channel 0

Then connect HAL pins (example: master m0, slave D9, channel 0):
    net el6002-tx-len   lcec.m0.D9.ch0.tx-len   => el6002_tty_ch0.tx-len
    net el6002-tx-d0    lcec.m0.D9.ch0.tx-data-0 => el6002_tty_ch0.tx-data-0
    net el6002-tx-d1    lcec.m0.D9.ch0.tx-data-1 => el6002_tty_ch0.tx-data-1
    net el6002-tx-d2    lcec.m0.D9.ch0.tx-data-2 => el6002_tty_ch0.tx-data-2
    net el6002-tx-d3    lcec.m0.D9.ch0.tx-data-3 => el6002_tty_ch0.tx-data-3
    net el6002-tx-d4    lcec.m0.D9.ch0.tx-data-4 => el6002_tty_ch0.tx-data-4
    net el6002-tx-d5    lcec.m0.D9.ch0.tx-data-5 => el6002_tty_ch0.tx-data-5
    net el6002-tx-busy  lcec.m0.D9.ch0.tx-busy   => el6002_tty_ch0.tx-busy
    net el6002-rx-len   lcec.m0.D9.ch0.rx-len    => el6002_tty_ch0.rx-len
    net el6002-rx-d0    lcec.m0.D9.ch0.rx-data-0 => el6002_tty_ch0.rx-data-0
    net el6002-rx-d1    lcec.m0.D9.ch0.rx-data-1 => el6002_tty_ch0.rx-data-1
    net el6002-rx-d2    lcec.m0.D9.ch0.rx-data-2 => el6002_tty_ch0.rx-data-2
    net el6002-rx-d3    lcec.m0.D9.ch0.rx-data-3 => el6002_tty_ch0.rx-data-3
    net el6002-rx-d4    lcec.m0.D9.ch0.rx-data-4 => el6002_tty_ch0.rx-data-4
    net el6002-rx-d5    lcec.m0.D9.ch0.rx-data-5 => el6002_tty_ch0.rx-data-5
    net el6002-rx-rdy   lcec.m0.D9.ch0.rx-ready  => el6002_tty_ch0.rx-ready

The bridge creates a symlink:  /dev/ttyEL6002ch0 → /dev/pts/X
Point your application at /dev/ttyEL6002ch0.

NOTE: This is a non-realtime userspace component (~1 kHz poll).
      Suitable for low-baud-rate protocols (Modbus RTU, custom ASCII, …).
      Not suitable for high-speed streaming.
"""

import hal
import os
import pty
import select
import argparse
import signal
import sys

MAX_DATA   = 22
DATA_PINS  = 6
POLL_S     = 0.001   # 1 ms


def create_hal_component(channel: int) -> hal.component:
    h = hal.component(f"el6002_tty_ch{channel}")

    # TX — we output these to the lcec driver
    h.newpin("tx-len",  hal.HAL_U32, hal.HAL_OUT)
    h.newpin("tx-busy", hal.HAL_BIT, hal.HAL_IN)
    for i in range(DATA_PINS):
        h.newpin(f"tx-data-{i}", hal.HAL_U32, hal.HAL_OUT)

    # RX — we read these from the lcec driver
    h.newpin("rx-len",   hal.HAL_U32, hal.HAL_IN)
    h.newpin("rx-ready", hal.HAL_BIT, hal.HAL_IN)
    for i in range(DATA_PINS):
        h.newpin(f"rx-data-{i}", hal.HAL_U32, hal.HAL_IN)

    h.ready()
    return h


def pack_bytes(data: bytes, h: hal.component) -> None:
    """Write up to MAX_DATA bytes into tx-data-0..5 (little-endian u32)."""
    words = [0] * DATA_PINS
    for i, b in enumerate(data[:MAX_DATA]):
        words[i // 4] |= b << ((i % 4) * 8)
    for i, w in enumerate(words):
        h[f"tx-data-{i}"] = w


def unpack_bytes(h: hal.component, length: int) -> bytes:
    """Read `length` bytes from rx-data-0..5 (little-endian u32)."""
    out = []
    for i in range(min(length, MAX_DATA)):
        word = h[f"rx-data-{i // 4}"]
        out.append((word >> ((i % 4) * 8)) & 0xFF)
    return bytes(out)


def run(channel: int) -> None:
    h = create_hal_component(channel)

    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    symlink = f"/dev/ttyEL6002ch{channel}"

    try:
        if os.path.islink(symlink):
            os.unlink(symlink)
        os.symlink(slave_name, symlink)
        print(f"[el6002_tty] ch{channel}: {slave_name} → {symlink}", flush=True)
    except PermissionError:
        print(f"[el6002_tty] WARNING: cannot create {symlink} "
              f"(run as root or add udev rule). Raw PTY: {slave_name}", flush=True)

    # Initialise TX pins
    h["tx-len"] = 0
    for i in range(DATA_PINS):
        h[f"tx-data-{i}"] = 0

    last_rx_ready = bool(h["rx-ready"])
    tx_pending = b""

    def cleanup(*_):
        try:
            os.unlink(symlink)
        except OSError:
            pass
        os.close(master_fd)
        os.close(slave_fd)
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT,  cleanup)

    while True:
        # ── Check for bytes from the application via PTY ──────────────────
        r, _, _ = select.select([master_fd], [], [], POLL_S)
        if r:
            try:
                chunk = os.read(master_fd, MAX_DATA)
                if chunk:
                    tx_pending += chunk
            except OSError:
                pass

        # ── Push pending TX bytes if channel is free ──────────────────────
        if tx_pending and not h["tx-busy"]:
            chunk       = tx_pending[:MAX_DATA]
            tx_pending  = tx_pending[MAX_DATA:]
            pack_bytes(chunk, h)
            h["tx-len"] = len(chunk)
        elif not tx_pending:
            h["tx-len"] = 0

        # ── Check for new RX data from the serial port ────────────────────
        current_rdy = bool(h["rx-ready"])
        if current_rdy != last_rx_ready:
            last_rx_ready = current_rdy
            length = int(h["rx-len"])
            if length > 0:
                data = unpack_bytes(h, length)
                try:
                    os.write(master_fd, data)
                except OSError:
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EL6002 ↔ PTY bridge")
    parser.add_argument("--channel", type=int, default=0,
                        choices=[0, 1], help="EL6002 channel (0 or 1)")
    args = parser.parse_args()
    run(args.channel)
