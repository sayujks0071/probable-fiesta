#!/usr/bin/env python3
import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RootStartup")

def main():
    logger.info("Starting Daily Startup Routine...")

    script_path = os.path.join("openalgo", "scripts", "daily_startup.py")

    if not os.path.exists(script_path):
        logger.error(f"Error: {script_path} not found. Ensure you are running from the repository root.")
        sys.exit(1)

    # Execute the new daily startup script, passing along any arguments
    try:
        cmd = [sys.executable, script_path] + sys.argv[1:]
        subprocess.check_call(cmd)
        logger.info("Daily Startup Completed Successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Daily Startup Failed with exit code {e.returncode}")
        sys.exit(e.returncode)

if __name__ == "__main__":
    main()
