#!/usr/bin/env python3
import sys
import os
import logging

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Add openalgo directory to path
openalgo_root = os.path.join(repo_root, 'openalgo')
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DBInit")

def main():
    logger.info("Starting Database Initialization...")

    # Load env variables
    try:
        from openalgo.utils.env_check import load_and_check_env_variables
        load_and_check_env_variables()
    except Exception as e:
        logger.error(f"Environment check failed: {e}")
        # Continue as we might be running in a partial env to just init DB

    # Init Auth DB
    try:
        from openalgo.database.auth_db import init_db as init_auth_db
        logger.info("Initializing Auth Database...")
        init_auth_db()
        logger.info("Auth Database Initialized.")
    except Exception as e:
        logger.error(f"Auth Database Initialization Failed: {e}")

    # Init User DB
    try:
        from openalgo.database.user_db import init_db as init_user_db
        logger.info("Initializing User Database...")
        init_user_db()
        logger.info("User Database Initialized.")
    except ImportError:
        logger.warning("User Database module not found.")
    except Exception as e:
        logger.error(f"User Database Initialization Failed: {e}")

if __name__ == "__main__":
    main()
