# TrustWatch

A small, local **intrusion and tamper monitor for your own laptop**. If you
suspect someone is using your machine while you're away, TrustWatch can:

- 📸 **Capture a snapshot of whoever accesses the machine** the moment it's
  logged into or unlocked, and log the event with a timestamp.
- 🕵️ **See what they do** — alongside the webcam photo, guard mode grabs a
  **screenshot** and records the **foreground app/window** and **USB plug/unplug**
  events, so you get a timeline of activity (never keystrokes — see below).
- 🖥️ **Keep watching across sleep** — guard mode captures the instant the laptop
  wakes/resumes, and the autostart setup restarts it on boot/login.
- 🎥 **Act as a motion-detecting security camera** — watch the webcam and save
  frames + alert you only when something actually moves.
- 🔔 **Send you a notification** on your phone or inbox (Telegram, email, or any
  webhook) with the photo attached — not just a desktop pop-up that's useless
  once the laptop walks away.
- 🗂️ Keep everything **on your own machine** in a folder you control. Nothing is
  uploaded anywhere unless *you* configure a notification channel.

> **No keylogging.** TrustWatch records *that* someone is interacting and *which
> app* is in focus, plus screenshots — it never captures keystrokes, typed text,
> passwords, or clipboard contents. That line is intentional: it keeps this a
> tool for catching tampering with your own device, not for spying on input.

It runs headless (no window) so it keeps watching quietly in the background —
the same reason a security camera isn't a flashing sign.

---

## ⚖️ Please read first — use it right

TrustWatch is meant for **a device you own or are explicitly authorized to
administer**. Recording people has legal limits that vary a lot by country,
state, and situation (one-party vs. all-party consent, workplace rules, shared
or household devices, etc.).

- Use it on **your own laptop**, to find out who is tampering with **your** device.
- Don't use it to secretly surveil other people, a shared/family computer others
  reasonably expect privacy on, or anyone else's device.
- If the tampering you're worried about involves theft, a break-in, or someone
  you feel unsafe around, a captured photo is **evidence** — consider involving
  the police or your IT/security team rather than confronting anyone yourself.

You're responsible for complying with the laws that apply to you.

---

## Install

TrustWatch is managed with [uv](https://docs.astral.sh/uv/). Install uv first
(`curl -LsSf https://astral.sh/uv/install.sh | sh`, or on Windows
`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`), then:

```bash
git clone https://github.com/duck420i69/TrustWatch.git
cd TrustWatch
uv sync            # creates .venv and installs the project + dev tools
```

That's it — `uv sync` reads `pyproject.toml`/`uv.lock`, picks a suitable Python
(3.9+), and installs everything. Run the CLI with `uv run trustwatch ...` (or
activate the venv: `.venv/bin/trustwatch`, or `.venv\Scripts\trustwatch.exe` on
Windows). A webcam is needed for capture; `mss`/`opencv-python` are installed
for you.

Some activity signals on **Linux/X11** rely on small OS tools rather than Python
packages — install them if you want idle-time and active-window detection in
guard mode: `sudo apt install xprintidle xdotool`. macOS and Windows use
built-in facilities (no extra install).

## Quick start

```bash
# 1. Copy the example config and (optionally) add your alert channel.
mkdir -p ~/.trustwatch && cp config.example.json ~/.trustwatch/config.json

# 2. Prove the camera + notifications work.
uv run trustwatch --config ~/.trustwatch/config.json snap          # take one photo now
uv run trustwatch --config ~/.trustwatch/config.json test-notify   # fire a test alert

# 3. Run the persistent guard (captures on turn-on, wake, interaction, USB).
uv run trustwatch --config ~/.trustwatch/config.json guard

#    ...or the motion-detecting security camera (Ctrl-C to stop either).
uv run trustwatch --config ~/.trustwatch/config.json camera

# 4. Review what happened.
uv run trustwatch --config ~/.trustwatch/config.json log -n 20
```

If you don't pass `--config`, built-in defaults are used (desktop notifications
only, data in `~/.trustwatch`). To run the tests: `uv run pytest`.

## Commands

| Command | What it does |
|---|---|
| `snap` | Capture **one** access event now (webcam photo + screenshot + foreground app), log it, and alert. Wire this to your OS login/unlock (see `install/`). Add `--kind login`/`--kind unlock` to label it. |
| `guard` | **Persistent watcher.** Captures on start (turn-on), on **wake from sleep**, while **someone is interacting**, and on **USB plug/unplug**; logs an activity timeline. Runs until `Ctrl-C`. |
| `camera` | Run the motion-detecting security camera loop until `Ctrl-C`. |
| `log [-n N]` | Print the most recent events. |
| `test-notify` | Send a test alert through every configured channel. |
| `show-config` | Print the effective configuration (handy for debugging). |

Add `--no-notify` to `snap`/`camera`/`guard` to capture and log silently without
sending alerts.

## Guard mode — capture interaction, activity, and wake-from-sleep

`trustwatch guard` is the "someone is tampering with my laptop" mode. It runs in
the background and captures a full event (webcam photo + screenshot + foreground
app) when any of these happen:

- **Turn-on / start** — the moment guard launches (wire it to boot/login below).
- **Wake from sleep** — userspace can't run while the laptop is physically
  suspended, so guard detects the *resume* (a poll gap far larger than its
  interval) and captures the instant the lid opens. Combined with the autostart
  setup, it keeps watching across sleep cycles.
- **Interaction** — when the OS idle timer shows someone is actively using the
  machine (rate-limited by `interaction_cooldown` so you get periodic snapshots,
  not a flood).
- **USB change** — a device plugged in or removed (a common tamper signal).

It also logs a lightweight **activity timeline** (which app/window comes to the
foreground). All tunables live in the `guard` and `screen` sections of the
config.

### Keep it running across sleep / reboots

Run `guard` as a persistent service that restarts on login and resumes after
sleep — the same `install/` guides cover this:

- **macOS** → add `KeepAlive` to the LaunchAgent and use the `guard` subcommand.
- **Linux** → a `systemd --user` service with `Restart=always`.
- **Windows** → a Task Scheduler task "At log on" + "On workstation unlock".

See [`install/`](install/) for the exact service definitions.

## Capturing who logs in (the anti-tamper use case)

`trustwatch snap` takes a photo and logs the access the instant it runs — so the
trick is to have your OS run it at **login and unlock**. Step-by-step guides:

- **macOS** → [`install/macos-launchagent.md`](install/macos-launchagent.md)
- **Linux** → [`install/linux-systemd.md`](install/linux-systemd.md)
- **Windows** → [`install/windows-task-scheduler.md`](install/windows-task-scheduler.md)

If the camera is covered or disabled when `snap` fires, the access is **still
logged** (with a note that capture failed) — a blocked camera is itself a signal.

## Notifications

Configure any combination in the `notifier` section of your config. Secrets can
also be supplied via environment variables so they stay out of the file:
`TRUSTWATCH_TELEGRAM_TOKEN`, `TRUSTWATCH_TELEGRAM_CHAT_ID`,
`TRUSTWATCH_SMTP_PASSWORD`, `TRUSTWATCH_WEBHOOK_URL`.

- **Desktop** (`desktop: true`) — native pop-up on the machine. Good while you're
  nearby; install `plyer` for the nicest cross-platform behavior.
- **Telegram** — the easiest way to get the photo on your phone. Create a bot
  with [@BotFather](https://t.me/BotFather), message it once, then read your
  `chat_id` from `https://api.telegram.org/bot<token>/getUpdates`.
- **Email** — standard SMTP (e.g. Gmail with an app password). The snapshot is
  attached.
- **Webhook** — TrustWatch POSTs the alert (and image as multipart) to any URL:
  Slack/Discord incoming webhooks, [ntfy.sh](https://ntfy.sh), IFTTT, Home
  Assistant, or your own endpoint.

Each channel fails independently — a bad token logs a warning but never stops
TrustWatch from capturing or alerting through the others.

## Where your data lives

```
~/.trustwatch/
├── config.json          # your settings (gitignored; keep your secrets here)
├── events.log           # one JSON line per event (incl. app/window + USB notes)
└── snapshots/           # 20260101-091500_login.jpg       (webcam)
                         # 20260101-091500_login-screen.jpg (screenshot)
```

Each event in `events.log` records the webcam photo path, the screenshot path,
and the foreground app/window at that moment. Review events any time with
`trustwatch log`. Delete the folder to wipe history.

## Tuning motion detection

In the `motion` section:

- `min_area` — bigger = less sensitive (ignores small movements).
- `sensitivity` — pixel-change threshold; **lower** = more sensitive.
- `cooldown_seconds` — minimum gap between alerts, so one person doesn't trigger
  a flood.
- `consecutive_frames` — frames of motion in a row before alerting (filters
  flickers).

## Similar / related projects worth a look

TrustWatch is deliberately small; depending on your needs these established
projects may fit better (verify current status/licenses yourself):

- **[Prey](https://preyproject.com/)** — mature open-source anti-theft for
  laptops & phones: remote location, lock, and webcam capture from a dashboard.
- **Objective-See tools (macOS)** — *Do Not Disturb* detects physical
  lid/tamper events; *OverSight* alerts whenever the webcam or mic turns on.
- **[Haven](https://guardianproject.info/apps/org.havenapp.main/)** (Guardian
  Project) — turns a spare Android phone into a tamper/intrusion sensor (camera,
  mic, motion, light) with encrypted alerts. Great as a standalone "guard" you
  leave next to your laptop.
- **[Motion](https://motion-project.github.io/) / motionEye** — full-featured
  Linux motion-detection CCTV software if you want a dedicated camera system.
- **[BusKill](https://www.buskill.in/)** — a physical USB "dead-man's switch"
  that locks/wipes the laptop if it's physically separated from you.
- **[usbkill](https://github.com/hephaest0s/usbkill)** — triggers a lockdown
  when USB devices are plugged/unplugged (anti-forensic / anti-tamper).

## Threat model & hardening

TrustWatch is a **tripwire with a camera**, not a vault. It's effective against a
casual snooper who doesn't know it's there. Anyone with physical access, admin
rights, and some knowledge can defeat a software monitor — understand how, so you
can pair it with the right hardening.

**How a software monitor gets bypassed (and the fix):**

| Attack | Why it works | Hardening |
|---|---|---|
| **Boot another OS / USB / recovery mode** | TrustWatch only runs after *your* OS boots and logs in; a different boot never starts it. | Firmware/BIOS password; disable USB/external boot. |
| **Pull the disk / mount offline** | With your OS not running, they read or delete `~/.trustwatch/` (snapshots, logs) and your config, or edit the code — no permission checks apply. | **Full-disk encryption** (FileVault / BitLocker / LUKS) — the single biggest hardener. |
| **Kill the process / disable autostart** | A background job has no special privilege; admin/root outranks it, and it runs as *you*. | Separate admin account; don't hand out your password. |
| **Cover the webcam / cut the network** | Black photos; alerts can't leave the machine, and queued captures die if the disk is then wiped. | Off-device upload *first* (below); treat "camera capture failed" events as a signal. |
| **Timing** | Physical access = they control the clock: cut network, act, wipe — faster than evidence escapes. | Immediate off-device alerts; a separate guard device. |

**What actually raises the bar** — the goal is to get evidence *off the device
before it can be suppressed*, and make the OS hard to bypass:

1. **Full-disk encryption** — defeats the offline disk attack and offline code edits.
2. **Firmware password + no external boot** — closes the "boot something else" bypass.
3. **Immediate off-device alerts** (Telegram / webhook) — the photo reaches your
   phone before a local wipe helps them. This is why TrustWatch favors phone-
   reachable channels over a desktop pop-up.
4. **A separate guard device** — the [Haven](https://guardianproject.info/apps/org.havenapp.main/)
   approach (a spare phone watching your laptop) can't be logged into or wiped as
   part of tampering with the laptop, so it's more robust for a persistent problem.
5. **Remote/append-only logging** — ship events to a server they don't control, so
   deleting the local log doesn't erase the trail.

## Limitations & honesty

- Login/unlock capture depends on the OS hook you set up — TrustWatch provides
  the capture, your OS provides the trigger. The guides in `install/` cover the
  common cases.
- A determined, technical attacker with physical access and time can find and
  disable almost any software monitor (see the threat model above). TrustWatch
  raises the bar and gives you evidence/alerts; it is not tamper-*proof*.
- Face *recognition* (naming who it is) is intentionally **not** included — it
  captures the image and leaves identification to you.

## License

MIT — see [LICENSE](LICENSE).
