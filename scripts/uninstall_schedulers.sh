#!/bin/bash

# Uninstall Systemd Timer
echo "Uninstalling Systemd timer..."
systemctl --user stop openalgo-healthcheck.timer 2>/dev/null
systemctl --user disable openalgo-healthcheck.timer 2>/dev/null
rm -f "$HOME/.config/systemd/user/openalgo-healthcheck.service"
rm -f "$HOME/.config/systemd/user/openalgo-healthcheck.timer"
systemctl --user daemon-reload

# Uninstall Cron Job
echo "Uninstalling Cron job..."
# Remove lines containing "scripts/healthcheck.py"
# We pipe existing crontab to grep -v, then reinstall
crontab -l 2>/dev/null | grep -v "scripts/healthcheck.py" | crontab -

echo "✅ Schedulers uninstalled."
