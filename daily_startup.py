#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import logging
import shutil

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("DailyStartup")

REPO_URL = "https://github.com/dheerajw7/OpenAlgo.git"
VENDOR_DIR = "vendor"
TARGET_DIR = os.path.join(VENDOR_DIR, "openalgo")

def check_and_clone():
    if not os.path.exists(VENDOR_DIR):
        os.makedirs(VENDOR_DIR)
        logger.info(f"Created {VENDOR_DIR} directory.")

    if not os.path.exists(TARGET_DIR):
        logger.info(f"Directory '{TARGET_DIR}' not found. Cloning from {REPO_URL}...")
        try:
            subprocess.check_call(["git", "clone", REPO_URL, TARGET_DIR])
            logger.info("Cloning successful.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone repository: {e}")
            sys.exit(1)
    else:
        logger.info(f"Directory '{TARGET_DIR}' exists. Verifying...")
        # Optional: Check remote/pull
        try:
            subprocess.check_call(["git", "-C", TARGET_DIR, "pull"])
            logger.info("Repo updated.")
        except Exception as e:
             logger.warning(f"Failed to pull latest changes: {e}")

def run_script(script_rel_path, description):
    # script_rel_path is relative to TARGET_DIR (vendor/openalgo)
    script_path = os.path.join(TARGET_DIR, script_rel_path)

    if not os.path.exists(script_path):
        logger.error(f"Error: {script_path} not found.")
        sys.exit(1)

    logger.info(f"Executing {description} ({script_path})...")
    try:
        env = os.environ.copy()
        # Add vendor to PYTHONPATH so 'import openalgo' works
        env['PYTHONPATH'] = os.path.abspath(VENDOR_DIR) + ":" + os.path.abspath(TARGET_DIR) + ":" + env.get('PYTHONPATH', '')

        # Use venv if exists, else system python
        venv_python = os.path.join(TARGET_DIR, "venv", "bin", "python3")
        python_exec = venv_python if os.path.exists(venv_python) else sys.executable

        subprocess.check_call([python_exec, script_path], env=env)
        logger.info(f"✅ {description} Success.")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {description} Failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(description="OpenAlgo Daily Startup Routine")
    parser.add_argument("--backtest", action="store_true", help="Run backtest and leaderboard generation after prep")
    args = parser.parse_args()

    logger.info("=== DAILY STARTUP ROUTINE ===")

    # 1. Ensure Repo
    check_and_clone()

    # 2. Daily Prep
    # Note: openalgo/scripts/daily_prep.py is inside the repo
    run_script("scripts/daily_prep.py", "Daily Prep")

    # 3. Backtest (Optional)
    if args.backtest:
        run_script("scripts/daily_backtest_leaderboard.py", "Daily Backtest & Leaderboard")

    logger.info("=== DAILY ROUTINE COMPLETE ===")

if __name__ == "__main__":
    main()
