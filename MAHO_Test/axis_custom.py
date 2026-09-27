# axis_custom.py
# Executed by AXIS at startup (USER_COMMAND_FILE).
#
# Hide the "Override Limits" checkbox. Limit override is handled in
# hardware (key switch in the cabinet) and masked in HAL via
# EL1859.din-2, so the GUI function must not be available.

def _find_override_checkbox(path="."):
    """Return the Tk path of the checkbutton bound to 'override_limits'."""
    tk = root_window.tk
    for child in tk.splitlist(tk.call("winfo", "children", path)):
        try:
            if (tk.call("winfo", "class", child) == "Checkbutton" and
                    str(tk.call(child, "cget", "-variable")) == "override_limits"):
                return child
        except Exception:
            pass
        found = _find_override_checkbox(child)
        if found:
            return found
    return None

_ovr = _find_override_checkbox()
if _ovr:
    # Remove from layout with whatever geometry manager placed it
    _mgr = root_window.tk.call("winfo", "manager", _ovr)
    if _mgr:
        root_window.tk.call(_mgr, "forget", _ovr)
    # Make it inert as well (keyboard accelerator)
    root_window.tk.call(_ovr, "configure", "-command", "")
else:
    print("axis_custom.py: 'Override Limits' checkbox not found")