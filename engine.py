"""
engine.py — the brain of the Gaslighting Mouse.

This file contains NO macOS code. It only answers questions like:

    "The real mouse moved by (dx, dy). Where should the cursor go instead?"
    "The user clicked. Is that click allowed?"

Keeping the rules separate from the operating-system plumbing means we can
unit test them on any computer (see tests/test_engine.py) and the scary
low-level code in mac_mouse.py stays small.
"""

import math
import queue
import random
import threading
import time

import config

# A control scheme is a tiny 2x2 grid of numbers that says how real movement
# turns into cursor movement:
#
#     cursor_dx = a * mouse_dx + b * mouse_dy
#     cursor_dy = c * mouse_dx + d * mouse_dy
#
#                 ((a, b), (c, d))
SCHEMES = {
    "normal":   ((1, 0), (0, 1)),
    "inverted": ((-1, 0), (0, -1)),
    "mirror_x": ((-1, 0), (0, 1)),
    "mirror_y": ((1, 0), (0, -1)),
    "swapped":  ((0, 1), (1, 0)),
}

FEATURES = ("random_flip", "nudge", "captcha", "messages")


class ChaosEngine:
    def __init__(self, rng=None, clock=time.monotonic):
        # rng and clock can be swapped out in tests so results are predictable.
        self.rng = rng or random.Random()
        self.clock = clock

        # The mouse hook and the window run on different threads and both
        # touch this object, so every public method takes this lock first.
        self._lock = threading.RLock()

        # Things that happened, for the UI to react to (show a message, etc).
        # Each item is a tuple like ("flip", "inverted").
        self.events = queue.Queue()

        self.active = False
        self.scheme = "normal"
        self.features = {name: True for name in FEATURES}

        # Click counter / CAPTCHA lock.
        self.clicks = 0
        self.locked = False

        # Set by button_sniffer.py when the cursor is over a real button.
        self.over_button = False

        self.stats = {"flips": 0, "nudges": 0, "captchas": 0, "blocked": 0}

        self._next_flip_at = 0.0
        self._reset_motion()

    # ------------------------------------------------------------ on / off

    def set_active(self, on):
        """Start or stop the chaos. While off, the mouse is 100% normal."""
        with self._lock:
            on = bool(on)
            if on == self.active:
                return
            self.active = on
            self.locked = False
            self.clicks = 0
            self._reset_motion()
            if on:
                self.scheme = config.START_SCHEME
                self._schedule_flip(self.clock())
            else:
                self.scheme = "normal"
            self.events.put(("active", on))

    def toggle(self):
        with self._lock:
            self.set_active(not self.active)

    def panic(self):
        """Emergency exit: everything off, right now."""
        with self._lock:
            self.set_active(False)
            self.events.put(("panic",))

    def set_feature(self, name, on):
        with self._lock:
            self.features[name] = bool(on)
            if name == "random_flip" and on:
                self._schedule_flip(self.clock())
            if name == "captcha" and not on:
                self.locked = False
                self.clicks = 0

    # ------------------------------------------------------------ movement

    def move(self, dx, dy, now=None):
        """
        The real mouse moved by (dx, dy) pixels.
        Returns the (dx, dy) the cursor should move by instead.
        """
        with self._lock:
            if not self.active:
                return dx, dy
            if now is None:
                now = self.clock()
            self._tick(now)

            (a, b), (c, d) = SCHEMES[self.scheme]
            out_x = a * dx + b * dy
            out_y = c * dx + d * dy

            nudge_x, nudge_y = self._maybe_nudge(out_x, out_y, now)
            return out_x + nudge_x, out_y + nudge_y

    def tick(self, now=None):
        """Called regularly by the UI so timed flips happen even when the
        mouse is sitting still."""
        with self._lock:
            if self.active:
                self._tick(self.clock() if now is None else now)

    def flip_now(self):
        """Flip between normal and inverted immediately (demo button)."""
        with self._lock:
            if self.active:
                self._flip(self.clock())

    def _tick(self, now):
        if self.features["random_flip"] and now >= self._next_flip_at:
            self._flip(now)

    def _flip(self, now):
        self.scheme = "inverted" if self.scheme == "normal" else "normal"
        self.stats["flips"] += 1
        self._schedule_flip(now)
        self.events.put(("flip", self.scheme))

    def _schedule_flip(self, now):
        self._next_flip_at = now + self.rng.uniform(
            config.FLIP_MIN_SECONDS, config.FLIP_MAX_SECONDS
        )

    # ------------------------------------------------------------ the nudge

    def _reset_motion(self):
        self._last_move_at = None
        self._speed = 0.0          # smoothed cursor speed, pixels per second
        self._was_fast = False     # were we recently moving quickly?
        self._heading = (0.0, 0.0)  # smoothed direction of travel
        self._nudge_ready_at = 0.0

    def _maybe_nudge(self, out_x, out_y, now):
        """
        People move the mouse fast towards a target and then slow down to
        land on it. When we see fast-then-slow, we shove the cursor a few
        pixels back the way it came.
        """
        last = self._last_move_at
        self._last_move_at = now
        if not self.features["nudge"]:
            return 0.0, 0.0

        distance = math.hypot(out_x, out_y)
        if last is None or now - last > config.NUDGE_PAUSE_RESET_SECONDS:
            # The mouse was resting. Start measuring from scratch.
            self._speed = 0.0
            self._was_fast = False
            return 0.0, 0.0

        # Events can arrive in bursts; never divide by a near-zero time gap.
        elapsed = max(now - last, 0.004)
        self._speed = 0.5 * self._speed + 0.5 * (distance / elapsed)
        if distance > 0:
            hx, hy = self._heading
            self._heading = (
                0.6 * hx + 0.4 * out_x / distance,
                0.6 * hy + 0.4 * out_y / distance,
            )

        if self._speed >= config.NUDGE_FAST_SPEED:
            self._was_fast = True
            return 0.0, 0.0

        slowing_onto_target = (
            self._was_fast
            and self._speed <= config.NUDGE_SLOW_SPEED
            and now >= self._nudge_ready_at
        )
        if not slowing_onto_target:
            return 0.0, 0.0

        self._was_fast = False
        chance = 1.0 if self.over_button else config.NUDGE_CHANCE
        if self.rng.random() >= chance:
            return 0.0, 0.0

        pixels = self.rng.uniform(config.NUDGE_MIN_PX, config.NUDGE_MAX_PX)
        hx, hy = self._heading
        # Back the way we came, give or take 60 degrees so it is not an
        # obvious bounce.
        angle = math.atan2(-hy, -hx) + self.rng.uniform(-math.pi / 3, math.pi / 3)
        self._nudge_ready_at = now + config.NUDGE_COOLDOWN_SECONDS
        self.stats["nudges"] += 1
        self.events.put(("nudge", round(pixels, 1)))
        return pixels * math.cos(angle), pixels * math.sin(angle)

    # ------------------------------------------------------------ clicks

    def click(self, exempt=False):
        """
        The user pressed a mouse button. Returns True if the click may go
        through, False if it must be swallowed.

        exempt=True is used for clicks on our own windows (the control panel
        and the CAPTCHA) so you can always switch the thing off.
        """
        with self._lock:
            if not self.active or exempt:
                return True
            if self.locked:
                self.stats["blocked"] += 1
                self.events.put(("blocked",))
                return False
            if not self.features["captcha"]:
                return True
            self.clicks += 1
            if self.clicks >= config.CLICKS_BEFORE_CAPTCHA:
                self.locked = True
                self.events.put(("captcha",))
            return True

    def trigger_captcha(self):
        """Force the CAPTCHA right now (demo button)."""
        with self._lock:
            if self.active:
                self.locked = True
                self.events.put(("captcha",))

    def captcha_solved(self):
        """The CAPTCHA was answered correctly: clicking works again... and
        the control scheme might have quietly changed."""
        with self._lock:
            if not self.locked:
                return
            self.locked = False
            self.clicks = 0
            self.stats["captchas"] += 1
            changed = False
            if self.rng.random() < config.CAPTCHA_SCHEME_CHANGE_CHANCE:
                new_scheme = self.rng.choice(config.CAPTCHA_SCHEMES)
                changed = new_scheme != self.scheme
                self.scheme = new_scheme
                self._schedule_flip(self.clock())
            self.events.put(("captcha_solved", changed))

    # ------------------------------------------------------------ for the UI

    def snapshot(self):
        """A copy of the current state that is safe to read from the UI."""
        with self._lock:
            return {
                "active": self.active,
                "scheme": self.scheme,
                "locked": self.locked,
                "clicks_left": max(0, config.CLICKS_BEFORE_CAPTCHA - self.clicks),
                "over_button": self.over_button,
                "features": dict(self.features),
                "stats": dict(self.stats),
            }
