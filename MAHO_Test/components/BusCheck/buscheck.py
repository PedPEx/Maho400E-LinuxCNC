#
#    buscheck - EtherCAT bus supervision for LinuxCNC.
#
#    Compares the live bus against an expected bus definition (busdef.json)
#    and reports, automatically for every configured slave:
#      * missing slave / wrong Device-ID  -> error   (root cause only)
#      * configured slave not in OP        -> warning (with its AL state)
#      * more slaves present than defined   -> info
#
#    Cascade handling: the ID sequence is compared in bus order and the check
#    stops at the first deviation, because a physically absent slave shifts the
#    ring positions of everything behind it. So one root message is raised, not
#    a flood of follow-on errors. A completely dead bus yields a single message.
#    Slaves marked "optional" in busdef.json may be absent (info, not error).
#
#    Outputs, all at once:
#      * a GladeVCP overview tab (one row per configured slave, colour-coded)
#      * HAL summary pins (below)
#      * "ok"-style pins meant to feed faultlatch.monitor inputs, so the same
#        conditions also appear in the operator Stoermeldungen queue.
#
#    Embed via the machine INI:
#      [DISPLAY]
#      EMBED_TAB_NAME = Bus
#      EMBED_TAB_COMMAND = gladevcp -c buscheck -x {XID}
#          -u components/buscheck/buscheck.py
#          -H components/buscheck/buscheck.hal
#          -U cfg=components/buscheck/busdef.json
#          components/buscheck/buscheck.ui
#
#    HAL pins (all HAL_OUT bit unless noted):
#      buscheck.ok               all configured slaves present, correct ID, in OP
#      buscheck.bus-alive        at least one slave answers            (ok-style)
#      buscheck.slaves-complete  no required slave missing/wrong-ID    (ok-style)
#      buscheck.all-op           every configured, reachable slave in OP (ok-style)
#      buscheck.bus-dead         no slave answers at all
#      buscheck.missing          a required slave is missing / wrong ID
#      buscheck.wrong-id         a present slave has the wrong Device-ID
#      buscheck.not-op           a configured slave is not in OP
#      buscheck.extra            more slaves present than configured
#      buscheck.checked          u32, number of configured slaves verified
#
#    NON-SAFE: diagnostics/HMI only; never a protective function.

import os
import re
import json
import subprocess

import hal
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

POLL_MS = 1500

COLOR_OK = "#2e7d32"       # green
COLOR_WARN = "#e3f707"     # yellow  (matches the Stoermeldungen palette)
COLOR_ERR = "#f74307"      # orange-red
COLOR_SUPPRESSED = "#808080"  # grey: not verifiable / optional absent / info

RE_POS = re.compile(r"===\s*Master\s+\d+,\s*Slave\s+(\d+)\s*===")
RE_STATE = re.compile(r"^\s*State:\s*(\S+)", re.I)
RE_VID = re.compile(r"Vendor Id:\s*(0x[0-9a-fA-F]+)", re.I)
RE_PID = re.compile(r"Product code:\s*(0x[0-9a-fA-F]+)", re.I)
RE_REV = re.compile(r"Revision number:\s*(0x[0-9a-fA-F]+)", re.I)
RE_NAME = re.compile(r"Device name:\s*(.*?)\s*$", re.I)


def _norm(v):
    """Normalise a hex-or-int id string to a lowercase 0x string, or None."""
    if v is None:
        return None
    try:
        return hex(int(str(v), 0))
    except (ValueError, TypeError):
        return None


def load_busdef(path):
    with open(path) as f:
        cfg = json.load(f)
    master = int(cfg.get("master", 0))
    slaves = []
    for s in cfg.get("slaves", []):
        slaves.append({
            "position": int(s["position"]),
            "name": s.get("name", "Slave %s" % s.get("position")),
            "vendor": _norm(s.get("vendor")),
            "product": _norm(s.get("product")),
            "revision": _norm(s.get("revision")),   # None => not checked
            "optional": bool(s.get("optional", False)),
        })
    slaves.sort(key=lambda x: x["position"])
    return master, slaves


class BusCheck:
    def __init__(self, halcomp, builder, useropts):
        self.halcomp = halcomp

        cfg = None
        self.ecat = "ethercat"
        for o in useropts:
            if o.startswith("cfg="):
                cfg = o.split("=", 1)[1]
            elif o.startswith("ecat="):
                self.ecat = o.split("=", 1)[1]
        if not cfg:
            cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "busdef.json")
        self.master, self.expected = load_busdef(cfg)

        for p in ("ok", "bus-alive", "slaves-complete", "all-op",
                  "bus-dead", "missing", "wrong-id", "not-op", "extra"):
            halcomp.newpin(p, hal.HAL_BIT, hal.HAL_OUT)
        halcomp.newpin("checked", hal.HAL_U32, hal.HAL_OUT)

        tv = builder.get_object("bustree")
        # columns: pos, name, expected-id, state, status-text, colour
        self.store = Gtk.ListStore(str, str, str, str, str, str)
        tv.set_model(self.store)
        cols = (("Pos", 0, False), ("Slave", 1, True), ("Erwartete ID", 2, False),
                ("State", 3, False), ("Status", 4, True))
        for title, idx, expand in cols:
            r = Gtk.CellRendererText()
            c = Gtk.TreeViewColumn(title, r, text=idx, foreground=5)
            c.set_expand(expand)
            tv.append_column(c)

        GLib.timeout_add(POLL_MS, self.poll)

    # ---- ethercat CLI access -------------------------------------------
    def _run(self, *args):
        out = subprocess.check_output(
            [self.ecat] + list(args) + ["-m", str(self.master)],
            timeout=5, stderr=subprocess.DEVNULL)
        return out.decode("utf-8", errors="replace")

    def read_live(self):
        """Return list of live slaves in bus order:
        [{pos, state, name, vendor, product, revision}], or None on CLI error.
        Uses `ethercat slaves -v` as single source so couplers/supply
        terminals without process data are covered too."""
        try:
            txt = self._run("slaves", "-v")
        except Exception:
            return None

        bus = {}
        cur = None
        for line in txt.splitlines():
            mo = RE_POS.search(line)
            if mo:
                cur = int(mo.group(1))
                bus[cur] = {"pos": cur, "state": "?", "name": "",
                            "vendor": None, "product": None, "revision": None}
                continue
            if cur is None:
                continue
            s = bus[cur]
            mo = RE_STATE.match(line)
            if mo:
                s["state"] = mo.group(1)
                continue
            for rx, key in ((RE_VID, "vendor"), (RE_PID, "product"), (RE_REV, "revision")):
                mo = rx.search(line)
                if mo:
                    s[key] = _norm(mo.group(1))
            mo = RE_NAME.search(line)
            if mo and not s["name"]:
                s["name"] = mo.group(1)

        return [bus[p] for p in sorted(bus)]

    # ---- comparison ----------------------------------------------------
    @staticmethod
    def _id_match(exp, act):
        if exp["vendor"] != act.get("vendor") or exp["product"] != act.get("product"):
            return False
        if exp["revision"] is not None and exp["revision"] != act.get("revision"):
            return False
        return True

    def evaluate(self, live):
        """Return (rows, flags). rows feed the tab; flags drive the pins."""
        rows = []
        flags = dict(bus_dead=False, missing=False, wrong_id=False,
                     not_op=False, extra=False, checked=0)

        if live is None:
            rows.append(("-", "EtherCAT-Master", "-", "-",
                         "Master nicht erreichbar (ethercat CLI Fehler)", COLOR_ERR))
            flags["bus_dead"] = True
            return rows, flags

        if len(live) == 0:
            rows.append(("-", "Bus", "-", "-",
                         "Kein Slave am Bus erreichbar", COLOR_ERR))
            flags["bus_dead"] = True
            return rows, flags

        si = 0          # index into expected
        ii = 0          # index into live
        broken = False  # sequence diverged -> rest not verifiable
        exp = self.expected

        while si < len(exp):
            e = exp[si]
            id_str = "%s:%s" % (e["vendor"], e["product"])

            if broken:
                rows.append((e["position"], e["name"], id_str, "-",
                             "nicht pruefbar (Abweichung weiter vorne)", COLOR_SUPPRESSED))
                si += 1
                continue

            act = live[ii] if ii < len(live) else None

            if act is not None and self._id_match(e, act):
                flags["checked"] += 1
                if act["state"] == "OP":
                    rows.append((act["pos"], e["name"], id_str, act["state"],
                                 "OK", COLOR_OK))
                else:
                    rows.append((act["pos"], e["name"], id_str, act["state"],
                                 "nicht in OP (State %s)" % act["state"], COLOR_WARN))
                    flags["not_op"] = True
                si += 1
                ii += 1
                continue

            # no match at this position
            if e["optional"]:
                rows.append((e["position"], e["name"], id_str, "-",
                             "optional, nicht vorhanden", COLOR_SUPPRESSED))
                si += 1          # skip optional, keep current live slave
                continue

            # required slave does not match -> root cause, stop ordered check
            if act is None:
                rows.append((e["position"], e["name"], id_str, "fehlt",
                             "FEHLT (Kette endet hier)", COLOR_ERR))
                flags["missing"] = True
            else:
                found = "%s:%s" % (act.get("vendor"), act.get("product"))
                rows.append((e["position"], e["name"], id_str, act["state"],
                             "falsche Device-ID (gefunden %s)" % found, COLOR_ERR))
                flags["wrong_id"] = True
                flags["missing"] = True
            broken = True
            si += 1

        # leftover live slaves beyond the expected list (only if not broken)
        if not broken and ii < len(live):
            flags["extra"] = True
            for act in live[ii:]:
                found = "%s:%s" % (act.get("vendor"), act.get("product"))
                rows.append((act["pos"], act["name"] or "(unbekannt)", "-",
                             act["state"], "zusaetzlicher Slave (%s)" % found,
                             COLOR_SUPPRESSED))

        return rows, flags

    # ---- poll ----------------------------------------------------------
    def poll(self):
        live = self.read_live()
        rows, f = self.evaluate(live)

        self.store.clear()
        for r in rows:
            self.store.append([str(r[0]), r[1], r[2], r[3], r[4], r[5]])

        bus_dead = f["bus_dead"]
        missing = f["missing"]
        wrong = f["wrong_id"]
        not_op = f["not_op"]
        extra = f["extra"]

        # raw problem pins
        self.halcomp["bus-dead"] = bus_dead
        self.halcomp["missing"] = missing
        self.halcomp["wrong-id"] = wrong
        self.halcomp["not-op"] = not_op
        self.halcomp["extra"] = extra
        self.halcomp["checked"] = f["checked"]

        # ok-style pins for faultlatch.monitor (HIGH = ok).
        # bus_dead suppresses the "missing" message: only bus-alive fires,
        # so a dead bus is one queue entry, not a flood.
        self.halcomp["bus-alive"] = not bus_dead
        self.halcomp["slaves-complete"] = bus_dead or not (missing or wrong)
        self.halcomp["all-op"] = not not_op
        self.halcomp["ok"] = not (bus_dead or missing or wrong or not_op)

        return True


def get_handlers(halcomp, builder, useropts):
    return [BusCheck(halcomp, builder, useropts)]
