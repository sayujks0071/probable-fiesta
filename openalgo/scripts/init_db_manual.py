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

from openalgo.utils.env_check import load_and_check_env_variables
load_and_check_env_variables()

from openalgo.database.auth_db import init_db as init_auth_db
from openalgo.database.user_db import init_db as init_user_db

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Initializing Auth DB...")
    init_auth_db()
    print("Initializing User DB...")
    try:
        init_user_db()
    except Exception as e:
        print(f"User DB init skipped/failed: {e}")
    print("Done.")
