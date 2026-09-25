#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mh400e_toolset - userspace helper for the manual tool change.

Two jobs, both of which need the LinuxCNC command channel and can therefore
not be done from the realtime component:

1. Setting the current tool number. HAL cannot change the interpreter's idea of
   the current tool: that number lives in the interpreter and is only moved by
   M61. Two request channels feed this helper - one from mh400e_toolchange
   (current tool set to 0 when a change is started at the release button), one
   from the GUI so the operator can enter the tool that was actually inserted.

2. Operator messages. Realtime code can only write to the RTAPI log, which
   never reaches the GUI. This helper watches the state pins of
   mh400e_toolchange and posts the corresponding notifications through NML,
   where AXIS (and later QtPyVCP) picks them up.

None of these messages influence the interpreter. text_msg and error_msg differ
only in appearance - neither stops the machine, and a pending M6 stays blocked
by the HAL handshake alone.

Pins
  mh400e-toolset.req-comp       bit in   rising edge: apply number-comp
  mh400e-toolset.number-comp    s32 in   tool number requested by the component
  mh400e-toolset.req-manual     bit in   rising edge: apply number-manual
  mh400e-toolset.number-manual  s32 in   tool number entered by the operator
  mh400e-toolset.ack            bit out  high for a moment after a successful M61
  mh400e-toolset.busy           bit out  high while a request is executed
  mh400e-toolset.error          bit out  high if the last request was rejected
  mh400e-toolset.tool-number    s32 out  current tool as reported by LinuxCNC
  mh400e-toolset.state          s32 in   mh400e-toolchange.0.state
  mh400e-toolset.change-active  bit in   mh400e-toolchange.0.change-active
  mh400e-toolset.manual-change  bit in   mh400e-toolchange.0.manual-change

Messages are written in German because they are read by the machine operator.
"""

import sys
import time

import hal
import linuxcnc

POLL_INTERVAL = 0.05    # s, userspace poll rate
ACK_HOLD = 0.2          # s, how long the ack pin stays high

# Waiting time before the first delay message. Keep this in sync with the
# 'timeout' parameter of mh400e_toolchange so log and GUI agree.
TIMEOUT_S = 60.0

# Upper limit for repeated delay messages. Notifications in AXIS stay until
# they are dismissed, so an unattended machine must not pile them up. The
# blinking button keeps signalling the pending change afterwards.
TIMEOUT_MAX_MSG = 3

# Post a notification once a tool change has been completed.
SHOW_FINISH_MSG = True

# States of mh400e_toolchange, mirrored from the component
ST_IDLE = 0
ST_WAIT_OPEN = 1
ST_OPEN = 2
ST_CLOSE = 3
ST_FINISH = 4

MSG_WAIT_BUTTON = (
    "Werkzeugwechsel angefordert - auf manuellen Werkzeugwechsel "
    "durch Benutzer wird gewartet. Taster druecken, um die Spannzange "
    "zu oeffnen."
)
MSG_TOOL_RELEASED = (
    "Spannzange geoeffnet - Werkzeug wechseln und Taster erneut "
    "druecken, um das Werkzeug einzuziehen."
)
MSG_FINISHED = "Werkzeugwechsel abgeschlossen, Werkzeug gespannt."
MSG_DELAY_WAIT = (
    "Werkzeugwechsel laeuft seit %d min - Spannzange noch geschlossen, "
    "es wird auf den Taster gewartet."
)
MSG_DELAY_OPEN = (
    "Werkzeugwechsel laeuft seit %d min - Spannzange offen, Taster "
    "druecken, um das Werkzeug zu spannen."
)


def main():
    h = hal.component("mh400e-toolset")
    h.newpin("req-comp", hal.HAL_BIT, hal.HAL_IN)
    h.newpin("number-comp", hal.HAL_S32, hal.HAL_IN)
    h.newpin("req-manual", hal.HAL_BIT, hal.HAL_IN)
    h.newpin("number-manual", hal.HAL_S32, hal.HAL_IN)
    h.newpin("ack", hal.HAL_BIT, hal.HAL_OUT)
    h.newpin("busy", hal.HAL_BIT, hal.HAL_OUT)
    h.newpin("error", hal.HAL_BIT, hal.HAL_OUT)
    h.newpin("tool-number", hal.HAL_S32, hal.HAL_OUT)
    h.newpin("state", hal.HAL_S32, hal.HAL_IN)
    h.newpin("change-active", hal.HAL_BIT, hal.HAL_IN)
    h.newpin("manual-change", hal.HAL_BIT, hal.HAL_IN)
    h.ready()

    cmd = linuxcnc.command()
    stat = linuxcnc.stat()

    prev_comp = False
    prev_manual = False
    prev_active = False
    prev_state = ST_IDLE
    ack_until = 0.0
    change_start = 0.0
    warn_count = 0

    try:
        while True:
            now = time.time()

            try:
                stat.poll()
                h["tool-number"] = int(stat.tool_in_spindle)
            except linuxcnc.error:
                # LinuxCNC not up yet or shutting down - keep the loop alive
                time.sleep(POLL_INTERVAL)
                continue

            # --------------------------------------------------------------
            # Tool number requests
            # --------------------------------------------------------------
            req_comp = bool(h["req-comp"])
            req_manual = bool(h["req-manual"])

            number = None
            if req_comp and not prev_comp:
                number = int(h["number-comp"])
            elif req_manual and not prev_manual:
                number = int(h["number-manual"])

            prev_comp = req_comp
            prev_manual = req_manual

            if number is not None:
                h["busy"] = True
                if set_tool(cmd, stat, number):
                    h["error"] = False
                    h["ack"] = True
                    ack_until = now + ACK_HOLD
                else:
                    h["error"] = True
                h["busy"] = False

            if h["ack"] and now >= ack_until:
                h["ack"] = False

            # --------------------------------------------------------------
            # Operator messages, driven by the state of the RT component
            # --------------------------------------------------------------
            state = int(h["state"])
            active = bool(h["change-active"])

            if active and not prev_active:
                # A change sequence has just started - restart the clock
                change_start = now
                warn_count = 0

            if state != prev_state:
                if state == ST_WAIT_OPEN:
                    # Requested by M6: the interpreter is now blocked until
                    # both presses have been made, so say so explicitly.
                    post(cmd, MSG_WAIT_BUTTON, error=False)
                elif state == ST_OPEN:
                    post(cmd, MSG_TOOL_RELEASED, error=False)

            if active and warn_count < TIMEOUT_MAX_MSG:
                elapsed = now - change_start
                if elapsed >= (warn_count + 1) * TIMEOUT_S:
                    warn_count += 1
                    minutes = int(elapsed / 60.0)
                    if state == ST_OPEN:
                        post(cmd, MSG_DELAY_OPEN % minutes, error=True)
                    else:
                        post(cmd, MSG_DELAY_WAIT % minutes, error=True)

            if prev_active and not active:
                if SHOW_FINISH_MSG and prev_state in (ST_CLOSE, ST_FINISH):
                    post(cmd, MSG_FINISHED, error=False)
                warn_count = 0

            prev_active = active
            prev_state = state

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        pass
    finally:
        h.exit()


def post(cmd, text, error=False):
    """Send a notification to the GUI. Never affects the interpreter."""
    try:
        if error:
            cmd.error_msg(text)
        else:
            cmd.text_msg(text)
    except linuxcnc.error as exc:
        print("mh400e_toolset: message failed: %s" % exc, file=sys.stderr)


def set_tool(cmd, stat, number):
    """Issue M61 Q<number>. Returns True on success."""
    if number < 0:
        print("mh400e_toolset: negative tool number %d rejected" % number,
              file=sys.stderr)
        return False

    stat.poll()
    if stat.task_state != linuxcnc.STATE_ON:
        print("mh400e_toolset: machine is off, M61 Q%d skipped" % number,
              file=sys.stderr)
        return False
    if stat.interp_state != linuxcnc.INTERP_IDLE:
        print("mh400e_toolset: interpreter busy, M61 Q%d skipped" % number,
              file=sys.stderr)
        return False

    previous_mode = stat.task_mode
    try:
        cmd.mode(linuxcnc.MODE_MDI)
        cmd.wait_complete(5)
        cmd.mdi("M61 Q%d" % number)
        cmd.wait_complete(5)
    except linuxcnc.error as exc:
        print("mh400e_toolset: M61 Q%d failed: %s" % (number, exc),
              file=sys.stderr)
        return False
    finally:
        # Return to whatever mode the operator was in before
        try:
            if previous_mode in (linuxcnc.MODE_MANUAL, linuxcnc.MODE_AUTO):
                cmd.mode(previous_mode)
                cmd.wait_complete(5)
        except linuxcnc.error:
            pass

    print("mh400e_toolset: current tool set to %d" % number)
    return True


if __name__ == "__main__":
    main()
