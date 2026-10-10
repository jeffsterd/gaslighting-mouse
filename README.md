# The Gaslighting Mouse

A macOS app that takes over your **real** mouse and quietly makes it worse,
while insisting everything is fine.

| Feature | What happens |
| --- | --- |
| Inverted controls | Move right, cursor goes left. Move up, cursor goes down. |
| Random inversion | Every 3-8 seconds it flips between normal and inverted. |
| Gaslighting nudge | When you slow down onto a target, the cursor slides 2-10 px away. |
| Click counter | After 2 clicks, clicking stops working. |
| CAPTCHA | Solve it to click again. Solving it may change the control scheme. |
| Messages | "Your mouse appears to be functioning normally." |

It starts **OFF**. Nothing happens to your mouse until you press Start.

## Emergency exit

- **Press Esc 3 times quickly**: everything switches off, from any app.
- **Control + Option + M**: start / stop from any app.
- Quit the program (close the panel, or Ctrl+C in the terminal). The moment
  Python stops, macOS removes the hook and the mouse is normal again.

The keyboard is never altered, so these always work.

## Setup in VS Code (about 5 minutes)

1. Open this folder in VS Code (**File > Open Folder**).
2. Install the **Python** extension if VS Code offers it.
3. Open a terminal in VS Code (**Terminal > New Terminal**) and run:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Try the windows first, without touching the mouse:

   ```bash
   python main.py --preview
   ```

5. Run the real thing:

   ```bash
   python main.py
   ```

   The first time, macOS will say the app wants to control your computer.
   Go to **System Settings > Privacy & Security > Accessibility** and switch
   on **Visual Studio Code** (or **Terminal**, if you ran it there). Then
   **quit VS Code completely (Cmd+Q)**, reopen it, and run again. macOS only
   notices the new permission after a restart.

You can also press **F5** (two run configurations are included), but prefer
**Ctrl+F5 "Run Without Debugging"** or the terminal for the real thing. The
debugger slows the mouse hook down and the cursor gets laggy.

### If something does not work

| Problem | Fix |
| --- | --- |
| `No module named 'tkinter'` | Use Python from python.org, or `brew install python-tk`. |
| It prints the permission help every time | The permission is on the wrong app, or the app was not restarted. Remove it from the Accessibility list, add it again, Cmd+Q, reopen. |
| Hotkeys do nothing | Also switch the app on under **Privacy & Security > Input Monitoring**, then restart it. |
| Cursor flickers while inverted | Expected to a small degree: macOS draws the real position for an instant before we move it. |
| Nudge fires too often / never | Tune `NUDGE_FAST_SPEED` and `NUDGE_SLOW_SPEED` in `config.py`. |

## The files

| File | What it does |
| --- | --- |
| `main.py` | Start here. Wires everything together. |
| `config.py` | Every number you can tweak (timings, pixels, hotkeys). |
| `messages.py` | Every line the mouse says. Add your own. |
| `engine.py` | The rules: schemes, random flips, nudge, click counter. No macOS code. |
| `mac_mouse.py` | Hooks the real mouse with a Quartz event tap and applies the rules. |
| `button_sniffer.py` | Uses the Accessibility API to spot real buttons under the cursor. |
| `ui.py` | Control panel, CAPTCHA window, notifications (tkinter). |
| `tests/` | Automated checks. Run with `python -m unittest discover -s tests -v`. |

## How it works

```
 real mouse ──> macOS ──> [ mac_mouse.py event tap ] ──> every app
                                   │   ▲
                     "moved 10,5"  ▼   │  "move -10,-5 instead"
                              [ engine.py ]
                                   │
                           state + events
                                   ▼
                               [ ui.py ]
```

- **Event tap.** macOS lets a trusted program see every mouse event before
  any app does, and change or drop it. That is what the Accessibility
  permission is for.
- **Inversion.** Each movement event says how far the real mouse moved. We
  keep our own idea of where the cursor is, add the *flipped* movement to it,
  teleport the cursor there, and rewrite the event so apps agree.
- **Nudge.** People move fast towards a target and slow down to land on it.
  When the engine sees fast-then-slow, it pushes the cursor a few pixels back.
  If the Accessibility API reports a real button under the cursor, the nudge
  is guaranteed instead of a 70% chance.
- **Click lock.** Clicks are counted. After the second one, press and release
  events are dropped before any app sees them. Clicks on our own windows are
  always allowed, so you can still solve the CAPTCHA and press Stop.
- **Threads.** The hook runs on its own thread so the cursor stays smooth.
  The window polls the engine about 12 times a second and redraws.

## Demo tips

- The panel has **Flip now**, **CAPTCHA now** and **Message now** buttons so
  you are not waiting on random timers in front of the judges.
- Switch features off in the panel and turn them on one at a time to show
  each one separately.
- Use **Control + Option + M** to hand the mouse to a judge, and again to
  rescue them.

## What has and has not been tested

This was written and checked on Linux, not on a Mac.

- **Tested:** all the rules in `engine.py`; the logic of `mac_mouse.py`
  against a stand-in for macOS (30 automated tests); the panel, CAPTCHA and
  notifications, run for real in a virtual display.
- **Checked but not run:** every macOS function used was verified to exist,
  with the expected arguments, in the current `pyobjc` package.
- **Not tested:** the actual behaviour on a real Mac: cursor smoothness,
  the permission flow, how the windows look, and button detection. Expect to
  tune a number or two in `config.py` on first run.

## Packaging as a .app (optional, untested)

```bash
pip install pyinstaller
pyinstaller --windowed --name "Gaslighting Mouse" main.py
```

The app appears in `dist/`. It needs its **own** entry under Accessibility
(add `Gaslighting Mouse.app`), and rebuilding it can reset that permission.
For a hackathon demo, running from VS Code is the safer choice.
