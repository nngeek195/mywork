"""
Dog-cam client -- runs on the Windows laptop near the dog.

- Opens the built-in webcam
- Forces manual exposure (fixes the "everything is white" washout problem)
- Streams JPEG frames to your Flask server over HTTP
- Shows a visible, ALWAYS-ON system tray icon while running. This is
  intentional and not configurable: a camera script with no on-screen
  indicator is spyware, even on your own hardware, if anyone else ever
  uses the machine -- that's the line between a monitoring tool and
  something that records people without their knowledge.
- The tray menu has "Pause" but NOT "Quit". This is the fix for the
  actual problem (someone closing it by accident/on purpose) without
  making the camera invisible: the icon is still there, still labeled,
  still shows status -- it just can't be stopped from the tray. Stop it
  from Task Manager if you need to.

Install once:
    pip install opencv-python requests pystray pillow

Run manually:
    set DOGCAM_TOKEN=your-long-random-string
    set DOGCAM_SERVER=https://your-tunnel-url.example.com
    python webcam_client.py

Enable auto-start on login:
    python webcam_client.py --install-autostart
Remove auto-start:
    python webcam_client.py --uninstall-autostart
"""

import io
import os
import sys
import time
import threading

import cv2
import requests
from PIL import Image, ImageDraw
import pystray

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CAMERA_INDEX = int(os.environ.get("DOGCAM_CAMERA_INDEX", "0"))
TARGET_FPS = float(os.environ.get("DOGCAM_FPS", "10"))
JPEG_QUALITY = int(os.environ.get("DOGCAM_JPEG_QUALITY", "70"))

LINK_SOURCE_URL = os.environ.get(
    "DOGCAM_LINK_SOURCE",
    "https://raw.githubusercontent.com/nngeek195/mywork/main/link.txt",
)
TOKEN_SOURCE_URL = os.environ.get(
    "DOGCAM_TOKEN_SOURCE",
    "https://raw.githubusercontent.com/nngeek195/mywork/main/token.txt",
)


def fetch_text_line(url):
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        line = r.text.strip().splitlines()[0].strip()
        return line or None
    except Exception as e:
        print(f"Could not fetch {url}: {e}")
        return None


def fetch_server_url():
    url = fetch_text_line(LINK_SOURCE_URL)
    if url and (url.startswith("http://") or url.startswith("https://")):
        return url
    return None


def fetch_auth_token():
    return fetch_text_line(TOKEN_SOURCE_URL)


SERVER_URL = fetch_server_url() or os.environ.get("DOGCAM_SERVER", "http://localhost:8000")
AUTH_TOKEN = fetch_auth_token() or os.environ.get("DOGCAM_TOKEN", "changeme-please")
UPLOAD_URL = f"{SERVER_URL.rstrip('/')}/upload?token={AUTH_TOKEN}"


_running = threading.Event()
_running.set()
_paused = threading.Event()


def open_camera():
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {CAMERA_INDEX}")
    try:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        exposure = float(os.environ.get("DOGCAM_EXPOSURE", "-6"))
        cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        cap.set(cv2.CAP_PROP_BRIGHTNESS, float(os.environ.get("DOGCAM_BRIGHTNESS", "128")))
    except Exception as e:
        print(f"Warning: could not set manual exposure ({e}). Continuing with auto-exposure.")
    return cap


def capture_loop(status_cb):
    cap = open_camera()
    interval = 1.0 / TARGET_FPS
    fail_count = 0

    while _running.is_set():
        if _paused.is_set():
            status_cb("paused")
            time.sleep(0.5)
            continue

        ok, frame = cap.read()
        if not ok:
            fail_count += 1
            status_cb(f"camera read failed ({fail_count})")
            time.sleep(1)
            if fail_count > 10:
                cap.release()
                cap = open_camera()
                fail_count = 0
            continue
        fail_count = 0

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            continue

        try:
            requests.post(UPLOAD_URL, data=buf.tobytes(), timeout=3)
            status_cb("streaming")
        except requests.RequestException as e:
            status_cb(f"upload error: {e}")

        time.sleep(interval)

    cap.release()
    status_cb("stopped")


# ---------------------------------------------------------------------------
# System tray icon -- always visible, no Quit option.
# ---------------------------------------------------------------------------
def make_icon_image(color):
    img = Image.new("RGB", (64, 64), color)
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill="white")
    return img


_current_status = "starting"


def _status_cb(text):
    global _current_status
    _current_status = text


def build_tray():
    icon_running = make_icon_image("green")
    icon_paused = make_icon_image("orange")
    icon_error = make_icon_image("red")

    def get_icon_image():
        if _paused.is_set():
            return icon_paused
        if "error" in _current_status or "failed" in _current_status:
            return icon_error
        return icon_running

    def on_pause(icon, item):
        if _paused.is_set():
            _paused.clear()
        else:
            _paused.set()
        icon.icon = get_icon_image()

    def on_status(icon, item):
        pass  # label only, no-op

    # NOTE: intentionally no "Quit" menu item. Stop via Task Manager.
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Dog Cam - Status: {_current_status}", on_status, enabled=False),
        pystray.MenuItem("Pause / Resume", on_pause),
    )

    icon = pystray.Icon("dogcam", get_icon_image(), "Dog Cam (running)", menu)

    def refresher():
        while _running.is_set():
            icon.icon = get_icon_image()
            icon.title = f"Dog Cam ({_current_status})"
            time.sleep(2)

    threading.Thread(target=refresher, daemon=True).start()
    return icon


def first_run_consent_check():
    marker = os.path.join(os.path.expanduser("~"), ".dogcam_consent_given")
    if os.path.exists(marker):
        return True

    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    agreed = messagebox.askyesno(
        "Dog Cam - Permission",
        "This app will turn on this computer's webcam and stream live "
        "video to a remote viewer whenever it's running.\n\n"
        "A tray icon will always be visible while it's active. It can "
        "be paused from the tray, but only stopped via Task Manager.\n\n"
        "Continue?",
    )
    root.destroy()
    if agreed:
        with open(marker, "w") as f:
            f.write("ok")
    return agreed


# ---------------------------------------------------------------------------
# Auto-start on login (Windows Startup folder shortcut)
# ---------------------------------------------------------------------------
def _startup_folder():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA not set -- are you on Windows?")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def install_autostart():
    """Creates a .lnk in the Startup folder that runs this script with pythonw.exe
    (no console window) every time the current user logs in."""
    try:
        import win32com.client  # from pywin32
    except ImportError:
        print("This needs pywin32. Install it with: pip install pywin32")
        sys.exit(1)

    script_path = os.path.abspath(__file__)
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable  # fallback, will show a console

    shortcut_path = os.path.join(_startup_folder(), "DogCam.lnk")

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = pythonw
    shortcut.Arguments = f'"{script_path}"'
    shortcut.WorkingDirectory = os.path.dirname(script_path)
    shortcut.IconLocation = pythonw
    shortcut.Description = "Dog Cam - starts webcam stream at login"
    shortcut.save()

    print(f"Auto-start installed: {shortcut_path}")
    print("Dog Cam will now launch automatically at every login, tray icon and all.")


def uninstall_autostart():
    shortcut_path = os.path.join(_startup_folder(), "DogCam.lnk")
    if os.path.exists(shortcut_path):
        os.remove(shortcut_path)
        print(f"Removed: {shortcut_path}")
    else:
        print("No auto-start shortcut found.")


def main():
    if "--install-autostart" in sys.argv:
        install_autostart()
        return
    if "--uninstall-autostart" in sys.argv:
        uninstall_autostart()
        return

    if AUTH_TOKEN == "changeme-please":
        print("WARNING: DOGCAM_TOKEN is not set. Set it before running for real.")

    if not first_run_consent_check():
        return

    cap_thread = threading.Thread(target=capture_loop, args=(_status_cb,), daemon=True)
    cap_thread.start()

    tray = build_tray()
    tray.run()


if __name__ == "__main__":
    main()