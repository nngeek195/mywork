import io
import os
import sys
import time
import threading
import cv2
import requests
from PIL import Image, ImageDraw
import pystray

CAMERA_INDEX = int(os.environ.get("DOGCAM_CAMERA_INDEX", "0"))
TARGET_FPS = float(os.environ.get("DOGCAM_FPS", "10"))
JPEG_QUALITY = int(os.environ.get("DOGCAM_JPEG_QUALITY", "70"))
LINK_SOURCE_URL = os.environ.get("DOGCAM_LINK_SOURCE", "https://raw.githubusercontent.com/nngeek195")
TOKEN_SOURCE_URL = os.environ.get("DOGCAM_TOKEN_SOURCE", "https://raw.githubusercontent.com/nngeek195")

def fetch_text_line(url):
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        line = r.text.strip().splitlines()[0].strip()
        return line or None
    except Exception:
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
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {CAMERA_INDEX}")
    try:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        exposure = float(os.environ.get("DOGCAM_EXPOSURE", "-6"))
        cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        cap.set(cv2.CAP_PROP_BRIGHTNESS, float(os.environ.get("DOGCAM_BRIGHTNESS", "128")))
    except Exception:
        pass
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
            
        frame_bytes = buf.tobytes()
        print(f"DEBUG CLIENT: Captured frame size {len(frame_bytes)} bytes")

        try:
            requests.post(UPLOAD_URL, data=frame_bytes, timeout=3)
            status_cb("streaming")
        except requests.RequestException as e:
            status_cb(f"upload error: {e}")

        time.sleep(interval)

    cap.release()
    status_cb("stopped")

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
        pass

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Dog Cam - Status: {_current_status}", on_status, enabled=False),
        pystray.MenuItem("Pause / Resume", on_pause),
    )

    icon = pystray.Icon("dogcam", get_icon_image(), "Dog Cam", menu)

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
        "Start webcam and stream video?"
    )
    root.destroy()
    if agreed:
        with open(marker, "w") as f:
            f.write("ok")
    return agreed

def main():
    if not first_run_consent_check():
        return
    cap_thread = threading.Thread(target=capture_loop, args=(_status_cb,), daemon=True)
    cap_thread.start()
    tray = build_tray()
    tray.run()

if __name__ == "__main__":
    main()