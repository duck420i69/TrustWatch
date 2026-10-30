# Run TrustWatch on login / unlock — macOS

macOS runs a LaunchAgent for your user. This one fires `trustwatch snap` every
time you log in and whenever the Mac wakes/unlocks.

1. Find your install path and config:

   ```bash
   which trustwatch      # e.g. /Users/you/.venv/bin/trustwatch
   ```

2. Create `~/Library/LaunchAgents/com.trustwatch.snap.plist` with this content,
   substituting the two paths:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
     <key>Label</key><string>com.trustwatch.snap</string>
     <key>ProgramArguments</key>
     <array>
       <string>/FULL/PATH/TO/trustwatch</string>
       <string>--config</string>
       <string>/Users/you/.trustwatch/config.json</string>
       <string>snap</string>
       <string>--kind</string>
       <string>login</string>
     </array>
     <key>RunAtLoad</key><true/>
   </dict>
   </plist>
   ```

3. Load it:

   ```bash
   launchctl load ~/Library/LaunchAgents/com.trustwatch.snap.plist
   ```

4. **Grant camera permission.** The first run will prompt, or add your terminal
   (and `trustwatch`'s Python) under System Settings → Privacy & Security →
   Camera.

To also snapshot on wake/unlock, pair this with `sleepwatcher` (Homebrew) or a
`caffeinate`-based watcher — see the project README for options.

## Persistent guard mode (recommended)

Instead of a one-shot `snap`, run the always-on `guard` watcher, which already
captures on wake, interaction, and USB change. Use a LaunchAgent with
`KeepAlive` so macOS restarts it if it ever exits, labelled
`com.trustwatch.guard`:

```xml
    <key>ProgramArguments</key>
    <array>
      <string>/FULL/PATH/TO/trustwatch</string>
      <string>--config</string>
      <string>/Users/you/.trustwatch/config.json</string>
      <string>guard</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
```

`KeepAlive` also means it comes back automatically after the machine wakes, so
it keeps watching across sleep cycles. Camera permission is required (see above).
