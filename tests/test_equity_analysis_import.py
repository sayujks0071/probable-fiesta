import sys
import os
import logging
sys.path.append(os.getcwd())

try:
    from openalgo.strategies.utils.equity_analysis import EquityAnalyzer
    print("Import successful")
    analyzer = EquityAnalyzer(api_key="test", host="http://127.0.0.1:5001")
    print("Instance created")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)
