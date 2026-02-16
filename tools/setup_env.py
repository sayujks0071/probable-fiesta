#!/usr/bin/env python3
import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SetupEnv")

REPO_URL = "https://github.com/dheerajw7/OpenAlgo.git"
TARGET_DIR = "openalgo"

def check_and_setup_repo():
    """
    Ensures that the OpenAlgo repository is present at the expected location.
    """
    repo_path = os.path.abspath(TARGET_DIR)

    if not os.path.exists(repo_path):
        logger.info(f"Directory '{TARGET_DIR}' not found. Cloning from {REPO_URL}...")
        try:
            subprocess.check_call(["git", "clone", REPO_URL, TARGET_DIR])
            logger.info("Cloning successful.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone repository: {e}")
            sys.exit(1)
    else:
        logger.info(f"Directory '{TARGET_DIR}' exists.")

        # Verify it's a git repo
        # If openalgo is a package inside a repo, .git might be in parent.
        # We check if TARGET_DIR is a git root OR if we can run git status
        if os.path.isdir(os.path.join(repo_path, ".git")):
            logger.info(f"'{TARGET_DIR}' is a valid git repository.")
        else:
            # Check if it's a valid package at least
            if os.path.exists(os.path.join(repo_path, "__init__.py")):
                 logger.warning(f"'{TARGET_DIR}' exists and appears to be a Python package, but is not a git root. Assuming manual setup.")
            else:
                 logger.warning(f"'{TARGET_DIR}' exists but lacks .git and __init__.py. Integrity check failed?")

def main():
    logger.info("=== SETTING UP ENVIRONMENT ===")
    check_and_setup_repo()

    # Print PYTHONPATH instructions for the shell script to pick up
    print(f"export PYTHONPATH=$PYTHONPATH:{os.getcwd()}")

    logger.info("=== SETUP COMPLETE ===")

if __name__ == "__main__":
    main()
