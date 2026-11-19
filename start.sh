#!/bin/bash
# Run the bot AND the real dashboard server together, 24/7 on a host.
# Bot runs in the background, dashboard runs in the foreground.
python bot.py &
python dashboard_server.py
