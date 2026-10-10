"""
button_sniffer.py — notices when the cursor is over a real button (macOS only).

macOS apps describe their interface to assistive tools (screen readers etc.)
through the Accessibility API. We ask it: "what is under the cursor right
now?" If the answer is a button, link or menu item, the engine makes the
nudge a certainty instead of a chance.

This is an optional extra. If it fails for any reason it switches itself off
and the nudge keeps working with the slow-down detection alone. Note that
some apps (many browsers, Electron apps like VS Code) do not report their
buttons unless a screen reader is running, so there the answer is just "no".
"""

import threading
import time

CLICKABLE_ROLES = {
    "AXButton",
    "AXLink",
    "AXMenuItem",
    "AXMenuBarItem",
    "AXMenuButton",
    "AXPopUpButton",
    "AXCheckBox",
    "AXRadioButton",
}

CHECKS_PER_SECOND = 12


class ButtonSniffer(threading.Thread):
    def __init__(self, engine, skip=None):
        """skip(x, y) -> True for points we should not inspect (our own
        windows)."""
        super().__init__(name="button-sniffer", daemon=True)
        self.engine = engine
        self.skip = skip or (lambda x, y: False)
        self._stop_requested = threading.Event()

    def stop(self):
        self._stop_requested.set()

    def run(self):
        try:
            self._loop()
        except Exception as error:  # optional feature: fail quietly
            print(f"[button sniffer switched off: {error!r}]")
        finally:
            self.engine.over_button = False

    def _loop(self):
        import Quartz
        from ApplicationServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCopyElementAtPosition,
            AXUIElementCreateSystemWide,
            AXUIElementSetMessagingTimeout,
            kAXRoleAttribute,
        )

        system = AXUIElementCreateSystemWide()
        # Never wait long for a busy app to answer.
        AXUIElementSetMessagingTimeout(system, 0.1)

        while not self._stop_requested.wait(1.0 / CHECKS_PER_SECOND):
            engine = self.engine
            if not (engine.active and engine.features["nudge"]):
                engine.over_button = False
                continue

            # Creating an empty event is the standard way to ask
            # "where is the cursor right now?"
            position = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
            if self.skip(position.x, position.y):
                engine.over_button = False
                continue

            error, element = AXUIElementCopyElementAtPosition(
                system, position.x, position.y, None
            )
            if error != 0 or element is None:
                engine.over_button = False
                continue

            error, role = AXUIElementCopyAttributeValue(
                element, kAXRoleAttribute, None
            )
            engine.over_button = error == 0 and str(role) in CLICKABLE_ROLES
