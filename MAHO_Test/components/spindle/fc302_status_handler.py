#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# fc302_status_handler.py   ->  components/spindle/fc302_status_handler.py
#
# GladeVCP handler for the FC302 status page (HAL component "fc302panel").
#
# Loaded from the INI as an embedded tab; see fc302_status.hal for the exact
# EMBED_TAB_COMMAND.  Commenting that line out disables the whole page.
#
# Changes against the original version:
#   * The EtherCAT XML is LOCATED instead of hard-coded.  The old absolute
#     path pointed at a config directory that does not exist here, so the
#     fallback sdoReadConfig="0" kicked in, no SDO pins were created and the
#     HAL file failed with "pin does not exist".
#   * decode_state() now evaluates the status word BIT BY BIT, highest state
#     first.  The FC302 does not use the textbook encoding: in SWITCHED ON it
#     reports 0x0232 (bit1 set, bit0 CLEARED), so the old
#     "oe and so and rtso and qs" test never matched and the page would have
#     shown "Not Ready To Switch On" permanently.
#   * All SDO pins are created unconditionally, so the HAL wiring is
#     deterministic.  Bits disabled in the XML simply stay at 0 and are
#     labelled "Deaktiviert".
#   * Added the state of the fc302_spindle component (fault code etc.).
#   * Errors in the update loop are reported once instead of swallowed.

import hal
import gi
import os
import xml.etree.ElementTree as ET
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

# ─────────────────────────────────────────────────────────────────────────────
# Farbdefinitionen (CSS)
# ─────────────────────────────────────────────────────────────────────────────
CSS_BIT_ON      = "background-color: #00CC44; color: #000000; font-weight: bold;"
CSS_BIT_OFF     = "background-color: #444444; color: #AAAAAA;"
CSS_BIT_FAULT   = "background-color: #FF3333; color: #FFFFFF; font-weight: bold;"
CSS_BIT_WARN    = "background-color: #FFAA00; color: #000000; font-weight: bold;"
CSS_STATE_OK    = "color: #00CC44; font-weight: bold;"
CSS_STATE_FAULT = "color: #FF3333; font-weight: bold;"
CSS_STATE_IDLE  = "color: #AAAAAA;"
CSS_STATE_WARN  = "color: #FFAA00; font-weight: bold;"

MODE_NAMES = {
    0: "No mode", 1: "Profile Position", 2: "Velocity (VL)",
    3: "Profile Velocity", 4: "Torque Profile", 6: "Homing",
    8: "Cyclic Sync Pos", 9: "Cyclic Sync Vel", 10: "Cyclic Sync Trq"
}

# Fehlercodes der fc302_spindle Komponente
FAULT_NAMES = {
    0: "OK",
    1: "Drehzahl nicht erreicht (blockiert?)",
    2: "Drehmomentgrenze überschritten",
    3: "Steuerkarte Übertemperatur",
    4: "Kühlkörper Übertemperatur",
    5: "Motor Übertemperatur",
    6: "Umrichter meldet CiA402 FAULT",
    7: "Umrichter nicht im Fernbetrieb",
}


def decode_state(sw):
    """CiA402 state from the status word.

    Evaluated bit by bit and from the highest state downwards, because the
    FC302 clears bit0 while in SWITCHED ON instead of keeping it set as the
    profile specifies.  Comparing against exact state values does not work.
    """
    fault = bool(sw & (1 << 3))
    sod   = bool(sw & (1 << 6))     # switch on disabled
    rtso  = bool(sw & (1 << 0))     # ready to switch on
    so    = bool(sw & (1 << 1))     # switched on
    oe    = bool(sw & (1 << 2))     # operation enabled
    qs    = bool(sw & (1 << 5))     # quick stop (1 = not active)

    if fault:
        return "FAULT", CSS_STATE_FAULT
    if sod:
        return "Switch On Disabled", CSS_STATE_IDLE
    if not qs:
        return "Quick Stop Active", CSS_STATE_FAULT
    if oe:
        return "Operation Enabled ✓", CSS_STATE_OK
    if so:
        return "Switched On", CSS_STATE_WARN
    if rtso:
        return "Ready To Switch On", CSS_STATE_WARN
    return "Not Ready To Switch On", CSS_STATE_IDLE


def find_ethercat_xml():
    """Locate the EtherCAT config without hard-coding an absolute path."""
    candidates = []

    ini = os.environ.get("INI_FILE_NAME")
    if ini:
        candidates.append(os.path.dirname(os.path.abspath(ini)))

    cfg = os.environ.get("CONFIG_DIR")
    if cfg:
        candidates.append(cfg)

    candidates.append(os.getcwd())

    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(here)                                     # components/spindle
    candidates.append(os.path.abspath(os.path.join(here, "..")))        # components
    candidates.append(os.path.abspath(os.path.join(here, "..", "..")))  # config root

    names = ["ethercat-conf_3axes.xml", "ethercat-conf.xml"]

    seen = set()
    for d in candidates:
        if not d or d in seen:
            continue
        seen.add(d)
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


# ─────────────────────────────────────────────────────────────────────────────
# GladeVCP Handler
# ─────────────────────────────────────────────────────────────────────────────

class HandlerClass:
    UPDATE_INTERVAL_MS = 100

    def __init__(self, halcomp, builder, useropts):
        self.halcomp = halcomp
        self.builder = builder
        self._error_reported = False

        # 1. Standard Pins für State Machine
        halcomp.newpin("statusword", hal.HAL_U32, hal.HAL_IN)
        halcomp.newpin("controlword", hal.HAL_U32, hal.HAL_IN)
        halcomp.newpin("modes-op", hal.HAL_U32, hal.HAL_IN)
        halcomp.newpin("slave-online", hal.HAL_BIT, hal.HAL_IN)
        halcomp.newpin("slave-oper", hal.HAL_BIT, hal.HAL_IN)

        # 2. Statische zyklische PDO Pins
        self.pdo_pins = {
            "srv-target-vl": {"type": hal.HAL_S32, "lbl": "lbl_pdo_target_vl", "unit": "RPM"},
            "srv-actual-vl": {"type": hal.HAL_S32, "lbl": "lbl_pdo_actual_vl", "unit": "RPM"},
            "Infos-RO-PDO.speed-rpm": {"type": hal.HAL_S32, "lbl": "lbl_pdo_speed", "unit": "RPM"},
            "Infos-RO-PDO.feedback-rpm": {"type": hal.HAL_S32, "lbl": "lbl_pdo_feedback", "unit": "RPM"},
            "Infos-RO-PDO.power-kw": {"type": hal.HAL_S32, "lbl": "lbl_pdo_power", "unit": "kW", "div": 100.0},
            "Infos-RO-PDO.torque-nm": {"type": hal.HAL_S32, "lbl": "lbl_pdo_torque", "unit": "Nm"},
            "Infos-RO-PDO.torque-pct-highres": {"type": hal.HAL_S32, "lbl": "lbl_pdo_torque_pct", "unit": "%", "div": 10.0},
            "Infos-RO-PDO.brake-energy-avg": {"type": hal.HAL_S32, "lbl": "lbl_pdo_brake", "unit": "kW"},
            "Infos-RO-PDO.dc-link-voltage": {"type": hal.HAL_U32, "lbl": "lbl_pdo_dc_link", "unit": "V"},
            # Dynamischer Temperatur-Slot: lcec stellt im PDO-Bereich nur
            # ctrl-card-temp bereit (tempSlotSource = 1639).  Wird der Slot in
            # der XML umgestellt, ändert sich auch der lcec-Pinname - dann
            # muss die entsprechende Zeile in fc302_status.hal mitgeändert
            # werden.
            "Infos-RO-PDO.ctrl-card-temp": {"type": hal.HAL_S32, "lbl": "lbl_pdo_temp_slot_val", "unit": "°C"},
        }
        for name, info in self.pdo_pins.items():
            halcomp.newpin(name, info["type"], hal.HAL_IN)
            info["widget"] = builder.get_object(info["lbl"])
            info["last_val"] = None

        # 3. XML modParams & Defaults laden
        self.modparams = {
            "accelDeltaSpeed": "0", "accelDeltaTime": "3",
            "decelDeltaSpeed": "0", "decelDeltaTime": "3",
            "vlDimNumerator": "1", "vlDimDenominator": "1",
            "ramp1Up": "0", "ramp1Down": "0", "ramp2Up": "0", "ramp2Down": "0",
            "jogRampTime": "0", "qstopRampTime": "0",
            "busJog1Speed": "0", "busJog2Speed": "0",
            "digitalRelayCtrl": "0", "tempSlotSource": "1639", "sdoReadConfig": "0"
        }

        xml_path = find_ethercat_xml()
        if xml_path:
            try:
                root = ET.parse(xml_path).getroot()
                for param in root.iter('modParam'):
                    name = param.get('name')
                    if name in self.modparams:
                        self.modparams[name] = param.get('value')
            except Exception as e:
                print(f"[fc302_status_handler] XML Error ({xml_path}): {e}")
        else:
            print("[fc302_status_handler] WARNING: ethercat-conf XML not found, "
                  "using defaults for modParams")

        for name, val in self.modparams.items():
            lbl = builder.get_object(f"lbl_mp_{name}")
            if lbl:
                lbl.set_text(str(val))

        # 4. Titel des dynamischen Temperatur-Slots setzen
        TS_TITLES = {
            1618: "Motor Thermisch (PDO):",
            1619: "KTY Temperatur (PDO):",
            1634: "Kühlkörper Temp (PDO):",
            1635: "Umrichter Thermisch (PDO):",
            1639: "Steuerkarte Temp (PDO):",
        }
        try:
            ts_par = int(self.modparams.get("tempSlotSource", "1639"))
        except ValueError:
            ts_par = 1639

        ts_title = builder.get_object("lbl_pdo_temp_slot_title")
        ts_val = builder.get_object("lbl_pdo_temp_slot_val")
        if ts_title:
            ts_title.set_text(TS_TITLES.get(ts_par, "Temp (PDO):"))
            ts_title.set_visible(True)
        if ts_val:
            ts_val.set_visible(True)

        # 5. Azyklische SDOs.  Pins werden IMMER angelegt, damit die HAL-Datei
        #    unabhängig von sdoReadConfig funktioniert; deaktivierte Bits
        #    bleiben schlicht bei 0.
        sdo_val_str = self.modparams.get("sdoReadConfig", "0")
        try:
            sdo_mask = int(sdo_val_str, 16) if sdo_val_str.lower().startswith('0x') \
                       else int(sdo_val_str)
        except ValueError:
            sdo_mask = 0

        self.SDO_MAP = {
            0: {"pin": "Infos-RO.motor-thermal-pct",    "lbl": "lbl_sdo_motor_thermal",    "unit": "%",   "type": hal.HAL_U32},
            1: {"pin": "Infos-RO.kty-temperature",      "lbl": "lbl_sdo_kty_temp",         "unit": "°C",  "type": hal.HAL_S32},
            2: {"pin": "Infos-RO.heatsink-temp",        "lbl": "lbl_sdo_heatsink_temp",    "unit": "°C",  "type": hal.HAL_S32},
            3: {"pin": "Infos-RO.inverter-thermal-pct", "lbl": "lbl_sdo_inverter_thermal", "unit": "%",   "type": hal.HAL_U32},
            4: {"pin": "Infos-RO.ctrl-card-temp",       "lbl": "lbl_sdo_ctrl_card_temp",   "unit": "°C",  "type": hal.HAL_S32},
            5: {"pin": "Infos-RO.operating-hours",      "lbl": "lbl_sdo_operating_hours",  "unit": "h",   "type": hal.HAL_U32},
            6: {"pin": "Infos-RO.running-hours",        "lbl": "lbl_sdo_running_hours",    "unit": "h",   "type": hal.HAL_U32},
            7: {"pin": "Infos-RO.kwh-counter",          "lbl": "lbl_sdo_kwh_counter",      "unit": "kWh", "type": hal.HAL_U32},
        }

        self.active_sdos = {}
        for bit, info in self.SDO_MAP.items():
            halcomp.newpin(info["pin"], info["type"], hal.HAL_IN)
            lbl_widget = builder.get_object(info["lbl"])
            if sdo_mask & (1 << bit):
                self.active_sdos[bit] = {
                    "pin": info["pin"], "lbl": lbl_widget,
                    "unit": info["unit"], "last_val": None
                }
            elif lbl_widget:
                lbl_widget.set_text("Deaktiviert")
                self._set_label_style(lbl_widget,
                                      "color: #777777; font-style: italic; font-weight: normal;")

        halcomp.newpin("Infos-RO.sdo-busy", hal.HAL_BIT, hal.HAL_IN)
        self.lbl_sdo_busy = builder.get_object("lbl_sdo_busy")
        self._last_sdo_busy = None

        # 6. Zustand der fc302_spindle Komponente
        halcomp.newpin("spindle-error", hal.HAL_BIT, hal.HAL_IN)
        halcomp.newpin("spindle-fault-code", hal.HAL_S32, hal.HAL_IN)
        halcomp.newpin("spindle-stopped", hal.HAL_BIT, hal.HAL_IN)
        halcomp.newpin("spindle-at-speed", hal.HAL_BIT, hal.HAL_IN)
        self.lbl_spdl_fault   = builder.get_object("lbl_spdl_fault")
        self.lbl_spdl_stopped = builder.get_object("lbl_spdl_stopped")
        self.lbl_spdl_atspeed = builder.get_object("lbl_spdl_atspeed")
        self._last_spdl_fault = None
        self._last_spdl_stop  = None
        self._last_spdl_speed = None

        # 7. Widget Cache für State Machine und Bits
        self.w = {
            "slave_status": builder.get_object("lbl_slave_status"),
            "slave_state":  builder.get_object("lbl_slave_state"),
            "mode_num":     builder.get_object("lbl_mode_num"),
            "mode_name":    builder.get_object("lbl_mode_name"),
            "state":        builder.get_object("lbl_state"),
            "sw_hex":       builder.get_object("lbl_sw_hex"),
        }
        self.sw_bits = [builder.get_object(f"sw_bit_{i}") for i in range(16)]
        self.cw_bits = [builder.get_object(f"cw_bit_{i}") for i in range(16)]

        self._last_sw = -1
        self._last_cw = -1
        self._last_mo = -1
        self._last_onl = None
        self._last_op = None

        GLib.timeout_add(self.UPDATE_INTERVAL_MS, self._update)

    @staticmethod
    def _set_label_style(label, css):
        if not label:
            return
        sc = label.get_style_context()
        provider = Gtk.CssProvider()
        provider.load_from_data(f"label {{ {css} }}".encode())
        sc.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _update_bit_label(self, label, value, is_f, is_w):
        if not label:
            return
        label.set_text("1" if value else "0")
        css = CSS_BIT_FAULT if (value and is_f) else (
              CSS_BIT_WARN if (value and is_w) else (
              CSS_BIT_ON if value else CSS_BIT_OFF))
        self._set_label_style(label, css)

    def _update(self):
        state_w = self.w.get("state")
        if state_w is not None and state_w.get_allocated_width() <= 1:
            return True

        try:
            # --- 1. State Machine ---
            sw = self.halcomp["statusword"]
            cw = self.halcomp["controlword"]
            mo = self.halcomp["modes-op"]
            online = self.halcomp["slave-online"]
            oper = self.halcomp["slave-oper"]

            if online != self._last_onl or oper != self._last_op:
                self._last_onl, self._last_op = online, oper
                if self.w["slave_status"]:
                    self.w["slave_status"].set_text("ONLINE" if online else "OFFLINE")
                    self._set_label_style(self.w["slave_status"],
                                          CSS_BIT_ON if oper else CSS_BIT_FAULT)
                if self.w["slave_state"]:
                    self.w["slave_state"].set_text("OP ✓" if oper else "nicht OP")

            if mo != self._last_mo:
                self._last_mo = mo
                if self.w["mode_num"]:
                    self.w["mode_num"].set_text(f"Code: {mo}")
                if self.w["mode_name"]:
                    self.w["mode_name"].set_text(MODE_NAMES.get(mo, "Unknown"))
                    self._set_label_style(self.w["mode_name"],
                                          CSS_STATE_OK if mo == 2 else CSS_STATE_WARN)

            if sw != self._last_sw:
                self._last_sw = sw
                st_text, st_css = decode_state(sw)
                if self.w["sw_hex"]:
                    self.w["sw_hex"].set_text(f"SW: 0x{sw:04X}  ({sw})")
                if self.w["state"]:
                    self.w["state"].set_text(st_text)
                    self._set_label_style(self.w["state"], st_css)
                for i in range(16):
                    self._update_bit_label(self.sw_bits[i], bool(sw & (1 << i)), i == 3, i == 7)

            if cw != self._last_cw:
                self._last_cw = cw
                for i in range(16):
                    self._update_bit_label(self.cw_bits[i], bool(cw & (1 << i)), i == 7, False)

            # --- 2. Zyklische PDOs ---
            for pin_name, info in self.pdo_pins.items():
                val = self.halcomp[pin_name]
                if val != info["last_val"]:
                    info["last_val"] = val
                    if info["widget"]:
                        display_val = val / info["div"] if "div" in info else val
                        fmt = f"{display_val:.2f}" if "div" in info else f"{display_val}"
                        info["widget"].set_text(f"{fmt} {info['unit']}")

            # --- 3. Azyklische SDOs ---
            for bit, sdo in self.active_sdos.items():
                val = self.halcomp[sdo["pin"]]
                if sdo["last_val"] != val:
                    sdo["last_val"] = val
                    if sdo["lbl"]:
                        sdo["lbl"].set_text(f"{val} {sdo['unit']}")

            if self.lbl_sdo_busy:
                sdo_busy = self.halcomp["Infos-RO.sdo-busy"]
                if sdo_busy != self._last_sdo_busy:
                    self._last_sdo_busy = sdo_busy
                    self.lbl_sdo_busy.set_text("SDO BUSY" if sdo_busy else "SDO IDLE")
                    self._set_label_style(self.lbl_sdo_busy,
                                          CSS_BIT_WARN if sdo_busy else CSS_BIT_OFF)

            # --- 4. Zustand der Spindelkomponente ---
            fc = self.halcomp["spindle-fault-code"]
            err = self.halcomp["spindle-error"]
            if fc != self._last_spdl_fault:
                self._last_spdl_fault = fc
                if self.lbl_spdl_fault:
                    self.lbl_spdl_fault.set_text(f"{fc} – {FAULT_NAMES.get(fc, 'unbekannt')}")
                    self._set_label_style(self.lbl_spdl_fault,
                                          CSS_STATE_FAULT if err else CSS_STATE_OK)

            stopped = self.halcomp["spindle-stopped"]
            if stopped != self._last_spdl_stop:
                self._last_spdl_stop = stopped
                if self.lbl_spdl_stopped:
                    self.lbl_spdl_stopped.set_text("steht" if stopped else "dreht")
                    self._set_label_style(self.lbl_spdl_stopped,
                                          CSS_STATE_IDLE if stopped else CSS_STATE_OK)

            atspeed = self.halcomp["spindle-at-speed"]
            if atspeed != self._last_spdl_speed:
                self._last_spdl_speed = atspeed
                if self.lbl_spdl_atspeed:
                    self.lbl_spdl_atspeed.set_text("ja" if atspeed else "nein")
                    self._set_label_style(self.lbl_spdl_atspeed,
                                          CSS_STATE_OK if atspeed else CSS_STATE_IDLE)

        except Exception as e:
            if not self._error_reported:
                self._error_reported = True
                print(f"[fc302_status_handler] update error: {e}")

        return True


def get_handlers(halcomp, builder, useropts):
    return [HandlerClass(halcomp, builder, useropts)]
