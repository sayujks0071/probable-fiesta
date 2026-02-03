import sys
import os

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Add openalgo directory to path
openalgo_root = os.path.join(repo_root, 'openalgo')
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

from openalgo.utils.env_check import load_and_check_env_variables
try:
    load_and_check_env_variables()
except SystemExit:
    pass # Ignore exit if some vars are missing, we just need enough for DB

from openalgo.database.auth_db import init_db as init_auth
from openalgo.database.user_db import init_db as init_user
from openalgo.database.strategy_db import init_db as init_strat

print("Initializing DBs...")
try:
    init_auth()
    print("Auth DB initialized.")
    init_user()
    print("User DB initialized.")
    init_strat()
    print("Strategy DB initialized.")
except Exception as e:
    print(f"Error initializing DB: {e}")
