"""
Kuki Kids Bot — Railway Entry Point
=====================================
Railway runs this file. It schedules the bot daily and keeps running forever.
All config comes from Railway environment variables (no .env file needed).
"""

import schedule
import time
import logging
from bot import run

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("KukiScheduler")

RUN_AT = "08:00"  # UTC time — adjust to your timezone if needed

def safe_run():
    try:
        run()
    except Exception as e:
        log.error(f"Bot run failed: {e}", exc_info=True)

log.info(f"🤖 Kuki Kids Bot started on Railway — runs daily at {RUN_AT} UTC")

# Run once immediately on first deploy
log.info("Running first job now...")
safe_run()

# Then every day at the scheduled time
schedule.every().day.at(RUN_AT).do(safe_run)

while True:
    schedule.run_pending()
    time.sleep(60)
