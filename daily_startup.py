#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import logging

# Ensure root is in path for imports
sys.path.append(os.getcwd())

try:
    from openalgo_observability.logging_setup import setup_logging
except ImportError:
    logging.basicConfig(level=logging.INFO)
    def setup_logging(): pass

REPO_URL = "https://github.com/dheerajw7/OpenAlgo.git"
TARGET_DIR = "openalgo"

def check_and_clone():
    if not os.path.exists(TARGET_DIR):
        logging.info(f"Directory '{TARGET_DIR}' not found. Cloning from {REPO_URL}...")
        try:
            subprocess.check_call(["git", "clone", REPO_URL, TARGET_DIR])
            logging.info("Cloning successful.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to clone repository: {e}")
            sys.exit(1)
    else:
        logging.info(f"Directory '{TARGET_DIR}' exists.")

def run_script_cmd(cmd, description):
    script_path = cmd[0]
    if not os.path.exists(script_path):
        logging.error(f"Error: {script_path} not found.")
        sys.exit(1)

    logging.info(f"Executing {description} ({script_path})...")
    try:
        env = os.environ.copy()
        env['PYTHONPATH'] = os.getcwd() + ":" + env.get('PYTHONPATH', '')

        # Determine python executable
        # Use venv if exists, else system python
        venv_python = os.path.join(TARGET_DIR, "venv", "bin", "python3")
        python_exec = venv_python if os.path.exists(venv_python) else sys.executable

        full_cmd = [python_exec] + cmd

        subprocess.check_call(full_cmd, env=env)
        logging.info(f"✅ {description} Success.")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ {description} Failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def main():
    # Initialize Observability Logging
    setup_logging()

    parser = argparse.ArgumentParser(description="OpenAlgo Daily Startup Routine")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip daily backtest")
    args = parser.parse_args()

    logging.info("=== DAILY STARTUP ROUTINE ===")

    # 1. Ensure Repo
    check_and_clone()

    # 2. Daily Prep (which handles backtest internally now)
    prep_script = os.path.join(TARGET_DIR, "scripts", "daily_prep.py")
    cmd = [prep_script]
    if args.skip_backtest:
        cmd.append("--skip-backtest")

    run_script_cmd(cmd, "Daily Prep")

    logging.info("=== DAILY ROUTINE COMPLETE ===")

if __name__ == "__main__":
    main()
