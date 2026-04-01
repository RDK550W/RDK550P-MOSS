#!/bin/bash
cd "$(dirname "$0")"
echo "Voice assistant launcher (auto-restart on crash)"
while true; do
    echo "[$(date)] Starting voice_assistant.py ..."
    python3 -u voice_assistant.py 2>&1 | tee -a /tmp/voice-assistant.log
    echo "[$(date)] Process exited ($?), restarting in 3s..."
    sleep 3
done
