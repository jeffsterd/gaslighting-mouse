"""
mac_mouse.py — the part that touches the REAL mouse (macOS only).

How it works
------------
macOS lets a trusted program install an "event tap": a function that sees
every mouse and keyboard event before any app does, and may change or drop it.

For every mouse movement we:
  1. read how far the real mouse moved (the "delta"),
  2. ask the engine where the cursor should go instead,
  3. teleport ("warp") the cursor there and rewrite the event to match.

For every click we ask the engine whether it is allowed. If not, we drop the
event so the app underneath never sees it.

Safety
------
* While the engine is off, events pass through completely untouched.
* If anything in here crashes, the event is passed through untouched.
* If this program quits or is killed, macOS removes the tap automatically
  and the mouse is normal again.
* Esc x3 (see config.py) switches everything off from any app.
"""

import threading
import time
import traceback
from collections import deque

import Quartz

import config

# Extra space above a window's contents that counts as "our window", so the
# title bar (and its close button) stays clickable too.
TITLE_BAR_HEIGHT = 32

_MOVE_EVENTS = (
    Quartz.kCGEventMouseMoved,
    Quartz.kCGEventLeftMouseDragged,
    Quartz.kCGEventRightMouseDragged,
    Quartz.kCGEventOtherMouseDragged,
)
# event type -> (button name, is this a press?)
_BUTTON_EVENTS = {
    Quartz.kCGEventLeftMouseDown: ("left", True),
    Quartz.kCGEventLeftMouseUp: ("left", False),
    Quartz.kCGEventRightMouseDown: ("right", True),
    Quartz.kCGEventRightMouseUp: ("right", False),
}


def has_permission(prompt=True):
    """
    Is this program allowed to control the computer (Accessibility)?
    With prompt=True macOS shows its own "open System Settings" dialog.
    """
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        return bool(
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: bool(prompt)})
        )
    except Exception:
        # Could not ask. Creating the tap will tell us for sure.
        return True


class MouseTap:
    def __init__(self, engine):
        self.engine = engine

        # Rectangles (x, y, width, height) of our own windows, in screen
        # coordinates. The UI keeps this up to date. Clicks inside them are
        # never counted or blocked.
        self.safe_rects = []

        # False if macOS would not let us listen to the keyboard.
        self.hotkeys_available = True

        self._tap = None
        self._source = None
        self._loop = None
        self._thread = None
        self._running = False

        self._pos = None            # where WE say the cursor is: [x, y]
        self._swallowed = set()     # buttons whose press we dropped
        self._esc_presses = deque(maxlen=config.PANIC_PRESSES)
        self._bounds = None
        self._bounds_checked_at = 0.0
        self._error_printed = False

    # ------------------------------------------------------------ start / stop

    def start(self):
        """Install the event tap. Returns False if macOS refused (no
        Accessibility permission)."""
        mouse_mask = 0
        for event_type in _MOVE_EVENTS + tuple(_BUTTON_EVENTS):
            mouse_mask |= Quartz.CGEventMaskBit(event_type)
        key_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)

        self._tap = self._create_tap(mouse_mask | key_mask)
        if self._tap is None:
            # Maybe only the keyboard part was refused. Try mouse only.
            self._tap = self._create_tap(mouse_mask)
            self.hotkeys_available = False
        if self._tap is None:
            return False

        self._source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="mouse-tap", daemon=True
        )
        self._thread.start()
        return True

    def _create_tap(self, mask):
        return Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,       # all events for this login session
            Quartz.kCGHeadInsertEventTap,    # put us first in line
            Quartz.kCGEventTapOptionDefault,  # we may change/drop events
            mask,
            self._callback,
            None,
        )

    def _run(self):
        # An event tap needs a "run loop" to deliver events. We give it its
        # own thread so the window (which owns the main thread) stays smooth.
        self._loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(
            self._loop, self._source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(self._tap, True)
        while self._running:
            Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.5, False)

    def stop(self):
        """Remove the tap. The mouse is normal again immediately."""
        self._running = False
        if self._tap is not None:
            Quartz.CGEventTapEnable(self._tap, False)
        if self._loop is not None:
            Quartz.CFRunLoopStop(self._loop)

    # ------------------------------------------------------------ the callback

    def _callback(self, proxy, event_type, event, refcon):
        """Called by macOS for every event. Return the event to let it
        through, or None to make it disappear."""
        try:
            if event_type in _MOVE_EVENTS:
                return self._on_move(event)
            if event_type in _BUTTON_EVENTS:
                button, pressed = _BUTTON_EVENTS[event_type]
                return self._on_button(event, button, pressed)
            if event_type == Quartz.kCGEventKeyDown:
                return self._on_key(event)
            if event_type in (
                Quartz.kCGEventTapDisabledByTimeout,
                Quartz.kCGEventTapDisabledByUserInput,
            ):
                # macOS switches a tap off if it is ever too slow. Switch
                # it back on.
                if self._running:
                    Quartz.CGEventTapEnable(self._tap, True)
            return event
        except Exception:
            # Never let a bug in our code break the user's mouse.
            if not self._error_printed:
                self._error_printed = True
                traceback.print_exc()
            return event

    # ------------------------------------------------------------ movement

    def _on_move(self, event):
        engine = self.engine
        if not engine.active:
            self._pos = None
            return event

        location = Quartz.CGEventGetLocation(event)
        dx = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventDeltaX)
        dy = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventDeltaY)

        new_dx, new_dy = engine.move(dx, dy)

        if new_dx == dx and new_dy == dy:
            # Normal controls and no nudge: leave the event alone and just
            # remember where the real cursor is.
            self._pos = [location.x, location.y]
            return event

        if self._pos is None:
            # First altered event since switching on. macOS has already moved
            # the cursor by (dx, dy), so step back to where it started.
            self._pos = [location.x - dx, location.y - dy]

        min_x, min_y, max_x, max_y = self._screen_bounds()
        x = min(max(self._pos[0] + new_dx, min_x), max_x)
        y = min(max(self._pos[1] + new_dy, min_y), max_y)
        self._pos = [x, y]

        point = Quartz.CGPointMake(x, y)
        Quartz.CGWarpMouseCursorPosition(point)
        # Without this line macOS ignores the mouse for 0.25s after a warp.
        Quartz.CGAssociateMouseAndMouseCursorPosition(True)

        # Make the event agree with where the cursor now is, so apps
        # (hover effects, drags) see the gaslit position too.
        Quartz.CGEventSetLocation(event, point)
        Quartz.CGEventSetIntegerValueField(
            event, Quartz.kCGMouseEventDeltaX, int(round(new_dx))
        )
        Quartz.CGEventSetIntegerValueField(
            event, Quartz.kCGMouseEventDeltaY, int(round(new_dy))
        )
        return event

    def _screen_bounds(self):
        """(min_x, min_y, max_x, max_y) covering every connected display.
        Re-checked every few seconds in case a monitor is plugged in."""
        now = time.monotonic()
        if self._bounds is not None and now - self._bounds_checked_at < 5.0:
            return self._bounds
        self._bounds_checked_at = now

        rects = []
        try:
            error, displays, count = Quartz.CGGetActiveDisplayList(16, None, None)
            if error == 0:
                rects = [Quartz.CGDisplayBounds(d) for d in list(displays)[:count]]
        except Exception:
            rects = []
        if not rects:
            rects = [Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())]

        self._bounds = (
            min(r.origin.x for r in rects),
            min(r.origin.y for r in rects),
            max(r.origin.x + r.size.width for r in rects) - 1,
            max(r.origin.y + r.size.height for r in rects) - 1,
        )
        return self._bounds

    # ------------------------------------------------------------ clicks

    def _on_button(self, event, button, pressed):
        engine = self.engine
        if not pressed:
            # A release goes through only if its press went through.
            if button in self._swallowed:
                self._swallowed.discard(button)
                return None
            return event

        if not engine.active:
            return event

        location = Quartz.CGEventGetLocation(event)
        on_our_window = self.in_safe_rect(location.x, location.y)
        if engine.click(exempt=on_our_window):
            return event
        self._swallowed.add(button)
        return None

    def in_safe_rect(self, x, y):
        for rx, ry, width, height in self.safe_rects:
            if rx <= x <= rx + width and ry - TITLE_BAR_HEIGHT <= y <= ry + height:
                return True
        return False

    # ------------------------------------------------------------ hotkeys

    def _on_key(self, event):
        if Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventAutorepeat
        ):
            return event  # a held-down key repeating; ignore

        keycode = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventKeycode
        )

        if keycode == config.PANIC_KEYCODE:
            now = time.monotonic()
            self._esc_presses.append(now)
            if (
                len(self._esc_presses) == config.PANIC_PRESSES
                and now - self._esc_presses[0] <= config.PANIC_WINDOW_SECONDS
            ):
                self._esc_presses.clear()
                self.engine.panic()
            return event  # Esc still does its normal job

        flags = Quartz.CGEventGetFlags(event)
        control = flags & Quartz.kCGEventFlagMaskControl
        option = flags & Quartz.kCGEventFlagMaskAlternate
        if keycode == config.TOGGLE_KEYCODE and control and option:
            self.engine.toggle()
            return None  # swallow it so no stray character gets typed

        return event
