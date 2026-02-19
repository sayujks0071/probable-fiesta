import unittest
from datetime import date
from openalgo.strategies.utils.mcx_utils import format_mcx_symbol, normalize_mcx_string

class TestMCXFormattingStrict(unittest.TestCase):
    def test_goldm_mini_strict(self):
        # GOLDM05FEB26FUT for date(2026,2,5) with mini=True
        result = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=True)
        self.assertEqual(result, "GOLDM05FEB26FUT")

    def test_silverm_mini_strict(self):
        # SILVERM27FEB26FUT for date(2026,2,27) with mini=True
        result = format_mcx_symbol("SILVER", date(2026, 2, 27), mini=True)
        self.assertEqual(result, "SILVERM27FEB26FUT")

    def test_crudeoil_strict(self):
        # CRUDEOIL19FEB26FUT for date(2026,2,19) with mini=False
        result = format_mcx_symbol("CRUDEOIL", date(2026, 2, 19), mini=False)
        self.assertEqual(result, "CRUDEOIL19FEB26FUT")

    def test_zero_padding_dd(self):
        # Test 1st day of month -> 01
        result = format_mcx_symbol("GOLD", date(2026, 2, 1), mini=False)
        self.assertEqual(result, "GOLD01FEB26FUT")

    def test_mmm_uppercase(self):
        # Test lowercase month input handling (though date object handles it, check result)
        # August -> AUG
        result = format_mcx_symbol("GOLD", date(2026, 8, 5), mini=False)
        self.assertIn("AUG", result)

    def test_yy_correct(self):
        # 2026 -> 26
        result = format_mcx_symbol("GOLD", date(2026, 2, 5), mini=False)
        self.assertTrue(result.endswith("26FUT"))

        # 2030 -> 30
        result = format_mcx_symbol("GOLD", date(2030, 2, 5), mini=False)
        self.assertTrue(result.endswith("30FUT"))

    def test_normalization(self):
        # Test normalization of malformed strings
        # GOLDM 5 FEB 26 FUT -> GOLDM05FEB26FUT
        malformed = "GOLDM05feb26FUT" # mixed case month
        result = normalize_mcx_string(malformed)
        self.assertEqual(result, "GOLDM05FEB26FUT")

if __name__ == '__main__':
    unittest.main()
