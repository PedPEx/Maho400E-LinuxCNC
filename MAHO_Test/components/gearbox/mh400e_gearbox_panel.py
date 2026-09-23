# -*- coding: utf-8 -*-
#
# GladeVCP handler for the MAHO MH400E gearbox status panel.
#
# Everything that a HAL_LED or a HAL_Label can show is bound directly in the
# .ui file.  This handler only renders the three texts that need decoding:
# the engaged gear, the requested gear and the fault code.
#
# It adds three input pins to the panel component:
#   <panel>.current-rpm-in   s32
#   <panel>.target-rpm-in    s32
#   <panel>.fault-code-in    s32
#
# Every update is wrapped in try/except so a problem here can never take the
# panel down during commissioning.

import hal

try:
    from gi.repository import GLib
except ImportError:                                   # very old GladeVCP
    import gobject as GLib

UPDATE_MS = 200

FAULT_TEXT = {
    0: "kein Fehler",
    1: "Welle hat Zielposition nicht erreicht (Timeout)",
    2: "Welle blockiert - Wiederholversuche erschöpft",
    3: "Spindel kam nicht zum Stillstand",
}

BIG = '<span size="xx-large" weight="bold"%s>%s</span>'


class HandlerClass(object):

    def __init__(self, halcomp, builder, useropts):
        self.halcomp = halcomp
        self.builder = builder

        for name in ("current-rpm-in", "target-rpm-in", "fault-code-in"):
            self.halcomp.newpin(name, hal.HAL_S32, hal.HAL_IN)

        self.lbl_gear = builder.get_object("lbl-gear")
        self.lbl_target = builder.get_object("lbl-target")
        self.lbl_fault = builder.get_object("lbl-fault")

        self._last = {}

        GLib.timeout_add(UPDATE_MS, self._update)

    @staticmethod
    def _gear_markup(rpm, idle_text):
        if rpm > 0:
            return BIG % ("", "%d" % rpm) + ' <span size="small">min⁻¹</span>'
        # plain text instead of a number, one size down so it still fits
        return '<span size="large" weight="bold" foreground="#c07000">%s</span>' % idle_text

    def _set(self, key, value, widget, markup):
        if self._last.get(key) == value or widget is None:
            return
        self._last[key] = value
        widget.set_markup(markup)

    def _update(self):
        try:
            rpm = int(self.halcomp["current-rpm-in"])
            self._set("gear", rpm, self.lbl_gear,
                      self._gear_markup(rpm, "Zwischen&#8203;stellung"))

            tgt = int(self.halcomp["target-rpm-in"])
            self._set("target", tgt, self.lbl_target,
                      self._gear_markup(tgt, "–"))

            code = int(self.halcomp["fault-code-in"])
            if self._last.get("fault") != code and self.lbl_fault is not None:
                self._last["fault"] = code
                text = FAULT_TEXT.get(code, "unbekannter Fehler %d" % code)
                if code:
                    self.lbl_fault.set_markup(
                        '<span foreground="#e04040" weight="bold">Fehler %d:</span> %s'
                        % (code, text))
                else:
                    self.lbl_fault.set_text(text)
        except Exception:
            pass
        return True


def get_handlers(halcomp, builder, useropts):
    return [HandlerClass(halcomp, builder, useropts)]
