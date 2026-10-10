"""
ui.py — everything you can see: the control panel, the CAPTCHA window and
the "everything is fine" notifications.

Built with tkinter, which comes with Python, so there is nothing to install.

The window never talks to the mouse directly. A few times a second it asks
the engine "what is your state?" and redraws itself (see App._poll).
"""

import queue
import random
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

import config
import messages

# Colours
BG = "#14161a"
CARD = "#1f232a"
CARD_HOVER = "#2a2f38"
TEXT = "#eceef1"
MUTED = "#8a909b"
GREEN = "#3ddc84"
RED = "#ff4d6d"
AMBER = "#ffb020"
BLUE = "#4c8dff"

SCHEME_LABELS = {
    "normal": "NORMAL",
    "inverted": "INVERTED",
    "mirror_x": "LEFT/RIGHT FLIPPED",
    "mirror_y": "UP/DOWN FLIPPED",
    "swapped": "AXES SWAPPED",
}

FEATURE_LABELS = [
    ("random_flip", "Random inversion"),
    ("nudge", "Nudge away from targets"),
    ("captcha", f"CAPTCHA every {config.CLICKS_BEFORE_CAPTCHA} clicks"),
    ("messages", "Gaslighting messages"),
]

POLL_MS = 80


def bring_app_to_front():
    """Ask macOS to make our app the active one, so a new window can take
    keyboard focus even if the user is in another app."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass


class App:
    def __init__(self, engine, mouse=None, sniffer=None):
        """mouse is None in preview mode (the real mouse is left alone)."""
        self.engine = engine
        self.mouse = mouse
        self.sniffer = sniffer

        self.captcha = None
        self._toast = None
        self._toast_job = None
        self._next_message_at = None
        self._closed = False

        self.root = tk.Tk()
        self.root.title("The Gaslighting Mouse")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        family = self._pick_font()
        self.f_small = (family, 11)
        self.f_body = (family, 13)
        self.f_bold = (family, 13, "bold")
        self.f_big = (family, 22, "bold")
        self.f_title = (family, 12, "bold")

        self._build_panel()
        self.root.after(POLL_MS, self._poll)

    def _pick_font(self):
        available = set(tkfont.families(self.root))
        for name in ("Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"):
            if name in available:
                return name
        return tkfont.nametofont("TkDefaultFont").actual("family")

    # ------------------------------------------------------------ the panel

    def _build_panel(self):
        outer = tk.Frame(self.root, bg=BG, padx=18, pady=16)
        outer.pack()

        tk.Label(
            outer, text="THE GASLIGHTING MOUSE", bg=BG, fg=MUTED, font=self.f_title
        ).pack(anchor="w")

        if self.mouse is None:
            tk.Label(
                outer,
                text="PREVIEW MODE: your real mouse is not being touched",
                bg=AMBER, fg="#1a1300", font=self.f_small, padx=8, pady=4,
            ).pack(fill="x", pady=(8, 0))

        # Big status line
        self.status = tk.Label(outer, text="", bg=BG, fg=GREEN, font=self.f_big)
        self.status.pack(anchor="w", pady=(10, 0))
        self.status_sub = tk.Label(outer, text="", bg=BG, fg=MUTED, font=self.f_body)
        self.status_sub.pack(anchor="w")

        # Start / stop
        self.toggle_button = self._button(
            outer, "", self.engine.toggle, bg=RED, fg="white", font=self.f_bold, pady=11
        )
        self.toggle_button.pack(fill="x", pady=(12, 14))

        # Current state
        card = tk.Frame(outer, bg=CARD, padx=12, pady=10)
        card.pack(fill="x")
        self.row_scheme = self._row(card, "Controls")
        self.row_clicks = self._row(card, "Clicking")
        self.row_button = self._row(card, "Under cursor") if self.sniffer else None
        self.counters = tk.Label(card, text="", bg=CARD, fg=MUTED, font=self.f_small)
        self.counters.pack(anchor="w", pady=(8, 0))

        # Feature switches
        tk.Label(outer, text="FEATURES", bg=BG, fg=MUTED, font=self.f_title).pack(
            anchor="w", pady=(14, 4)
        )
        self.switches = {}
        for name, label in FEATURE_LABELS:
            self.switches[name] = self._switch(outer, name, label)

        # Demo buttons
        tk.Label(outer, text="DEMO", bg=BG, fg=MUTED, font=self.f_title).pack(
            anchor="w", pady=(14, 4)
        )
        demo = tk.Frame(outer, bg=BG)
        demo.pack(fill="x")
        for column, (text, command) in enumerate(
            [
                ("Flip now", self.engine.flip_now),
                ("CAPTCHA now", self.engine.trigger_captcha),
                ("Message now", self._message_now),
            ]
        ):
            demo.columnconfigure(column, weight=1, uniform="demo")
            self._button(demo, text, command, bg=CARD, fg=TEXT, font=self.f_small).grid(
                row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0)
            )

        # Hotkey reminder
        if self.mouse is not None and not self.mouse.hotkeys_available:
            hint = "Hotkeys unavailable. Use this panel to stop."
        else:
            hint = (
                "Start / stop from any app:  Control + Option + M\n"
                f"Emergency stop:  press Esc {config.PANIC_PRESSES} times quickly"
            )
        tk.Label(
            outer, text=hint, bg=BG, fg=MUTED, font=self.f_small, justify="left"
        ).pack(anchor="w", pady=(14, 0))

    def _button(self, parent, text, command, bg, fg, font, pady=8):
        """A flat clickable label. (Real tk Buttons ignore colours on macOS.)"""
        button = tk.Label(
            parent, text=text, bg=bg, fg=fg, font=font, padx=10, pady=pady,
            cursor="hand2",
        )
        button.bind("<Button-1>", lambda event: command())
        return button

    def _row(self, parent, name):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=2)
        tk.Label(row, text=name, bg=CARD, fg=MUTED, font=self.f_body).pack(side="left")
        value = tk.Label(row, text="", bg=CARD, fg=TEXT, font=self.f_bold)
        value.pack(side="right", padx=(24, 0))
        return value

    def _switch(self, parent, name, label):
        row = tk.Frame(parent, bg=CARD, padx=12, pady=7, cursor="hand2")
        row.pack(fill="x", pady=2)
        text = tk.Label(row, text=label, bg=CARD, fg=TEXT, font=self.f_body)
        text.pack(side="left")
        state = tk.Label(row, text="", bg=CARD, font=self.f_bold, width=4, anchor="e")
        state.pack(side="right", padx=(24, 0))

        def flip(event=None):
            self.engine.set_feature(name, not self.engine.features[name])

        for widget in (row, text, state):
            widget.bind("<Button-1>", flip)
        return state

    # ------------------------------------------------------------ main loop

    def run(self):
        self.root.mainloop()

    def quit(self):
        if self._closed:
            return
        self._closed = True
        self.engine.set_active(False)
        if self.sniffer is not None:
            self.sniffer.stop()
        if self.mouse is not None:
            self.mouse.stop()
        self.root.destroy()

    def _poll(self):
        """Runs ~12 times a second: react to engine events and redraw."""
        if self._closed:
            return
        now = time.monotonic()
        self.engine.tick()

        while True:
            try:
                event = self.engine.events.get_nowait()
            except queue.Empty:
                break
            self._handle(event, now)

        state = self.engine.snapshot()
        self._redraw(state)
        self._sync_captcha(state)
        self._maybe_message(state, now)
        self._publish_window_rects()
        self.root.after(POLL_MS, self._poll)

    def _handle(self, event, now):
        kind = event[0]
        messages_on = self.engine.features["messages"]

        if kind == "active":
            # First message arrives quickly so a demo does not have to wait.
            self._next_message_at = now + random.uniform(4, 8) if event[1] else None
        elif kind == "flip":
            if messages_on and random.random() < config.MESSAGE_AFTER_FLIP_CHANCE:
                self.toast(random.choice(messages.AFTER_FLIP))
        elif kind == "nudge":
            if messages_on and random.random() < config.MESSAGE_AFTER_NUDGE_CHANCE:
                self.toast(random.choice(messages.AFTER_NUDGE))
        elif kind == "blocked":
            if self.captcha is not None:
                self.captcha.demand_attention()
        elif kind == "captcha_solved":
            if messages_on:
                line = random.choice(messages.CAPTCHA_SOLVED)
                self.toast(line.format(n=config.CLICKS_BEFORE_CAPTCHA))
        elif kind == "panic":
            self.toast(messages.PANIC, title="Emergency stop")

    def _redraw(self, state):
        active = state["active"]
        if active:
            self.status.config(text="GASLIGHTING", fg=RED)
            self.status_sub.config(text="The mouse is lying to you.")
            self.toggle_button.config(text="Stop  (mouse back to normal)", bg=CARD_HOVER)
        else:
            self.status.config(text="OFF", fg=GREEN)
            self.status_sub.config(text="The mouse is behaving normally.")
            self.toggle_button.config(text="Start gaslighting", bg=RED)

        scheme = state["scheme"]
        self.row_scheme.config(
            text=SCHEME_LABELS.get(scheme, scheme.upper()),
            fg=TEXT if scheme == "normal" else AMBER,
        )

        if not active:
            self.row_clicks.config(text="allowed", fg=TEXT)
        elif state["locked"]:
            self.row_clicks.config(text="BLOCKED until CAPTCHA", fg=RED)
        elif not state["features"]["captcha"]:
            self.row_clicks.config(text="allowed", fg=TEXT)
        else:
            left = state["clicks_left"]
            self.row_clicks.config(
                text=f"{left} click{'' if left == 1 else 's'} left", fg=TEXT
            )

        if self.row_button is not None:
            over = state["over_button"]
            self.row_button.config(
                text="a button" if over else "nothing special",
                fg=AMBER if over else MUTED,
            )

        stats = state["stats"]
        self.counters.config(
            text=(
                f"Flips {stats['flips']}   Nudges {stats['nudges']}   "
                f"CAPTCHAs {stats['captchas']}   Blocked clicks {stats['blocked']}"
            )
        )

        for name, widget in self.switches.items():
            on = state["features"][name]
            widget.config(text="ON" if on else "OFF", fg=GREEN if on else MUTED)

    def _publish_window_rects(self):
        """Tell the mouse hook where our windows are, so clicks on them are
        never counted or blocked."""
        if self.mouse is None:
            return
        windows = [self.root]
        if self.captcha is not None:
            windows.append(self.captcha.window)
        self.mouse.safe_rects = [
            (w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height())
            for w in windows
        ]

    # ------------------------------------------------------------ CAPTCHA

    def _sync_captcha(self, state):
        if state["locked"] and self.captcha is None:
            self.captcha = CaptchaWindow(self)
        elif not state["locked"] and self.captcha is not None:
            self.captcha.close()
            self.captcha = None

    # ------------------------------------------------------------ messages

    def _maybe_message(self, state, now):
        if not (state["active"] and state["features"]["messages"]):
            return
        if self._next_message_at is None or now < self._next_message_at:
            return
        self._message_now()

    def _message_now(self):
        self.toast(random.choice(messages.GENERAL))
        self._next_message_at = time.monotonic() + random.uniform(
            config.MESSAGE_MIN_SECONDS, config.MESSAGE_MAX_SECONDS
        )

    def toast(self, text, title="Mouse Diagnostics"):
        """A small notification in the top-right corner of the screen."""
        self._close_toast()

        width = 330
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)  # no title bar
        if sys.platform == "darwin":
            try:
                # Float above everything without stealing keyboard focus
                # (the same trick tooltips use on macOS).
                window.tk.call(
                    "::tk::unsupported::MacWindowStyle",
                    "style", window._w, "help", "noActivates",
                )
            except tk.TclError:
                pass
        window.attributes("-topmost", True)
        try:
            window.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        x = self.root.winfo_screenwidth() - width - 18
        window.geometry(f"{width}x10+{x}+44")

        border = tk.Frame(window, bg="#3a404b", padx=1, pady=1)
        border.pack(fill="both", expand=True)
        body = tk.Frame(border, bg=CARD, padx=14, pady=11)
        body.pack(fill="both", expand=True)

        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="●", bg=CARD, fg=GREEN, font=self.f_small).pack(side="left")
        tk.Label(head, text=f" {title}", bg=CARD, fg=TEXT, font=self.f_bold).pack(side="left")
        tk.Label(head, text="now", bg=CARD, fg=MUTED, font=self.f_small).pack(side="right")
        tk.Label(
            body, text=text, bg=CARD, fg=TEXT, font=self.f_body,
            wraplength=width - 34, justify="left",
        ).pack(anchor="w", pady=(5, 0))

        window.update_idletasks()
        window.geometry(f"{width}x{border.winfo_reqheight()}+{x}+44")
        window.lift()

        self._toast = window
        self._toast_job = self.root.after(
            int(config.MESSAGE_VISIBLE_SECONDS * 1000), self._close_toast
        )

    def _close_toast(self):
        if self._toast_job is not None:
            self.root.after_cancel(self._toast_job)
            self._toast_job = None
        if self._toast is not None:
            self._toast.destroy()
            self._toast = None


class CaptchaWindow:
    """The 'prove you are human' window. Type the characters and press
    Return. The keyboard always works, even though clicking does not."""

    WIDTH, HEIGHT = 300, 92

    def __init__(self, app):
        self.app = app
        self.code = ""

        window = self.window = tk.Toplevel(app.root)
        window.title("Human Verification")
        window.configure(bg="#f4f5f7")
        window.resizable(False, False)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", self._refuse_to_close)

        frame = tk.Frame(window, bg="#f4f5f7", padx=22, pady=18)
        frame.pack()

        tk.Label(
            frame, text="Are you human?", bg="#f4f5f7", fg="#15171a",
            font=(app.f_big[0], 18, "bold"),
        ).pack(anchor="w")
        clicks = config.CLICKS_BEFORE_CAPTCHA
        tk.Label(
            frame,
            text=(
                f"You have used your {clicks} free clicks.\n"
                "Type the characters below to keep clicking."
            ),
            bg="#f4f5f7", fg="#5b616b", font=app.f_body, justify="left",
        ).pack(anchor="w", pady=(2, 12))

        self.canvas = tk.Canvas(
            frame, width=self.WIDTH, height=self.HEIGHT, bg="#e3e6ea",
            highlightthickness=1, highlightbackground="#c4c8cf",
        )
        self.canvas.pack()

        entry_row = tk.Frame(frame, bg="#f4f5f7")
        entry_row.pack(fill="x", pady=(12, 0))
        self.answer = tk.StringVar()
        self.entry = tk.Entry(
            entry_row, textvariable=self.answer, font=(app.f_big[0], 18),
            width=10, justify="center", bg="white", fg="#15171a",
            insertbackground="#15171a", relief="solid", borderwidth=1,
        )
        self.entry.pack(side="left", ipady=4)
        self.entry.bind("<Return>", lambda event: self.submit())
        verify = app._button(
            entry_row, "Verify", self.submit, bg=BLUE, fg="white", font=app.f_bold
        )
        verify.pack(side="right")

        self.feedback = tk.Label(
            frame, text="Press Return to submit.", bg="#f4f5f7", fg="#5b616b",
            font=app.f_small, wraplength=self.WIDTH, justify="left",
        )
        self.feedback.pack(anchor="w", pady=(10, 0))

        new_code = tk.Label(
            frame, text="Can't read it? Get a different one", bg="#f4f5f7",
            fg=BLUE, font=app.f_small, cursor="hand2",
        )
        new_code.pack(anchor="w", pady=(4, 0))
        new_code.bind("<Button-1>", lambda event: self.new_code())

        self.new_code()

        # Centre on the main screen.
        window.update_idletasks()
        x = (window.winfo_screenwidth() - window.winfo_reqwidth()) // 2
        y = (window.winfo_screenheight() - window.winfo_reqheight()) // 3
        window.geometry(f"+{x}+{y}")

        self.demand_attention()
        window.after(150, self.demand_attention)

    def new_code(self):
        self.code = "".join(
            random.choice(config.CAPTCHA_ALPHABET) for _ in range(config.CAPTCHA_LENGTH)
        )
        self.answer.set("")
        self._draw()

    def _draw(self):
        canvas = self.canvas
        canvas.delete("all")
        width, height = self.WIDTH, self.HEIGHT
        ink = ["#1f2a44", "#3b2a4a", "#234035", "#4a2f24", "#2b2b2b"]

        # Background speckles
        for _ in range(70):
            x, y = random.uniform(0, width), random.uniform(0, height)
            canvas.create_oval(x, y, x + 2, y + 2, fill="#aeb4bd", outline="")

        # Wobbly letters
        slot = (width - 40) / len(self.code)
        for index, character in enumerate(self.code):
            x = 20 + slot * (index + 0.5) + random.uniform(-4, 4)
            y = height / 2 + random.uniform(-10, 10)
            options = dict(
                text=character, fill=random.choice(ink),
                font=("Courier", random.randint(28, 36), "bold"),
            )
            try:
                canvas.create_text(x, y, angle=random.uniform(-28, 28), **options)
            except tk.TclError:  # very old Tk cannot rotate text
                canvas.create_text(x, y, **options)

        # Lines through the letters
        for _ in range(3):
            canvas.create_line(
                random.uniform(0, width * 0.3), random.uniform(8, height - 8),
                random.uniform(width * 0.4, width * 0.6), random.uniform(8, height - 8),
                random.uniform(width * 0.7, width), random.uniform(8, height - 8),
                smooth=True, fill=random.choice(ink), width=1,
            )

    def submit(self):
        typed = self.answer.get().strip().upper()
        if typed == self.code:
            # The engine unlocks; App._sync_captcha then closes this window.
            self.app.engine.captcha_solved()
        else:
            self.feedback.config(text=random.choice(messages.CAPTCHA_WRONG), fg=RED)
            self.new_code()
            self.entry.focus_set()

    def demand_attention(self):
        """Jump to the front and put the typing cursor in the answer box."""
        bring_app_to_front()
        try:
            self.window.lift()
            self.window.focus_force()
            self.entry.focus_set()
        except tk.TclError:
            pass  # the window was closed in the meantime

    def _refuse_to_close(self):
        self.feedback.config(text=messages.CAPTCHA_NO_CLOSE, fg=RED)

    def close(self):
        self.window.destroy()
