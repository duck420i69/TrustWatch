# Run TrustWatch on login / unlock — Windows

Use Task Scheduler to fire `trustwatch snap` at logon and at workstation unlock.

1. Find your executable. With uv, after `uv sync` in your clone it lives in the
   project's virtual environment, e.g.
   `E:\repos\Python\TrustWatch\.venv\Scripts\trustwatch.exe`:

   ```powershell
   Get-Command .\.venv\Scripts\trustwatch.exe | Select-Object -ExpandProperty Source
   ```

   (Use that full `.exe` path below. Alternatively set the action to run
   `uv` with arguments `run --project E:\repos\Python\TrustWatch trustwatch ...`.)

2. Open **Task Scheduler** → **Create Task** (not "Basic Task").

3. **General tab:** name it `TrustWatch Snap`. Check *Run only when user is
   logged on*. Check *Hidden* if you don't want a console window to flash.

4. **Triggers tab** → *New* → create two triggers:
   - Begin the task: **At log on** (your user).
   - Begin the task: **On workstation unlock**.

5. **Actions tab** → *New*:
   - Program/script: the full path from step 1 (or `python.exe`).
   - Add arguments:
     `--config "%USERPROFILE%\.trustwatch\config.json" snap --kind login`
     (If you used `python.exe`, prefix with `-m trustwatch`.)

6. **Conditions tab:** uncheck *Start the task only if the computer is on AC
   power* so it also runs on battery.

7. Save. Windows may ask for your password to register the task.

The first capture will prompt for camera access (Settings → Privacy & security
→ Camera → let desktop apps use the camera).

## Persistent guard mode (recommended)

For the always-on watcher (captures on start, wake, interaction, and USB
change), create a second task `TrustWatch Guard`:

- **Trigger:** *At log on* (your user).
- **Action:** the `trustwatch` path, arguments
  `--config "%USERPROFILE%\.trustwatch\config.json" guard`.
- **Settings tab:** check *If the task fails, restart every* 1 minute, and set
  *If the task is already running* to *Do not start a new instance*.
- **Conditions tab:** uncheck *Stop if the computer switches to battery power*
  and *Start only on AC power* so it keeps running unplugged.

Guard detects resume-from-sleep itself and captures on wake; the "On workstation
unlock" trigger from the `snap` task above is a good complement.
