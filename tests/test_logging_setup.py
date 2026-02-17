import unittest
import logging
import os
import shutil
from openalgo_observability.logging_setup import setup_logging, SensitiveDataFilter

class TestLoggingSetup(unittest.TestCase):
    def setUp(self):
        # Reset logging setup done flag
        if 'OPENALGO_LOGGING_SETUP_DONE' in os.environ:
            del os.environ['OPENALGO_LOGGING_SETUP_DONE']

        # Clean up logs
        self.log_dir = os.path.join(os.path.dirname(__file__), '../logs')
        self.log_file = os.path.join(self.log_dir, 'openalgo.log')
        if os.path.exists(self.log_file):
            os.remove(self.log_file)

    def test_redaction(self):
        setup_logging()
        logger = logging.getLogger("test_logger")

        secret = "12345secret"
        logger.info(f"My api_key={secret}")

        # Check file content
        with open(self.log_file, 'r') as f:
            content = f.read()
            self.assertIn("api_key=[REDACTED]", content)
            self.assertNotIn(secret, content)

if __name__ == '__main__':
    unittest.main()
