#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import logging
import shutil

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DailyStartup")

REPO_URL = "https://github.com/dheerajw7/OpenAlgo.git"
TARGET_DIR = "openalgo"

def check_and_clone():
    """Ensure OpenAlgo is cloned in the expected path."""
    if not os.path.exists(TARGET_DIR):
        logger.info(f"Directory '{TARGET_DIR}' not found. Cloning from {REPO_URL}...")
        try:
            subprocess.check_call(["git", "clone", REPO_URL, TARGET_DIR])
            logger.info("Cloning successful.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone repository: {e}")
            sys.exit(1)
    else:
        logger.info(f"Directory '{TARGET_DIR}' exists. Verifying git status (optional)...")
        # Could add git pull here if needed, but risky for local changes.
        # For now, just assume it's there.

def run_script(script_path, description, args=None):
    if not os.path.exists(script_path):
        logger.error(f"Error: {script_path} not found.")
        sys.exit(1)

    logger.info(f"Executing {description} ({script_path})...")

    cmd = [sys.executable, script_path]
    if args:
        cmd.extend(args)

    try:
        env = os.environ.copy()
        # Ensure root is in PYTHONPATH so 'import openalgo...' works
        env['PYTHONPATH'] = os.getcwd() + os.pathsep + env.get('PYTHONPATH', '')

        subprocess.check_call(cmd, env=env)
        logger.info(f"✅ {description} Success.")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {description} Failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(description="OpenAlgo Daily Startup Routine")
    parser.add_argument("--backtest", action="store_true", help="Run backtest and leaderboard generation after prep")
    parser.add_argument("--skip-prep", action="store_true", help="Skip daily prep (only run backtest)")
    args = parser.parse_args()

    logger.info("=== DAILY STARTUP ROUTINE ===")

    # 1. Ensure Repo Structure
    check_and_clone()

    # 2. Daily Prep (Purge, Login, Refresh, Validate)
    if not args.skip_prep:
        prep_script = os.path.join(TARGET_DIR, "scripts", "daily_prep.py")
        run_script(prep_script, "Daily Prep (Purge, Login, Instruments, Validation)")

    # 3. Backtest & Leaderboard (Optional but recommended)
    if args.backtest:
        backtest_script = os.path.join(TARGET_DIR, "scripts", "daily_backtest_leaderboard.py")
        run_script(backtest_script, "Daily Backtest & Leaderboard")

    logger.info("=== DAILY ROUTINE COMPLETE ===")

if __name__ == "__main__":
    main()
