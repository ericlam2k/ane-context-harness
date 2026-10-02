"""Tests for the discount calculation."""
import unittest
from src.discount import calculate_discount, calculate_total_with_discount, apply_coupon, format_currency


class TestDiscount(unittest.TestCase):
    def test_calculate_discount(self):
        # price=100, rate=0.2 -> discount should be 20, final 80
        result = calculate_discount(100, 0.2)
        self.assertAlmostEqual(result, 80.0, places=2)

    def test_calculate_total_with_discount(self):
        self.assertAlmostEqual(calculate_total_with_discount(100, 0.2), 80.0, places=2)

    def test_apply_coupon(self):
        coupons = {"SAVE10": 0.1}
        self.assertAlmostEqual(apply_coupon(100, "SAVE10", coupons), 90.0, places=2)

    def test_format_currency(self):
        self.assertEqual(format_currency(80.0), "$80.00")


if __name__ == "__main__":
    unittest.main()
