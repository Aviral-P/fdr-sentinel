#!/bin/bash
set -euo pipefail

# Installs a daily local reminder-generation job for the current macOS user.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing $PYTHON. Create the backend virtual environment and install requirements first." >&2
  exit 1
fi
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/backend/logs"
PLIST="$HOME/Library/LaunchAgents/com.fdrsentinel.reminders.plist"
python3 - "$PLIST" "$PYTHON" "$ROOT/backend" "$ROOT/backend/logs/reminder-scheduler.log" <<'PYTHON'
import plistlib, sys
from pathlib import Path
plist_path, python, working_dir, log_path = sys.argv[1:]
data = {
    "Label": "com.fdrsentinel.reminders",
    "ProgramArguments": [python, "-m", "scripts.generate_reminders"],
    "WorkingDirectory": working_dir,
    "StartCalendarInterval": {"Hour": 9, "Minute": 0},
    "StandardOutPath": log_path,
    "StandardErrorPath": log_path,
    "RunAtLoad": True,
}
with Path(plist_path).open("wb") as f:
    plistlib.dump(data, f)
PYTHON
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed daily FDR Sentinel reminder job at 09:00 local time."
echo "Log: $ROOT/backend/logs/reminder-scheduler.log"
echo "To uninstall: launchctl bootout gui/$(id -u) $PLIST && rm $PLIST"
