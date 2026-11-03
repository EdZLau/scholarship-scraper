#!/usr/bin/env bash
# schedule.sh — set up weekly cron job to run the scholarship scraper
# Run: bash schedule.sh

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG="$PROJECT_DIR/logs/cron.log"

# Weekly cron: every Sunday at 8 AM
CRON_LINE="0 8 * * 0 cd $PROJECT_DIR && $PYTHON main.py >> $LOG 2>&1"

# Add to crontab if not already present
( crontab -l 2>/dev/null | grep -v "scholarship_system"; echo "$CRON_LINE" ) | crontab -

echo "✅ Cron job set: runs every Sunday at 8 AM"
echo "   Log: $LOG"
echo ""
echo "To verify: crontab -l"
echo "To remove: crontab -e  (then delete the scholarship_system line)"
