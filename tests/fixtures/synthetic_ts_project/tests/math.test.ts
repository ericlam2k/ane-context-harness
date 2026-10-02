// Tests for discount and total helpers.
import { calculateDiscount, calculateTotal, applyCoupon, formatCurrency } from "../src/math";

describe("math", () => {
  test("calculate_total", () => {
    expect(calculateTotal([1, 2, 3])).toBe(6);
  });

  test("calculate_discount", () => {
    expect(calculateDiscount(100, 0.2)).toBeCloseTo(80, 2);
  });

  test("apply_coupon", () => {
    expect(applyCoupon(100, "SAVE10", { SAVE10: 0.1 })).toBeCloseTo(90, 2);
  });

  test("format_currency", () => {
    expect(formatCurrency(80)).toBe("$80.00");
  });
});
