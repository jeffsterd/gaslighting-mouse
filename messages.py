"""
messages.py — things the mouse says to make you doubt yourself.

Add your own! Each list is used at a different moment.
"""

# Shown at random while the chaos is running.
GENERAL = [
    "Your mouse appears to be functioning normally.",
    "No issues detected. Have you tried moving it the right way?",
    "Diagnostics complete: the mouse is fine. Are you?",
    "Pointer accuracy: 100%. User accuracy: under review.",
    "Reminder: left has always been on that side.",
    "Everything is working as intended.",
    "We checked. It's not the mouse.",
    "Your cursor is exactly where you put it.",
    "Tip: confident users rarely miss buttons.",
    "No changes have been made to your mouse settings. Ever.",
    "Other users are not reporting this problem.",
    "Calibration is perfect. Please stop asking.",
]

# Sometimes shown right after the controls flip.
AFTER_FLIP = [
    "No changes have been made to your mouse settings.",
    "Nothing changed just now.",
    "Your mouse has always worked this way.",
    "Direction settings: unchanged since installation.",
]

# Sometimes shown right after the cursor is nudged off a target.
AFTER_NUDGE = [
    "Looks like you missed. It happens.",
    "The button did not move. Neither did the cursor.",
    "Try aiming more carefully next time.",
]

# Shown when a CAPTCHA is solved.
CAPTCHA_SOLVED = [
    "Thank you, human. You may now click {n} more times.",
    "Verified. Enjoy your {n} complimentary clicks.",
]

# Shown inside the CAPTCHA window when the answer is wrong.
CAPTCHA_WRONG = [
    "Incorrect. Clicking privileges remain suspended.",
    "That is not what it says. Try again.",
    "Hmm. A human would have got that.",
]

# Shown when someone tries to close the CAPTCHA window.
CAPTCHA_NO_CLOSE = "This window cannot be closed by an unverified user."

# Shown after the emergency exit.
PANIC = "Emergency stop received. The mouse is back to normal (for real)."
