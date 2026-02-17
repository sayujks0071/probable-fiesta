#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
import shutil
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DailyStartup")

REPO_URL = "https://github.com/dheerajw7/OpenAlgo.git"
VENDOR_DIR = "vendor"
OPENALGO_DIR = os.path.join(VENDOR_DIR, "openalgo")

def check_env():
    logger.info("Checking Environment Variables...")
    required_vars = ['OPENALGO_APIKEY']
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        logger.warning(f"Missing environment variables: {missing}. Using defaults or risking failure.")
        if 'OPENALGO_APIKEY' in missing:
             os.environ['OPENALGO_APIKEY'] = 'demo_key' # Fallback for now

    # Ensure we are in the repo root (heuristic: check for 'openalgo' and 'README.md')
    if not os.path.exists("openalgo") and not os.path.exists("README.md"):
         logger.error("Error: Please run this script from the repository root.")
         sys.exit(1)

def ensure_vendor_openalgo():
    logger.info(f"Ensuring OpenAlgo is present in {OPENALGO_DIR}...")

    if not os.path.exists(VENDOR_DIR):
        os.makedirs(VENDOR_DIR)

    if not os.path.exists(OPENALGO_DIR):
        logger.info(f"Cloning OpenAlgo to {OPENALGO_DIR}...")
        try:
            subprocess.check_call(["git", "clone", REPO_URL, OPENALGO_DIR])
            logger.info("Cloning successful.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone OpenAlgo: {e}")
            sys.exit(1)
    else:
        # Verify it's a git repo and maybe update?
        # User said: "If already present, verify remote + branch"
        # For now, just logging existence.
        logger.info(f"OpenAlgo found in {OPENALGO_DIR}.")

def run_daily_prep():
    logger.info("Running Daily Prep...")

    prep_script = os.path.join("openalgo", "scripts", "daily_prep.py")
    if not os.path.exists(prep_script):
        logger.error(f"Daily prep script not found at {prep_script}")
        sys.exit(1)

    # Set PYTHONPATH to include vendor so we can import from there if needed
    env = os.environ.copy()
    cwd = os.getcwd()
    vendor_path = os.path.join(cwd, VENDOR_DIR)
    env['PYTHONPATH'] = f"{cwd}:{vendor_path}:{env.get('PYTHONPATH', '')}"

    try:
        subprocess.check_call([sys.executable, prep_script], env=env)
        logger.info("Daily Prep completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Daily Prep failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def run_backtest_pipeline(run_tuning=False):
    logger.info("Running Backtest Pipeline...")

    backtest_script = os.path.join("openalgo", "scripts", "daily_backtest_leaderboard.py")
    if not os.path.exists(backtest_script):
        logger.error(f"Backtest script not found at {backtest_script}")
        return

    env = os.environ.copy()
    cwd = os.getcwd()
    vendor_path = os.path.join(cwd, VENDOR_DIR)
    env['PYTHONPATH'] = f"{cwd}:{vendor_path}:{env.get('PYTHONPATH', '')}"

    try:
        subprocess.check_call([sys.executable, backtest_script], env=env)
        logger.info("Backtest Leaderboard generated.")

        if run_tuning:
            tuning_script = os.path.join("openalgo", "scripts", "fine_tune_strategies.py")
            if os.path.exists(tuning_script):
                logger.info("Running Fine Tuning...")
                subprocess.check_call([sys.executable, tuning_script], env=env)
                logger.info("Fine Tuning completed.")
            else:
                logger.warning(f"Fine Tuning script not found at {tuning_script}")

    except subprocess.CalledProcessError as e:
        logger.error(f"Backtest Pipeline failed with exit code {e.returncode}")
        # Don't exit main process, as Prep succeeded.

def main():
    parser = argparse.ArgumentParser(description="OpenAlgo Daily Startup Routine")
    parser.add_argument("--backtest", action="store_true", help="Run backtest and leaderboard generation after prep")
    parser.add_argument("--tune", action="store_true", help="Run fine-tuning optimization after backtest")
    args = parser.parse_args()

    logger.info("=== OPENALGO DAILY STARTUP ===")
    check_env()
    ensure_vendor_openalgo()

    run_daily_prep()

    if args.backtest:
        run_backtest_pipeline(run_tuning=args.tune)

    logger.info("=== STARTUP SEQUENCE COMPLETE ===")

if __name__ == "__main__":
    main()
