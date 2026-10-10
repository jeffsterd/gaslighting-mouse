"""
main.py — start here.

    python main.py             run the Gaslighting Mouse (macOS)
    python main.py --preview   open the windows only; the real mouse is untouched

How the pieces fit together:

    engine.py          the rules (what should the cursor do?)        no macOS code
    mac_mouse.py       hooks the real mouse and applies the rules    macOS only
    button_sniffer.py  spots real buttons under the cursor           macOS only
    ui.py              control panel, CAPTCHA, notifications
    config.py          every number you can tweak
    messages.py        every line of text the mouse says
"""

import signal
import sys

from engine import ChaosEngine

PERMISSION_HELP = """
The Gaslighting Mouse needs permission to control the mouse.

  1. Open  System Settings > Privacy & Security > Accessibility
  2. Switch ON the app you are running this from:
       - "Visual Studio Code" if you pressed Run inside VS Code
       - "Terminal" (or iTerm) if you ran it from a terminal
     If it is not in the list, press + and add it.
  3. QUIT that app completely (Cmd+Q) and open it again.
  4. Run main.py again.
"""


def main():
    preview = "--preview" in sys.argv[1:]
    engine = ChaosEngine()
    mouse = None
    sniffer = None

    if not preview and sys.platform != "darwin":
        print("The real-mouse part only works on macOS. Starting in preview mode.")
        preview = True

    if not preview:
        try:
            import mac_mouse
        except ImportError as error:
            print(f"Missing a library: {error}")
            print("Run:  pip install -r requirements.txt")
            return 1

        mouse = mac_mouse.MouseTap(engine)
        allowed = mac_mouse.has_permission(prompt=True)
        if not allowed or not mouse.start():
            print(PERMISSION_HELP)
            return 1

        from button_sniffer import ButtonSniffer

        sniffer = ButtonSniffer(engine, skip=mouse.in_safe_rect)
        sniffer.start()

    # Imported late so a missing tkinter gives a clear message.
    try:
        from ui import App
    except ImportError as error:
        print(f"Could not load the window toolkit (tkinter): {error}")
        print("Install Python from python.org, or run:  brew install python-tk")
        if mouse is not None:
            mouse.stop()
        return 1

    app = App(engine, mouse, sniffer)

    # Ctrl+C in the terminal closes everything cleanly.
    signal.signal(signal.SIGINT, lambda *args: app.root.after(0, app.quit))

    print("Gaslighting Mouse is running. It starts OFF: press Start in the panel.")
    print("Emergency stop from anywhere: press Esc 3 times quickly.")
    try:
        app.run()
    finally:
        # Whatever happens, hand the mouse back.
        engine.set_active(False)
        if mouse is not None:
            mouse.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
