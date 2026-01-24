import os
import json
import logging
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger("StrategyConfig")

class StrategyConfig:
    """
    Configuration loader for OpenAlgo strategies.
    Prioritizes Environment Variables > strategy_env.json > Defaults.
    """
    def __init__(self, strategy_name: Optional[str] = None):
        self.strategy_name = strategy_name
        self.env_data = self._load_json_config()

    def _load_json_config(self) -> dict:
        """Load strategy_env.json if it exists."""
        try:
            # openalgo/strategies/utils/config.py -> openalgo/strategies/
            base_dir = Path(__file__).resolve().parent.parent
            env_path = base_dir / "strategy_env.json"

            if env_path.exists():
                with open(env_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load strategy_env.json: {e}")
        return {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value.
        1. Check OS Environment Variable.
        2. Check strategy-specific config in JSON.
        3. Check 'default' or 'global' config in JSON.
        4. Return default.
        """
        # 1. OS Env
        val = os.getenv(key)
        if val is not None:
            return val

        # 2. Strategy specific in JSON
        if self.strategy_name and self.strategy_name in self.env_data:
            strat_config = self.env_data[self.strategy_name]
            if isinstance(strat_config, dict) and key in strat_config:
                return strat_config[key]

        # 3. Global/Default in JSON
        if "default" in self.env_data and isinstance(self.env_data["default"], dict):
             if key in self.env_data["default"]:
                 return self.env_data["default"][key]

        return default

    @property
    def api_key(self) -> str:
        """Get API Key with fallback logic."""
        # Common keys used: OPENALGO_APIKEY, API_KEY
        val = self.get("OPENALGO_APIKEY")
        if not val:
            val = self.get("API_KEY")
        if not val:
            return "demo_key"
        return val

    @property
    def host(self) -> str:
        """Get Host URL."""
        return self.get("OPENALGO_HOST", "http://127.0.0.1:5001")
