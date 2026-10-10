"""
Tests for the rules in engine.py. They run on any computer:

    python -m unittest discover -s tests -v
"""

import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from engine import ChaosEngine


class FakeClock:
    """A clock we can move forward by hand."""

    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make_engine(seed=1, **features):
    clock = FakeClock()
    engine = ChaosEngine(rng=random.Random(seed), clock=clock)
    # Tests switch features on one at a time.
    for name in engine.features:
        engine.features[name] = features.get(name, False)
    return engine, clock


def drain(engine):
    events = []
    while not engine.events.empty():
        events.append(engine.events.get())
    return events


class MovementTests(unittest.TestCase):
    def test_off_means_untouched(self):
        engine, _ = make_engine()
        self.assertEqual(engine.move(7, -3), (7, -3))

    def test_inverted_reverses_both_directions(self):
        engine, _ = make_engine()
        engine.set_active(True)
        self.assertEqual(engine.scheme, "inverted")
        self.assertEqual(engine.move(7, -3), (-7, 3))

    def test_other_schemes(self):
        engine, _ = make_engine()
        engine.set_active(True)
        expected = {
            "normal": (7, -3),
            "mirror_x": (-7, -3),
            "mirror_y": (7, 3),
            "swapped": (-3, 7),
        }
        for scheme, result in expected.items():
            engine.scheme = scheme
            self.assertEqual(engine.move(7, -3), result, scheme)

    def test_switching_off_restores_normal(self):
        engine, _ = make_engine()
        engine.set_active(True)
        engine.set_active(False)
        self.assertEqual(engine.scheme, "normal")
        self.assertEqual(engine.move(5, 5), (5, 5))


class RandomFlipTests(unittest.TestCase):
    def test_flips_within_the_configured_window(self):
        engine, clock = make_engine(random_flip=True)
        engine.set_active(True)
        start = clock.now

        clock.now = start + config.FLIP_MIN_SECONDS - 0.01
        engine.tick()
        self.assertEqual(engine.scheme, "inverted", "flipped too early")

        clock.now = start + config.FLIP_MAX_SECONDS + 0.01
        engine.tick()
        self.assertEqual(engine.scheme, "normal", "did not flip in time")
        self.assertIn(("flip", "normal"), drain(engine))

    def test_keeps_flipping_back_and_forth(self):
        engine, clock = make_engine(random_flip=True)
        engine.set_active(True)
        seen = []
        for _ in range(400):
            clock.now += 0.1
            engine.tick()
            seen.append(engine.scheme)
        self.assertGreaterEqual(engine.stats["flips"], 4)
        self.assertEqual(set(seen), {"normal", "inverted"})

    def test_no_flips_when_feature_is_off(self):
        engine, clock = make_engine(random_flip=False)
        engine.set_active(True)
        clock.now += 60
        engine.tick()
        self.assertEqual(engine.scheme, "inverted")


class ClickTests(unittest.TestCase):
    def test_locks_after_two_clicks_until_captcha(self):
        engine, _ = make_engine(captcha=True)
        engine.set_active(True)
        self.assertTrue(engine.click())
        self.assertFalse(engine.locked)
        self.assertTrue(engine.click(), "the 2nd click itself still works")
        self.assertTrue(engine.locked)
        self.assertFalse(engine.click(), "3rd click must be blocked")
        self.assertFalse(engine.click())
        self.assertEqual(engine.stats["blocked"], 2)

        engine.captcha_solved()
        self.assertFalse(engine.locked)
        self.assertTrue(engine.click())
        self.assertEqual(engine.snapshot()["clicks_left"], 1)

    def test_our_own_windows_are_always_clickable(self):
        engine, _ = make_engine(captcha=True)
        engine.set_active(True)
        for _ in range(10):
            self.assertTrue(engine.click(exempt=True))
        self.assertFalse(engine.locked, "exempt clicks must not be counted")
        engine.click()
        engine.click()
        self.assertTrue(engine.locked)
        self.assertTrue(engine.click(exempt=True), "still clickable when locked")

    def test_never_blocks_when_off(self):
        engine, _ = make_engine(captcha=True)
        for _ in range(10):
            self.assertTrue(engine.click())

    def test_captcha_can_change_the_scheme(self):
        schemes = set()
        for seed in range(40):
            engine, _ = make_engine(seed=seed, captcha=True)
            engine.set_active(True)
            engine.click()
            engine.click()
            engine.captcha_solved()
            schemes.add(engine.scheme)
            self.assertIn(engine.scheme, set(config.CAPTCHA_SCHEMES) | {"inverted"})
        self.assertEqual(schemes, {"normal", "inverted"})

    def test_panic_unlocks_everything(self):
        engine, _ = make_engine(captcha=True)
        engine.set_active(True)
        engine.click()
        engine.click()
        engine.panic()
        self.assertFalse(engine.active)
        self.assertFalse(engine.locked)
        self.assertTrue(engine.click())
        self.assertEqual(engine.move(4, 4), (4, 4))
        self.assertIn(("panic",), drain(engine))


class NudgeTests(unittest.TestCase):
    def approach(self, engine, clock):
        """Simulate a hand moving right: fast at first, then slowing down
        onto a target. Returns the extra movement the engine added."""
        engine.scheme = "normal"
        extra = []
        speeds = [1500] * 12 + [900, 500, 300, 150, 80, 60, 40, 30, 20, 20]
        for speed in speeds:
            clock.now += 0.01
            dx = speed * 0.01
            out_x, out_y = engine.move(dx, 0)
            extra.append((out_x - dx, out_y))
        return [e for e in extra if e != (0.0, 0.0)]

    def test_nudges_when_slowing_onto_a_target(self):
        engine, clock = make_engine(nudge=True)
        engine.set_active(True)
        engine.over_button = True  # makes the nudge certain
        nudges = self.approach(engine, clock)
        self.assertEqual(len(nudges), 1, "exactly one nudge per approach")
        size = math.hypot(*nudges[0])
        self.assertGreaterEqual(size, config.NUDGE_MIN_PX)
        self.assertLessEqual(size, config.NUDGE_MAX_PX)
        self.assertLess(nudges[0][0], 0, "should push back against the motion")

    def test_nudge_size_always_in_range(self):
        for seed in range(50):
            engine, clock = make_engine(seed=seed, nudge=True)
            engine.set_active(True)
            engine.over_button = True
            for nudge in self.approach(engine, clock):
                size = math.hypot(*nudge)
                self.assertTrue(
                    config.NUDGE_MIN_PX <= size <= config.NUDGE_MAX_PX, size
                )

    def test_slow_careful_movement_is_left_alone(self):
        engine, clock = make_engine(nudge=True)
        engine.set_active(True)
        engine.over_button = True
        engine.scheme = "normal"
        for _ in range(200):
            clock.now += 0.01
            self.assertEqual(engine.move(1, 0), (1, 0))

    def test_no_nudge_when_feature_is_off(self):
        engine, clock = make_engine(nudge=False)
        engine.set_active(True)
        engine.over_button = True
        self.assertEqual(self.approach(engine, clock), [])


if __name__ == "__main__":
    unittest.main()
