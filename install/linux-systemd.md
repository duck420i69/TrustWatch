# Run TrustWatch on login / unlock — Linux

Two options depending on what you want to trigger on.

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

## Camera permission

On Linux the webcam is `/dev/video0`; make sure your user is in the `video`
group: `sudo usermod -aG video $USER` (then log out/in).
