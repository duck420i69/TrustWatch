# Run TrustWatch on login / unlock — Windows

Use Task Scheduler to fire `trustwatch snap` at logon and at workstation unlock.

1. Find your executable:

   ```powershell
   where.exe trustwatch
   ```

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
