
import sys
import os

# Add repo root to path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Add openalgo directory to path (so imports like 'from utils ...' work)
openalgo_root = os.path.join(repo_root, 'openalgo')
if openalgo_root not in sys.path:
    sys.path.insert(0, openalgo_root)

# Setup logging
import logging
logging.basicConfig(level=logging.INFO)

print("Initializing Database...")

try:
    # 1. Import openalgo package
    import openalgo

    # 2. Patch openalgo.api with APIClient
    from openalgo.strategies.utils.trading_utils import APIClient
    openalgo.api = APIClient
    print("Patched openalgo.api")

    # 3. Import app (this initializes the app and triggers DB creation)
    from openalgo.app import app
    print("App imported successfully. DBs should be initialized.")

except Exception as e:
    print(f"Error initializing DB: {e}")
    import traceback
    traceback.print_exc()
