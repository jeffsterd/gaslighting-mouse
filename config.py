"""
config.py — every number you might want to tweak lives here.

Change a value, save, and re-run main.py. Nothing else needs editing.
"""

# ---------------------------------------------------------------- control schemes
# Which scheme the mouse starts in when you press "Start".
#   "normal"   -> behaves like a regular mouse
#   "inverted" -> right goes left, up goes down
START_SCHEME = "inverted"

# Random inversion: every few seconds the mouse flips between normal and
# inverted. The gap between flips is a random number in this range (seconds).
FLIP_MIN_SECONDS = 3.0
FLIP_MAX_SECONDS = 8.0

# ---------------------------------------------------------------- the nudge
# "Gaslighting": when you slow down to land on a target, the cursor quietly
# slides a few pixels away.
NUDGE_MIN_PX = 2
NUDGE_MAX_PX = 10

# How we guess you are approaching a target: you were moving FAST and have now
# slowed down to SLOW (both in pixels per second).
NUDGE_FAST_SPEED = 500
NUDGE_SLOW_SPEED = 160

# Chance (0..1) that a slow-down actually gets nudged. Over a real button
# (detected through the macOS Accessibility API) it is always 100%.
NUDGE_CHANCE = 0.7

# Minimum time between two nudges, so it stays subtle.
NUDGE_COOLDOWN_SECONDS = 0.8

# If the mouse sat still for longer than this, forget the previous speed.
NUDGE_PAUSE_RESET_SECONDS = 0.12

# ---------------------------------------------------------------- CAPTCHA
# After this many clicks the mouse stops clicking until a CAPTCHA is solved.
CLICKS_BEFORE_CAPTCHA = 2

# How many characters the CAPTCHA has.
CAPTCHA_LENGTH = 5

# Letters/digits used. Look-alikes (0/O, 1/I/L) are left out on purpose -
# the mouse is the annoying part, not the CAPTCHA.
CAPTCHA_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# After solving a CAPTCHA there is this chance (0..1) the control scheme is
# re-rolled from CAPTCHA_SCHEMES.
CAPTCHA_SCHEME_CHANGE_CHANCE = 0.6

# Schemes a solved CAPTCHA can pick from. For extra chaos add any of:
#   "mirror_x" (only left/right flipped), "mirror_y" (only up/down flipped),
#   "swapped"  (moving right goes down, moving down goes right)
CAPTCHA_SCHEMES = ["normal", "inverted"]

# ---------------------------------------------------------------- messages
# A reassuring notification pops up every so often (seconds, random in range).
MESSAGE_MIN_SECONDS = 10.0
MESSAGE_MAX_SECONDS = 25.0

# How long a notification stays on screen.
MESSAGE_VISIBLE_SECONDS = 4.5

# Chance (0..1) of an extra, perfectly timed message right after a flip/nudge.
MESSAGE_AFTER_FLIP_CHANCE = 0.35
MESSAGE_AFTER_NUDGE_CHANCE = 0.15

# ---------------------------------------------------------------- hotkeys
# These work from ANY app while the program is running.
#
# Toggle on/off: Control + Option + M
TOGGLE_KEYCODE = 46  # the "M" key

# EMERGENCY EXIT: press Esc this many times within the time window.
# The mouse instantly goes back to normal.
PANIC_KEYCODE = 53  # the "Esc" key
PANIC_PRESSES = 3
PANIC_WINDOW_SECONDS = 1.5
