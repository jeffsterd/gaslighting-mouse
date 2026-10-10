"""
Tests for mac_mouse.py using a pretend version of macOS.

The real file talks to Quartz, which only exists on a Mac and needs
Accessibility permission. Here we swap in a small fake that records what the
code *asks* macOS to do (warp the cursor, drop a click...), so the logic can
be checked anywhere without moving a real mouse.

    python -m unittest discover -s tests -v
"""

import os
import random
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Point:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _Size:
    def __init__(self, width, height):
        self.width, self.height = width, height


class _Rect:
    def __init__(self, x, y, width, height):
        self.origin, self.size = _Point(x, y), _Size(width, height)


class FakeEvent:
    def __init__(self, x=0, y=0, dx=0, dy=0, keycode=0, flags=0, repeat=0):
        self.location = _Point(x, y)
        self.fields = {"dx": dx, "dy": dy, "keycode": keycode, "repeat": repeat}
        self.flags = flags


def build_fake_quartz():
    q = types.ModuleType("Quartz")
    names = [
        "kCGEventMouseMoved", "kCGEventLeftMouseDragged",
        "kCGEventRightMouseDragged", "kCGEventOtherMouseDragged",
        "kCGEventLeftMouseDown", "kCGEventLeftMouseUp",
        "kCGEventRightMouseDown", "kCGEventRightMouseUp", "kCGEventKeyDown",
        "kCGEventTapDisabledByTimeout", "kCGEventTapDisabledByUserInput",
    ]
    for number, name in enumerate(names, start=1):
        setattr(q, name, number)
    q.kCGMouseEventDeltaX, q.kCGMouseEventDeltaY = "dx", "dy"
    q.kCGKeyboardEventKeycode, q.kCGKeyboardEventAutorepeat = "keycode", "repeat"
    q.kCGEventFlagMaskControl, q.kCGEventFlagMaskAlternate = 0x40000, 0x80000
    q.kCGSessionEventTap = q.kCGHeadInsertEventTap = q.kCGEventTapOptionDefault = 0

    q.warps = []          # every place the code teleported the cursor to
    q.reenabled = []
    q.CGEventMaskBit = lambda event_type: 1 << event_type
    q.CGEventGetLocation = lambda event: event.location
    q.CGEventSetLocation = lambda event, point: setattr(event, "location", point)
    q.CGEventGetIntegerValueField = lambda event, field: event.fields[field]
    q.CGEventSetIntegerValueField = (
        lambda event, field, value: event.fields.__setitem__(field, value)
    )
    q.CGEventGetFlags = lambda event: event.flags
    q.CGPointMake = _Point
    q.CGWarpMouseCursorPosition = lambda point: q.warps.append((point.x, point.y))
    q.CGAssociateMouseAndMouseCursorPosition = lambda connected: 0
    q.CGGetActiveDisplayList = lambda maximum, a, b: (0, [1], 1)
    q.CGDisplayBounds = lambda display: _Rect(0, 0, 1440, 900)
    q.CGMainDisplayID = lambda: 1
    q.CGEventTapEnable = lambda tap, on: q.reenabled.append(on)
    return q


# Must happen before mac_mouse is imported.
Q = build_fake_quartz()
sys.modules["Quartz"] = Q

import config  # noqa: E402
import mac_mouse  # noqa: E402
from engine import ChaosEngine  # noqa: E402


def make(**features):
    engine = ChaosEngine(rng=random.Random(3))
    for name in engine.features:
        engine.features[name] = features.get(name, False)
    tap = mac_mouse.MouseTap(engine)
    tap._tap = object()
    tap._running = True
    Q.warps.clear()
    Q.reenabled.clear()
    return engine, tap


def send(tap, event_type, event):
    return tap._callback(None, event_type, event, None)


class MoveTests(unittest.TestCase):
    def test_off_passes_events_through_untouched(self):
        engine, tap = make()
        event = FakeEvent(x=500, y=400, dx=10, dy=5)
        self.assertIs(send(tap, Q.kCGEventMouseMoved, event), event)
        self.assertEqual(Q.warps, [])
        self.assertEqual((event.location.x, event.location.y), (500, 400))

    def test_inverted_moves_cursor_the_opposite_way(self):
        engine, tap = make()
        engine.set_active(True)
        # Cursor was at (500, 400); the real mouse moved right 10 and down 5,
        # so macOS reports (510, 405).
        event = FakeEvent(x=510, y=405, dx=10, dy=5)
        self.assertIs(send(tap, Q.kCGEventMouseMoved, event), event)
        self.assertEqual(Q.warps, [(490, 395)])
        self.assertEqual((event.location.x, event.location.y), (490, 395))
        self.assertEqual((event.fields["dx"], event.fields["dy"]), (-10, -5))

        # Keep moving right: the cursor keeps going left from where WE put it.
        send(tap, Q.kCGEventMouseMoved, FakeEvent(x=500, y=395, dx=10, dy=0))
        self.assertEqual(Q.warps[-1], (480, 395))

    def test_dragging_is_inverted_too(self):
        engine, tap = make()
        engine.set_active(True)
        send(tap, Q.kCGEventLeftMouseDragged, FakeEvent(x=110, y=100, dx=10, dy=0))
        self.assertEqual(Q.warps, [(90, 100)])

    def test_cursor_stays_on_screen(self):
        engine, tap = make()
        engine.set_active(True)
        send(tap, Q.kCGEventMouseMoved, FakeEvent(x=5, y=5, dx=0, dy=0))
        for _ in range(5):
            send(tap, Q.kCGEventMouseMoved, FakeEvent(x=0, y=0, dx=400, dy=400))
        self.assertEqual(Q.warps[-1], (0, 0))
        for _ in range(10):
            send(tap, Q.kCGEventMouseMoved, FakeEvent(x=0, y=0, dx=-400, dy=-400))
        self.assertEqual(Q.warps[-1], (1439, 899))

    def test_normal_scheme_leaves_cursor_alone(self):
        engine, tap = make()
        engine.set_active(True)
        engine.scheme = "normal"
        event = FakeEvent(x=510, y=405, dx=10, dy=5)
        send(tap, Q.kCGEventMouseMoved, event)
        self.assertEqual(Q.warps, [])
        self.assertEqual(tap._pos, [510, 405])


class ClickTests(unittest.TestCase):
    DOWN = property(lambda self: Q.kCGEventLeftMouseDown)
    UP = property(lambda self: Q.kCGEventLeftMouseUp)

    def click(self, tap, x=600, y=600):
        down = send(tap, self.DOWN, FakeEvent(x=x, y=y))
        up = send(tap, self.UP, FakeEvent(x=x, y=y))
        return down is not None, up is not None

    def test_third_click_is_swallowed_press_and_release(self):
        engine, tap = make(captcha=True)
        engine.set_active(True)
        self.assertEqual(self.click(tap), (True, True))
        self.assertEqual(self.click(tap), (True, True))
        self.assertTrue(engine.locked)
        self.assertEqual(self.click(tap), (False, False))
        engine.captcha_solved()
        self.assertEqual(self.click(tap), (True, True))

    def test_clicks_on_our_windows_always_work(self):
        engine, tap = make(captcha=True)
        engine.set_active(True)
        tap.safe_rects = [(100, 100, 300, 400)]
        self.click(tap)
        self.click(tap)
        self.assertTrue(engine.locked)
        self.assertEqual(self.click(tap, x=250, y=300), (True, True))
        self.assertEqual(self.click(tap, x=250, y=80), (True, True), "title bar")
        self.assertEqual(self.click(tap, x=50, y=300), (False, False))

    def test_release_is_dropped_even_if_switched_off_mid_click(self):
        engine, tap = make(captcha=True)
        engine.set_active(True)
        self.click(tap)
        self.click(tap)
        self.assertIsNone(send(tap, self.DOWN, FakeEvent(x=600, y=600)))
        engine.set_active(False)
        self.assertIsNone(send(tap, self.UP, FakeEvent(x=600, y=600)))
        self.assertEqual(self.click(tap), (True, True))


class HotkeyTests(unittest.TestCase):
    def esc(self, tap, repeat=0):
        event = FakeEvent(keycode=config.PANIC_KEYCODE, repeat=repeat)
        return send(tap, Q.kCGEventKeyDown, event), event

    def test_esc_three_times_is_the_emergency_stop(self):
        engine, tap = make()
        engine.set_active(True)
        for _ in range(config.PANIC_PRESSES - 1):
            result, event = self.esc(tap)
            self.assertIs(result, event, "Esc must still reach other apps")
            self.assertTrue(engine.active)
        self.esc(tap)
        self.assertFalse(engine.active)

    def test_holding_esc_does_not_count(self):
        engine, tap = make()
        engine.set_active(True)
        for _ in range(20):
            self.esc(tap, repeat=1)
        self.assertTrue(engine.active)

    def test_control_option_m_toggles(self):
        engine, tap = make()
        flags = Q.kCGEventFlagMaskControl | Q.kCGEventFlagMaskAlternate
        key = FakeEvent(keycode=config.TOGGLE_KEYCODE, flags=flags)
        self.assertIsNone(send(tap, Q.kCGEventKeyDown, key))
        self.assertTrue(engine.active)
        send(tap, Q.kCGEventKeyDown, FakeEvent(keycode=config.TOGGLE_KEYCODE, flags=flags))
        self.assertFalse(engine.active)

    def test_plain_m_is_just_a_letter(self):
        engine, tap = make()
        key = FakeEvent(keycode=config.TOGGLE_KEYCODE)
        self.assertIs(send(tap, Q.kCGEventKeyDown, key), key)
        self.assertFalse(engine.active)


class SafetyTests(unittest.TestCase):
    def test_tap_is_switched_back_on_if_macos_disables_it(self):
        engine, tap = make()
        send(tap, Q.kCGEventTapDisabledByTimeout, None)
        self.assertEqual(Q.reenabled, [True])

    def test_a_bug_never_eats_the_event(self):
        engine, tap = make()
        engine.set_active(True)
        tap._error_printed = True  # keep the test output quiet

        def boom(*args):
            raise RuntimeError("pretend bug")

        engine.move = boom
        event = FakeEvent(x=10, y=10, dx=1, dy=1)
        self.assertIs(send(tap, Q.kCGEventMouseMoved, event), event)


if __name__ == "__main__":
    unittest.main()
