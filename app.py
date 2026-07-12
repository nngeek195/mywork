"""
Dog-cam viewer server.

Runs on YOUR viewing machine (or a small cloud/VPS box, or the same machine
you browse from). The client script (on the OTHER computer, next to the dog)
pushes JPEG frames to this server over HTTP POST. This server re-serves them
as a live MJPEG stream to a simple web page.

Run:
    pip install flask
    python app.py

Then open http://localhost:8000/  (or your Cloudflare tunnel URL) in a browser.
"""

import os
import threading
import time
from flask import Flask, Response, request, render_template_string, abort

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Shared secret. Anyone who has this token can push frames to your stream OR
# view it. Since this will be exposed to the public internet via Cloudflare,
# treat it like a password. Set it via environment variable, don't hardcode.
#   Windows (client machine):  set DOGCAM_TOKEN=your-long-random-string
#   Mac/Linux (server):        export DOGCAM_TOKEN=your-long-random-string
# ---------------------------------------------------------------------------
AUTH_TOKEN = os.environ.get("DOGCAM_TOKEN", "changeme-please")

# Latest frame lives in memory, protected by a lock. No disk writes, no
# persistence -- purely a live pass-through.
_frame_lock = threading.Lock()
_latest_frame = None
_last_frame_time = 0.0


def check_token(req):
    token = req.args.get("token") or req.headers.get("X-Auth-Token")
    if token != AUTH_TOKEN:
        abort(401, description="Bad or missing token")


@app.route("/upload", methods=["POST"])
def upload():
    """Client posts one JPEG frame per request here."""
    check_token(request)
    global _latest_frame, _last_frame_time
    data = request.get_data()
    if not data:
        abort(400, description="Empty body")
    with _frame_lock:
        _latest_frame = data
        _last_frame_time = time.time()
    return "", 204


def _mjpeg_generator():
    boundary = b"--frame"
    while True:
        with _frame_lock:
            frame = _latest_frame
            age = time.time() - _last_frame_time if _last_frame_time else None
        if frame is None or (age is not None and age > 10):
            # No recent frame -- send a tiny sleep so we don't busy-loop.
            time.sleep(0.5)
            continue
        yield (
            boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
            + frame + b"\r\n"
        )
        time.sleep(0.05)  # cap relay rate ~20fps


@app.route("/video_feed")
def video_feed():
    check_token(request)
    return Response(
        _mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/status")
def status():
    check_token(request)
    with _frame_lock:
        age = time.time() - _last_frame_time if _last_frame_time else None
    online = age is not None and age < 10
    return {"online": online, "last_frame_seconds_ago": age}


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dog Cam</title>
<style>
  :root {
    --bg: #14171c;
    --panel: #1c2027;
    --accent: #ff9f4a;
    --text: #e8e6e1;
    --muted: #8b909a;
    --ok: #5fd18b;
    --off: #e0616b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 100vh;
    padding: 24px 16px;
  }
  h1 {
    font-size: 1.1rem;
    letter-spacing: 0.02em;
    color: var(--muted);
    text-transform: uppercase;
    margin: 0 0 16px 0;
    font-weight: 600;
  }
  .frame {
    width: 100%;
    max-width: 900px;
    background: var(--panel);
    border-radius: 12px;
    padding: 12px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.4);
  }
  img {
    width: 100%;
    display: block;
    border-radius: 6px;
    background: #000;
  }
  .status {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
    font-size: 0.85rem;
    color: var(--muted);
  }
  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--off);
  }
  .dot.on { background: var(--ok); }
</style>
</head>
<body>
  <h1>Dog Cam &mdash; Live</h1>
  <div class="frame">
    <img id="stream" src="/video_feed?token={{ token }}" alt="live stream">
    <div class="status">
      <span class="dot" id="dot"></span>
      <span id="status_text">checking connection&hellip;</span>
    </div>
  </div>
<script>
async function poll() {
  try {
    const r = await fetch('/status?token={{ token }}');
    const j = await r.json();
    const dot = document.getElementById('dot');
    const t = document.getElementById('status_text');
    if (j.online) {
      dot.classList.add('on');
      t.textContent = 'Live';
    } else {
      dot.classList.remove('on');
      t.textContent = 'No recent frames from camera machine';
    }
  } catch (e) {
    document.getElementById('status_text').textContent = 'Connection error';
  }
}
setInterval(poll, 3000);
poll();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    check_token(request)
    return render_template_string(PAGE, token=AUTH_TOKEN)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Dog cam server starting on port {port}")
    print(f"Token in use: {AUTH_TOKEN}")
    if AUTH_TOKEN == "changeme-please":
        print("WARNING: using the default token. Set DOGCAM_TOKEN before exposing this publicly.")
    app.run(host="0.0.0.0", port=port, threaded=True)