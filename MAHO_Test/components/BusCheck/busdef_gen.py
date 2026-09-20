#!/usr/bin/env python3
#
#    busdef_gen - snapshot the currently attached EtherCAT bus into a
#    bus-definition file (the "expected" bus) for buscheck.
#
#    Usage:
#      ./busdef_gen.py > busdef.json        # master 0
#      ./busdef_gen.py -m 1 > busdef.json   # another master
#
#    Reads `ethercat slaves -v`, which lists position, AL state and the
#    Identity (vendor id / product code / revision) for EVERY slave, including
#    couplers and supply terminals that carry no process data. Writes a JSON
#    list in bus order. Review the result once: mark slaves that may
#    legitimately be absent with "optional": true, and set "revision": null on
#    any slave whose revision you do NOT want checked (vendor+product are
#    always checked).
#
#    NON-SAFE: diagnostics only.

import re
import sys
import json
import argparse
import subprocess

RE_POS = re.compile(r"===\s*Master\s+\d+,\s*Slave\s+(\d+)\s*===")
RE_STATE = re.compile(r"^\s*State:\s*(\S+)", re.I)
RE_VID = re.compile(r"Vendor Id:\s*(0x[0-9a-fA-F]+)", re.I)
RE_PID = re.compile(r"Product code:\s*(0x[0-9a-fA-F]+)", re.I)
RE_REV = re.compile(r"Revision number:\s*(0x[0-9a-fA-F]+)", re.I)
RE_NAME = re.compile(r"Device name:\s*(.*?)\s*$", re.I)


def norm(v):
    try:
        return hex(int(str(v), 0))
    except (ValueError, TypeError):
        return None


def read_bus(ecat, m):
    out = subprocess.check_output([ecat, "slaves", "-v", "-m", str(m)], timeout=10)
    txt = out.decode("utf-8", errors="replace")

    slaves = {}
    cur = None
    for line in txt.splitlines():
        mo = RE_POS.search(line)
        if mo:
            cur = int(mo.group(1))
            slaves[cur] = {"position": cur, "name": "", "vendor": None,
                           "product": None, "revision": None, "state": "?"}
            continue
        if cur is None:
            continue
        s = slaves[cur]
        mo = RE_STATE.match(line)
        if mo:
            s["state"] = mo.group(1)
            continue
        for rx, key in ((RE_VID, "vendor"), (RE_PID, "product"), (RE_REV, "revision")):
            mo = rx.search(line)
            if mo:
                s[key] = norm(mo.group(1))
        mo = RE_NAME.search(line)
        if mo and not s["name"]:
            s["name"] = mo.group(1)
    return slaves


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--master", type=int, default=0)
    ap.add_argument("-e", "--ethercat", default="ethercat")
    args = ap.parse_args()

    bus = read_bus(args.ethercat, args.master)
    slaves = []
    for pos in sorted(bus):
        b = bus[pos]
        slaves.append({
            "position": pos,
            "name": b["name"] or ("Slave %d" % pos),
            "vendor": b["vendor"],
            "product": b["product"],
            "revision": b["revision"],   # set to null to skip revision check
            "optional": False,           # true = absence is only an info
        })

    json.dump({"master": args.master, "slaves": slaves}, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
