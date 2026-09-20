#
#    faultmsg - GladeVCP handler for a persistent operator fault queue,
#    embedded as a tab in AXIS. Companion to faultlatch.comp.
#
#    Embed via the machine INI:
#      [DISPLAY]
#      EMBED_TAB_NAME = Stoermeldungen
#      EMBED_TAB_LOCATION = ntb_user_tabs
#      EMBED_TAB_COMMAND = gladevcp -c faultmsg -x {XID}
#          -u components/faulthandler/faultmsg.py
#          -H components/faulthandler/faultmsg.hal
#          -U cfg=components/faulthandler/faults.json
#          components/faulthandler/faultmsg.ui
#      Optional overrides:
#          -U logdir=<path>    log folder (default: <config>/FaultLogs)
#          -U logdays=30       keep logs newer than N days (default 30)
#
#    Overview list columns: Stufe | Zeit | Meldung | Detail
#      Zeit = time the fault appeared (KOMMT), HH:MM:SS.
#
#    Logging: one file per machine start, named "<MACHINE>_<YYYY-MM-DD_HH-MM-SS>.log",
#    in a "FaultLogs" folder under the machine config directory. Files older than
#    <logdays> days are deleted on start. Each message logs KOMMT / GEHT / QUITTIERT.
#
#    Queue semantics: shown while 'fault' is HIGH, order = arrival (FIFO), level
#    sets the colour. Info messages self-clear via the block's auto-clear-s timer,
#    with a countdown shown while it runs.
#
#    Exposes summary pins: faultmsg.any-info / -warning / -alarm / -fault / -ackable
#
#    NON-SAFE: diagnostics/HMI only.

import os
import re
import json
import math
import time
import hal
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango
from datetime import datetime

LEVELS = {"info": 0, "warning": 1, "alarm": 2}
LEVEL_NAME = ("Info", "Warnung", "Alarm")
LEVEL_COLOR = ("#ffffff", "#e3f707", "#f74307")   # info / warning / alarm
POLL_MS = 150
DEFAULT_LOG_DAYS = 30


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    out = []
    for id_str, m in cfg.items():
        out.append({
            "id": int(id_str),
            "inst": m["instance"],
            "level": LEVELS.get(str(m.get("level", "alarm")).lower(), 2),
            "title": m.get("title", "Fault %s" % id_str),
            "details": m.get("details", ""),
        })
    return out


def get_bit(name):
    try:
        return bool(hal.get_value(name))
    except Exception:
        return False


def get_s32(name, default=-1):
    try:
        return int(hal.get_value(name))
    except Exception:
        return default


def get_float(name, default=0.0):
    try:
        return float(hal.get_value(name))
    except Exception:
        return default


def config_dir():
    ini = os.environ.get("INI_FILE_NAME")
    if ini:
        return os.path.dirname(os.path.abspath(ini))
    return os.getcwd()


def machine_name():
    try:
        import linuxcnc
        ini = linuxcnc.ini(os.environ["INI_FILE_NAME"])
        name = ini.find("EMC", "MACHINE")
        if name:
            return name
    except Exception:
        pass
    return os.path.basename(config_dir()) or "machine"


def sanitize(s):
    return re.sub(r"[^\w.-]", "_", s)


class FaultQueue:
    def __init__(self, halcomp, builder, useropts):
        self.halcomp = halcomp

        cfg = None
        logdir = None
        logdays = DEFAULT_LOG_DAYS
        for o in useropts:
            if o.startswith("cfg="):
                cfg = o.split("=", 1)[1]
            elif o.startswith("logdir="):
                logdir = o.split("=", 1)[1]
            elif o.startswith("logdays="):
                try:
                    logdays = int(o.split("=", 1)[1])
                except ValueError:
                    pass
        if not cfg:
            cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "faults.json")
        self.entries = load_config(cfg)

        self.logdays = logdays
        self.logdir = logdir or os.path.join(config_dir(), "FaultLogs")
        self.logpath = None
        self._setup_log()

        self.seq = {}
        self.counter = 0
        self.arrival = {}       # id -> "HH:MM:SS" when the fault appeared
        self._last_rows = None
        self._ev = {}           # per-id edge state for logging

        for p in ("any-info", "any-warning", "any-alarm", "any-fault", "any-ackable"):
            halcomp.newpin(p, hal.HAL_BIT, hal.HAL_OUT)

        tv = builder.get_object("faulttree")
        # columns: Stufe, Zeit, Meldung, Detail, colour(foreground)
        self.store = Gtk.ListStore(str, str, str, str, str)
        tv.set_model(self.store)
        for title, idx, expand, wrap in (("Stufe", 0, False, 0),
                                        ("Zeit", 1, False, 0),
                                        ("Meldung", 2, True, 260),
                                        ("Detail", 3, True, 480)):
            r = Gtk.CellRendererText()
            if wrap:
                r.set_property("wrap-mode", Pango.WrapMode.WORD_CHAR)
                r.set_property("wrap-width", wrap)
            col = Gtk.TreeViewColumn(title, r, text=idx, foreground=4)
            col.set_expand(expand)
            col.set_resizable(True)
            tv.append_column(col)

        GLib.timeout_add(POLL_MS, self.poll)

    # ---- event log -----------------------------------------------------
    def _setup_log(self):
        try:
            os.makedirs(self.logdir, exist_ok=True)
            cutoff = time.time() - self.logdays * 86400
            for fn in os.listdir(self.logdir):
                if not fn.endswith(".log"):
                    continue
                fp = os.path.join(self.logdir, fn)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass
            now = datetime.now()
            fname = "%s_%s.log" % (sanitize(machine_name()),
                                   now.strftime("%Y-%m-%d_%H-%M-%S"))
            self.logpath = os.path.join(self.logdir, fname)
            with open(self.logpath, "w") as f:
                f.write("===== %s  Maschinenstart %s =====\n" % (
                    machine_name(), now.strftime("%Y-%m-%d %H:%M:%S")))
        except Exception:
            self.logpath = None

    def _log(self, event, e):
        if not self.logpath:
            return
        try:
            with open(self.logpath, "a") as f:
                f.write("  %s  %-16s ID %-4d %s\n" % (
                    datetime.now().strftime("%H:%M:%S"), event, e["id"], e["title"]))
        except Exception:
            pass

    # ---- poll ----------------------------------------------------------
    def poll(self):
        active = []
        any_lvl = {0: False, 1: False, 2: False}
        any_fault = False
        any_ack = False
        seen = set()

        for e in self.entries:
            inst = e["inst"]
            fault = get_bit(inst + ".fault")
            errack = get_bit(inst + ".errack-possible")

            st = self._ev.setdefault(e["id"], {"fault": False, "errack": False})
            if fault and not st["fault"]:
                self._log("KOMMT", e)
                self.arrival[e["id"]] = datetime.now().strftime("%H:%M:%S")
            if errack and not st["errack"]:
                self._log("GEHT", e)
            if (not fault) and st["fault"]:
                self._log("QUITTIERT (auto)" if e["level"] == 0 else "QUITTIERT", e)
            st["fault"] = fault
            st["errack"] = errack

            if not fault:
                continue

            seen.add(e["id"])
            if e["id"] not in self.seq:
                self.seq[e["id"]] = self.counter
                self.counter += 1
            lvl_pin = get_s32(inst + ".level", -1)
            lvl = lvl_pin if lvl_pin >= 0 else e["level"]
            clear_rem = get_float(inst + ".clear-remaining", 0.0)
            active.append((self.seq[e["id"]], e, lvl, errack, clear_rem))
            any_fault = True
            any_lvl[lvl] = True
            if errack:
                any_ack = True

        for fid in list(self.seq):
            if fid not in seen:
                del self.seq[fid]
                self.arrival.pop(fid, None)

        active.sort(key=lambda x: x[0])

        rows_data = []
        for _, e, lvl, errack, clear_rem in active:
            if clear_rem > 0:
                suffix = "   – nicht mehr zutreffend, verschwindet in %ds" % int(math.ceil(clear_rem))
            elif errack:
                suffix = "   (quittierbar)"
            else:
                suffix = ""
            rows_data.append([LEVEL_NAME[lvl],
                              self.arrival.get(e["id"], ""),
                              e["title"] + suffix,
                              e["details"],
                              LEVEL_COLOR[lvl]])

        if rows_data != self._last_rows:
            self.store.clear()
            for row in rows_data:
                self.store.append(row)
            self._last_rows = rows_data

        self.halcomp["any-info"] = any_lvl[0]
        self.halcomp["any-warning"] = any_lvl[1]
        self.halcomp["any-alarm"] = any_lvl[2]
        self.halcomp["any-fault"] = any_fault
        self.halcomp["any-ackable"] = any_ack
        return True


def get_handlers(halcomp, builder, useropts):
    return [FaultQueue(halcomp, builder, useropts)]