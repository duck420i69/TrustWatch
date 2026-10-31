# Run TrustWatch on login / unlock — Linux

Two options depending on what you want to trigger on. With uv, after `uv sync`
the `trustwatch` executable lives at `<your-clone>/.venv/bin/trustwatch` — use
that full path for `ExecStart` below (or run `uv run --project <clone> trustwatch`).

## A. Snapshot on graphical login (systemd user service)

Create `~/.config/systemd/user/trustwatch-snap.service`:

```ini
[Unit]
Description=TrustWatch access snapshot
After=graphical-session.target

[Service]
Type=oneshot
ExecStart=/FULL/PATH/TO/trustwatch --config %h/.trustwatch/config.json snap --kind login

[Install]
WantedBy=graphical-session.target
```

Enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now trustwatch-snap.service
```

## B. Snapshot on screen unlock (D-Bus)

Many desktops emit a D-Bus signal on unlock. This watcher fires `snap` on each
unlock; run it from your autostart:

```bash
#!/usr/bin/env bash
dbus-monitor --session \
  "type='signal',interface='org.freedesktop.ScreenSaver'" |
while read -r line; do
  if echo "$line" | grep -q "boolean false"; then   # false = unlocked
    trustwatch --config "$HOME/.trustwatch/config.json" snap --kind unlock
  fi
done
```

Save as `~/.local/bin/trustwatch-unlock-watch.sh`, `chmod +x` it, and add it to
your desktop's autostart. (GNOME uses `org.gnome.ScreenSaver`; adjust the
interface to match your environment — check with `dbus-monitor --session`.)

## C. Persistent guard mode (recommended)

Rather than one-shot snapshots, run the always-on `guard` watcher (captures on
start, wake, interaction, and USB change). Create
`~/.config/systemd/user/trustwatch-guard.service`:

```ini
[Unit]
Description=TrustWatch guard
After=graphical-session.target

[Service]
ExecStart=/FULL/PATH/TO/trustwatch --config %h/.trustwatch/config.json guard
Restart=always
RestartSec=5

[Install]
WantedBy=graphical-session.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now trustwatch-guard.service
```

`Restart=always` brings it back after sleep/resume or if it crashes. For it to
run even while you're logged out, enable lingering: `loginctl enable-linger $USER`.

Idle-time and active-window detection on X11 use the small tools `xprintidle`
and `xdotool` (e.g. `sudo apt install xprintidle xdotool`). On Wayland these
signals may be unavailable; guard still captures on start, wake, and USB change.

## Camera permission

On Linux the webcam is `/dev/video0`; make sure your user is in the `video`
group: `sudo usermod -aG video $USER` (then log out/in).
