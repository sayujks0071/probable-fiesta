#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import logging

# Ensure vendor path is in sys.path for imports
repo_root = os.path.dirname(os.path.abspath(__file__))
vendor_path = os.path.join(repo_root, "vendor")
sys.path.append(vendor_path)

try:
    from openalgo_observability.logging_setup import setup_logging
except ImportError:
    # Fallback if module not found in root (should be there)
    logging.basicConfig(level=logging.INFO)
    def setup_logging(): pass

REPO_URL = "https://github.com/dheerajw7/OpenAlgo.git"
TARGET_DIR = "vendor/openalgo"

def check_and_clone():
    if not os.path.exists(TARGET_DIR):
        logging.info(f"Directory '{TARGET_DIR}' not found. Cloning from {REPO_URL}...")
        try:
            os.makedirs("vendor", exist_ok=True)
            subprocess.check_call(["git", "clone", REPO_URL, TARGET_DIR])
            logging.info("Cloning successful.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to clone repository: {e}")
            sys.exit(1)
    else:
        logging.info(f"Directory '{TARGET_DIR}' exists.")

def run_script(script_path, description):
    if not os.path.exists(script_path):
        logging.error(f"Error: {script_path} not found.")
        sys.exit(1)

    logging.info(f"Executing {description} ({script_path})...")
    try:
        env = os.environ.copy()
        # Add vendor to PYTHONPATH so scripts can import openalgo
        current_path = env.get('PYTHONPATH', '')
        vendor_abs = os.path.abspath("vendor")
        env['PYTHONPATH'] = f"{os.getcwd()}:{vendor_abs}:{current_path}"

        # Use venv if exists, else system python
        venv_python = os.path.join(TARGET_DIR, "venv", "bin", "python3")
        python_exec = venv_python if os.path.exists(venv_python) else sys.executable

        subprocess.check_call([python_exec, script_path], env=env)
        logging.info(f"✅ {description} Success.")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ {description} Failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def main():
    # Initialize Observability Logging
    setup_logging()

    parser = argparse.ArgumentParser(description="OpenAlgo Daily Startup Routine")
    parser.add_argument("--backtest", action="store_true", help="Run backtest and leaderboard generation after prep")
    args = parser.parse_args()

    logging.info("=== DAILY STARTUP ROUTINE ===")

    # 1. Ensure Repo
    check_and_clone()

    # 2. Daily Prep
    prep_script = os.path.join(TARGET_DIR, "scripts", "daily_prep.py")
    run_script(prep_script, "Daily Prep")

    # 3. Backtest (Optional)
    if args.backtest:
        backtest_script = os.path.join(TARGET_DIR, "scripts", "daily_backtest_leaderboard.py")
        run_script(backtest_script, "Daily Backtest & Leaderboard")

    logging.info("=== DAILY ROUTINE COMPLETE ===")

if __name__ == "__main__":
    main()
