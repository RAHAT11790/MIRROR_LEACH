#!/usr/bin/env bash
# Start the bot. Use:  bash run_cloudshell.sh        (foreground)
#                      bash run_cloudshell.sh bg     (keeps running after the tab is closed)
cd "$(dirname "$0")"
[ -d .venv ] || { echo "Run: bash setup_cloudshell.sh first"; exit 1; }
. .venv/bin/activate
export PATH="$PWD/bin:$PATH"
if [ "${1:-}" = "bg" ]; then
  nohup python3 main.py > log.txt 2>&1 &
  echo "Bot started in background (PID $!). Logs: tail -f log.txt"
else
  exec python3 main.py
fi
