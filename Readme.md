set DOGCAM_EXPOSURE=-8
set DOGCAM_BRIGHTNESS=100
export DOGCAM_TOKEN=PsbEJ9Mxfi96Z0lDTSxgGAXRgROhhhfq
export PORT=8000
python app.py


# Dog Cam — Setup Flow


Follow these steps **in order**. Two machines are involved:
- **Server machine** — stays running, hosts the viewing webpage
- **Windows machine** (near the dog) — runs the camera app

---

## STEP 1 — Pick a token

Run once anywhere Python is installed:
```
python -c "import secrets; print(secrets.token_urlsafe(24))"
```
Copy the output — this is your password for the whole system.

---

## STEP 2 — Publish token.txt and link.txt on GitHub

In your repo (`nngeek195/mywork`):
- Create/edit **`token.txt`** — paste only the token from Step 1, nothing else.
- Create/edit **`link.txt`** — leave it for now, you'll fill it in at Step 4.

Commit and push both.

---

## STEP 3 — Start the server

On the server machine:
```
cd server
pip install -r requirements.txt
set DOGCAM_TOKEN=PASTE_YOUR_TOKEN_HERE
set PORT=8000
python app.py
```
Leave this window open and running.

---

## STEP 4 — Open a public tunnel (Cloudflare) and update link.txt

On the **same server machine**, in a new terminal:
```
cloudflared tunnel --url http://localhost:8000
```
Cloudflare prints a URL like `https://random-words-1234.trycloudflare.com`.

Go back to GitHub, edit `link.txt` so it contains **only** that URL, and
push. Leave the `cloudflared` window open too.

This URL changes every time the tunnel restarts — see the **ROUTINE**
section below for exactly what to redo when that happens (it's more than
just editing the file).

---

## STEP 5 — Build the Windows app (one time)

On a Windows machine with Python installed:
```
cd client
pip install -r requirements.txt
pyinstaller --onefile --windowed --name DogCam webcam_client.py
```
Your file is now at `client\dist\DogCam.exe`. This is the only file you
hand to whoever runs it — no separate config needed, since it pulls both
the token and the server link from GitHub automatically every time it
starts.

---

## STEP 6 — Run it on the Windows machine

1. Double-click `DogCam.exe`.
2. A popup explains what it does — click **Yes** to start.
3. A tray icon appears near the clock. Green = streaming.
4. Done — no terminal, nothing else to configure.

---

## STEP 7 — Watch the stream

In any browser:
```
https://random-words-1234.trycloudflare.com/?token=PASTE_YOUR_TOKEN_HERE
```
(your Step 4 URL + `?token=` + your Step 1 token)

---

## ROUTINE — Every time the tunnel URL changes

This is the one thing you'll repeat regularly (free Cloudflare quick-tunnels
get a **new random URL every time you start `cloudflared`** — restart your
PC, close the terminal, anything like that, and the old link stops working).

Do all three of these, in order, every time:

1. **Restart the tunnel** on the server machine:
   ```
   cloudflared tunnel --url http://localhost:8000
   ```
   Copy the new URL it prints.

2. **Update `link.txt` on GitHub** with that new URL (only the URL, nothing
   else), then commit and push.

3. **Restart `DogCam.exe`** on the Windows machine — right-click the tray
   icon → Quit, then double-click `DogCam.exe` again.
   *Important:* the app only reads `link.txt` once, when it starts up. If
   it's already running, editing `link.txt` on GitHub does nothing until
   you quit and reopen it. There's no "auto-reload while running."

4. **Update your bookmark/browser tab** for Step 7 with the new URL too.

If you want to skip this routine entirely: run `cloudflared tunnel login`
once and use a **named tunnel** tied to your own domain (see Cloudflare's
tunnel docs) instead of a quick-tunnel — a named tunnel's URL stays fixed
forever, so you'd only ever do Step 4 once.

---

## If you ever rotate the token

Update it in **both** places, or the server and the app will disagree:
1. `token.txt` on GitHub (the Windows app reads this)
2. The server's `DOGCAM_TOKEN` env var, then restart `python app.py`

---

## If the picture is washed-out white

Run from a terminal instead of the .exe, with tuning:
```
set DOGCAM_EXPOSURE=-8
set DOGCAM_BRIGHTNESS=100
python webcam_client.py
```
Adjust the numbers until it looks right, then rebuild the .exe (Step 5).

---

## Auto-start on login (optional)

1. `Win+R` → type `shell:startup` → Enter.
2. Put a shortcut to `DogCam.exe` in that folder.
3. It now launches automatically every login (tray icon still visible).

---

## Reference

| Item | What it is | Set in |
|---|---|---|
| `token.txt` | Your password, fetched by the app on every start | Step 1 → Step 2 |
| `link.txt` | Current tunnel URL, fetched by the app once on startup only | Step 4 → ROUTINE |
| `DOGCAM_TOKEN` (server) | Must match `token.txt` | Step 3 |
| `DogCam.exe` | The camera app | Step 5 → Step 6 |

**Note:** both `token.txt` and `link.txt` are in your repo, so if it's
public, anyone with the raw file URL can view the stream. Set the repo to
private if that's not fine.