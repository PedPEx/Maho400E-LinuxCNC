#
#    buscheck - EtherCAT bus supervision for LinuxCNC.
#
#    Compares the live bus against an expected bus definition (busdef.json)
#    and reports, automatically for every configured slave:
#      * missing slave / wrong Device-ID  -> error   (root cause only)
#      * configured slave not in OP        -> warning (with its AL state)
#      * more slaves present than defined   -> info
#      * safety-PLC slave whose Safety-CRC changed -> error   (see below)
#
#    Cascade handling: the ID sequence is compared in bus order and the check
#    stops at the first deviation, because a physically absent slave shifts the
#    ring positions of everything behind it. So one root message is raised, not
#    a flood of follow-on errors. A completely dead bus yields a single message.
#    Slaves marked "optional" in busdef.json may be absent (info, not error).
#
#    Resource behaviour: the slave Identity (vendor/product/revision) is static
#    at runtime, so the expensive `ethercat slaves -v` is run only ONCE and
#    whenever the set of slaves changes; every poll otherwise uses the cheap
#    `ethercat slaves` (position + AL state only). The tab is redrawn only when
#    a row actually changed, so scrolling stays put and idle CPU stays low.
#
#    Safety-CRC check: a slave may carry "safety_plc": true in busdef.json. It
#    then MUST also carry "safety_crc" (the expected CRC of its safety program).
#    If "safety_crc_sdo" (a readable CoE object) is given, buscheck reads the
#    live CRC once after the slave reaches OP and compares it, so a changed
#    safety program is detected. Without a readable SDO the CRC stays a
#    documented setpoint and the row shows "not verifiable".
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
#      Optional user options: -U poll=2000  (ms)   -U ecat=/usr/bin/ethercat
#
#    HAL pins (all HAL_OUT bit unless noted):
#      buscheck.ok               all configured slaves present, correct ID, in OP
#      buscheck.bus-alive        at least one slave answers            (ok-style)
#      buscheck.slaves-complete  no required slave missing/wrong-ID    (ok-style)
#      buscheck.all-op           every configured, reachable slave in OP (ok-style)
#      buscheck.safety-ok        every safety-PLC slave verified & CRC matches
#                                                                     (ok-style)
#      buscheck.bus-dead         no slave answers at all
#      buscheck.missing          a required slave is missing / wrong ID
#      buscheck.wrong-id         a present slave has the wrong Device-ID
#      buscheck.not-op           a configured slave is not in OP
#      buscheck.extra            more slaves present than configured
#      buscheck.safety-mismatch  a safety-PLC slave's CRC differs from expected
#      buscheck.safety-unverified a safety CRC could not be read/verified
#      buscheck.checked          u32, number of configured slaves verified
#      buscheck.safety-checked   u32, number of safety CRCs verified as matching
#
#    NON-SAFE: diagnostics/HMI only; never a protective function. The Safety-CRC
#    check is a configuration-integrity aid, not a safety function in itself.

import os
import re
import json
import subprocess

import hal
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

DEFAULT_POLL_MS = 2000

COLOR_OK = "#2e7d32"       # green
COLOR_WARN = "#e3f707"     # yellow  (matches the Stoermeldungen palette)
COLOR_ERR = "#f74307"      # orange-red
COLOR_SUPPRESSED = "#808080"  # grey: not verifiable / optional absent / info

# `ethercat slaves -v` (verbose: Identity per slave, static -> cached)
RE_POS = re.compile(r"===\s*Master\s+\d+,\s*Slave\s+(\d+)\s*===")
RE_STATE = re.compile(r"^\s*State:\s*(\S+)", re.I)
RE_VID = re.compile(r"Vendor Id:\s*(0x[0-9a-fA-F]+)", re.I)
RE_PID = re.compile(r"Product code:\s*(0x[0-9a-fA-F]+)", re.I)
RE_REV = re.compile(r"Revision number:\s*(0x[0-9a-fA-F]+)", re.I)
RE_NAME = re.compile(r"Device name:\s*(.*?)\s*$", re.I)

# `ethercat slaves` (plain: one line per slave, cheap -> every poll)
#   0  0:0   PREOP  +  EK1914, 2 Ch. Safety Input/Output 24V,  TwinSAFE
RE_LINE = re.compile(r"^\s*(\d+)\s+\d+:\d+\s+(\S+)\s+\S+\s+(.*?)\s*$")

_TYPE_BY_SIZE = {1: "uint8", 2: "uint16", 4: "uint32", 8: "uint64"}


def _norm(v):
    """Normalise a hex-or-int id string to a lowercase 0x string, or None."""
    if v is None:
        return None
    try:
        return hex(int(str(v), 0))
    except (ValueError, TypeError):
        return None


def _norm_sdo(sd):
    """Normalise a safety_crc_sdo dict, or None."""
    if not sd:
        return None
    idx = _norm(sd.get("index"))
    if idx is None:
        return None
    return {
        "index": idx,
        "subindex": _norm(sd.get("subindex", "0x0")) or "0x0",
        "size": int(sd.get("size", 4)),
    }


def load_busdef(path):
    with open(path) as f:
        cfg = json.load(f)
    master = int(cfg.get("master", 0))
    slaves = []
    for s in cfg.get("slaves", []):
        safety_plc = bool(s.get("safety_plc", False))
        safety_crc = _norm(s.get("safety_crc")) if safety_plc else None
        if safety_plc and safety_crc is None:
            raise ValueError(
                "busdef: slave at position %s has \"safety_plc\": true but no "
                "valid \"safety_crc\"" % s.get("position"))
        slaves.append({
            "position": int(s["position"]),
            "name": s.get("name", "Slave %s" % s.get("position")),
            "vendor": _norm(s.get("vendor")),
            "product": _norm(s.get("product")),
            "revision": _norm(s.get("revision")),   # None => not checked
            "optional": bool(s.get("optional", False)),
            "safety_plc": safety_plc,
            "safety_crc": safety_crc,
            "safety_crc_sdo": _norm_sdo(s.get("safety_crc_sdo")) if safety_plc else None,
        })
    slaves.sort(key=lambda x: x["position"])
    return master, slaves


class BusCheck:
    def __init__(self, halcomp, builder, useropts):
        self.halcomp = halcomp

        cfg = None
        self.ecat = "ethercat"
        poll_ms = DEFAULT_POLL_MS
        for o in useropts:
            if o.startswith("cfg="):
                cfg = o.split("=", 1)[1]
            elif o.startswith("ecat="):
                self.ecat = o.split("=", 1)[1]
            elif o.startswith("poll="):
                try:
                    poll_ms = max(250, int(o.split("=", 1)[1]))
                except ValueError:
                    pass
        if not cfg:
            cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "busdef.json")
        self.master, self.expected = load_busdef(cfg)

        # caches
        self._ident = None        # {pos: {vendor, product, revision, name}}
        self._ident_sig = None    # signature of the bus the ident cache is for
        self._crc = {}            # {pos: (status, actual)}  status: ok/mismatch/unreadable/unconfigured
        self._last_rows = None     # last rendered rows -> change-only redraw

        for p in ("ok", "bus-alive", "slaves-complete", "all-op", "safety-ok",
                  "bus-dead", "missing", "wrong-id", "not-op", "extra",
                  "safety-mismatch", "safety-unverified"):
            halcomp.newpin(p, hal.HAL_BIT, hal.HAL_OUT)
        halcomp.newpin("checked", hal.HAL_U32, hal.HAL_OUT)
        halcomp.newpin("safety-checked", hal.HAL_U32, hal.HAL_OUT)

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

        GLib.timeout_add(poll_ms, self.poll)

    # ---- ethercat CLI access -------------------------------------------
    def _run(self, *args):
        out = subprocess.check_output(
            [self.ecat] + list(args) + ["-m", str(self.master)],
            timeout=5, stderr=subprocess.DEVNULL)
        return out.decode("utf-8", errors="replace")

    def _read_state(self):
        """Cheap per-poll read: [{pos, state, name}] in bus order, or None.
        Uses plain `ethercat slaves` (one line per slave)."""
        try:
            txt = self._run("slaves")
        except Exception:
            return None
        out = []
        for line in txt.splitlines():
            mo = RE_LINE.match(line)
            if mo:
                out.append({"pos": int(mo.group(1)),
                            "state": mo.group(2),
                            "name": mo.group(3)})
        out.sort(key=lambda x: x["pos"])
        return out

    def _read_identity(self):
        """Expensive read (only on bus change): {pos: {vendor, product,
        revision, name}}, or None on CLI error. Uses `ethercat slaves -v`."""
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
                bus[cur] = {"vendor": None, "product": None,
                            "revision": None, "name": ""}
                continue
            if cur is None:
                continue
            s = bus[cur]
            for rx, key in ((RE_VID, "vendor"), (RE_PID, "product"), (RE_REV, "revision")):
                mo = rx.search(line)
                if mo:
                    s[key] = _norm(mo.group(1))
            mo = RE_NAME.search(line)
            if mo and not s["name"]:
                s["name"] = mo.group(1)
        return bus

    def _upload(self, pos, sdo):
        """Read a CoE object via `ethercat upload`, return normalised 0x string
        or None on any error."""
        t = _TYPE_BY_SIZE.get(sdo["size"], "uint32")
        try:
            out = subprocess.check_output(
                [self.ecat, "upload", "-m", str(self.master), "-p", str(pos),
                 "--type", t, sdo["index"], sdo["subindex"]],
                timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
        except Exception:
            return None
        mo = re.search(r"0x[0-9a-fA-F]+", out)
        return _norm(mo.group(0)) if mo else None

    def read_live(self):
        """Merge cheap state with cached identity. Returns (live, ready):
        live = [{pos, state, name, vendor, product, revision}] or None,
        ready = True only when the identity cache matches the current bus."""
        state = self._read_state()
        if state is None:
            return None, False

        sig = tuple((s["pos"], s["name"]) for s in state)
        if sig != self._ident_sig or self._ident is None:
            ident = self._read_identity()
            if ident is not None:
                self._ident = ident
                self._ident_sig = sig
                self._crc = {}          # bus changed -> re-verify safety CRCs
            else:
                # could not (re)identify yet -> not ready this cycle
                return state, False

        live = []
        for s in state:
            idn = self._ident.get(s["pos"], {})
            live.append({
                "pos": s["pos"], "state": s["state"], "name": s["name"],
                "vendor": idn.get("vendor"), "product": idn.get("product"),
                "revision": idn.get("revision"),
            })
        return live, True

    # ---- safety CRC ----------------------------------------------------
    def _update_safety_crc(self, live_by_pos):
        """Read each configured safety-PLC slave's CRC once, after it is present
        and in OP. Results cached in self._crc until the bus changes."""
        for e in self.expected:
            if not e["safety_plc"]:
                continue
            pos = e["position"]
            if pos in self._crc:
                continue
            act = live_by_pos.get(pos)
            if act is None or act["state"] != "OP" or not self._id_match(e, act):
                continue
            sdo = e["safety_crc_sdo"]
            if sdo is None:
                self._crc[pos] = ("unconfigured", None)
                continue
            actual = self._upload(pos, sdo)
            if actual is None:
                self._crc[pos] = ("unreadable", None)
            elif actual == e["safety_crc"]:
                self._crc[pos] = ("ok", actual)
            else:
                self._crc[pos] = ("mismatch", actual)

    # ---- comparison ----------------------------------------------------
    @staticmethod
    def _id_match(exp, act):
        if exp["vendor"] != act.get("vendor") or exp["product"] != act.get("product"):
            return False
        if exp["revision"] is not None and exp["revision"] != act.get("revision"):
            return False
        return True

    def _safety_suffix(self, e):
        """Return (text_suffix, colour_override_or_None, flag) for a matched,
        in-OP safety-PLC slave, based on the cached CRC result."""
        status, actual = self._crc.get(e["position"], (None, None))
        if status == "ok":
            return " · Safety-CRC ok", None, None
        if status == "mismatch":
            return (" · SAFETY-CRC ABWEICHUNG (ist %s, soll %s)"
                    % (actual, e["safety_crc"]), COLOR_ERR, "mismatch")
        if status == "unreadable":
            return " · Safety-CRC nicht lesbar", COLOR_WARN, "unverified"
        if status == "unconfigured":
            return " · Safety-CRC nicht konfiguriert (kein SDO)", COLOR_WARN, "unverified"
        return " · Safety-CRC wird geprüft…", COLOR_WARN, "unverified"

    def evaluate(self, live):
        """Return (rows, flags). rows feed the tab; flags drive the pins."""
        rows = []
        flags = dict(bus_dead=False, missing=False, wrong_id=False,
                     not_op=False, extra=False, checked=0,
                     safety_mismatch=False, safety_unverified=False,
                     safety_checked=0)

        if live is None:
            rows.append(("-", "EtherCAT-Master", "-", "-",
                         "Master nicht erreichbar (ethercat CLI Fehler)", COLOR_ERR))
            flags["bus_dead"] = True
            flags["safety_unverified"] = True
            return rows, flags

        if len(live) == 0:
            rows.append(("-", "Bus", "-", "-",
                         "Kein Slave am Bus erreichbar", COLOR_ERR))
            flags["bus_dead"] = True
            flags["safety_unverified"] = True
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
                if e["safety_plc"]:
                    flags["safety_unverified"] = True
                si += 1
                continue

            act = live[ii] if ii < len(live) else None

            if act is not None and self._id_match(e, act):
                flags["checked"] += 1
                if act["state"] == "OP":
                    status_txt, colour, sflag = "OK", COLOR_OK, None
                    if e["safety_plc"]:
                        suf, col_over, sflag = self._safety_suffix(e)
                        status_txt += suf
                        if col_over:
                            colour = col_over
                        if sflag == "mismatch":
                            flags["safety_mismatch"] = True
                        elif sflag == "unverified":
                            flags["safety_unverified"] = True
                        elif sflag is None:
                            flags["safety_checked"] += 1
                    rows.append((act["pos"], e["name"], id_str, act["state"],
                                 status_txt, colour))
                else:
                    rows.append((act["pos"], e["name"], id_str, act["state"],
                                 "nicht in OP (State %s)" % act["state"], COLOR_WARN))
                    flags["not_op"] = True
                    if e["safety_plc"]:
                        flags["safety_unverified"] = True
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
            if e["safety_plc"]:
                flags["safety_unverified"] = True
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
    def _render(self, rows):
        """Redraw the store only when rows actually changed (keeps scroll)."""
        key = [tuple(r) for r in rows]
        if key == self._last_rows:
            return
        self._last_rows = key
        self.store.clear()
        for r in rows:
            self.store.append([str(r[0]), r[1], r[2], r[3], r[4], r[5]])

    def poll(self):
        live, ready = self.read_live()

        if live is not None and not ready:
            # bus present but identity not (re)established yet: show a transient
            # note and leave the pins at their last value.
            self._render([("-", "Bus", "-", "-", "Bus wird geprüft…", COLOR_SUPPRESSED)])
            return True

        if live is not None:
            self._update_safety_crc({s["pos"]: s for s in live})

        rows, f = self.evaluate(live)
        self._render(rows)

        bus_dead = f["bus_dead"]
        missing = f["missing"]
        wrong = f["wrong_id"]
        not_op = f["not_op"]
        extra = f["extra"]
        s_mismatch = f["safety_mismatch"]
        s_unver = f["safety_unverified"]

        # raw problem pins
        self.halcomp["bus-dead"] = bus_dead
        self.halcomp["missing"] = missing
        self.halcomp["wrong-id"] = wrong
        self.halcomp["not-op"] = not_op
        self.halcomp["extra"] = extra
        self.halcomp["safety-mismatch"] = s_mismatch
        self.halcomp["safety-unverified"] = s_unver
        self.halcomp["checked"] = f["checked"]
        self.halcomp["safety-checked"] = f["safety_checked"]

        # ok-style pins for faultlatch.monitor (HIGH = ok).
        # bus_dead suppresses the "missing" message: only bus-alive fires,
        # so a dead bus is one queue entry, not a flood.
        self.halcomp["bus-alive"] = not bus_dead
        self.halcomp["slaves-complete"] = bus_dead or not (missing or wrong)
        self.halcomp["all-op"] = not not_op
        self.halcomp["safety-ok"] = not (s_mismatch or s_unver)
        self.halcomp["ok"] = not (bus_dead or missing or wrong or not_op
                                  or s_mismatch or s_unver)

        return True


def get_handlers(halcomp, builder, useropts):
    return [BusCheck(halcomp, builder, useropts)]
