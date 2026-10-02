"""TypeScript utilities for the synthetic project."""

export function calculateTotal(items: number[]): number {
  return items.reduce((a, b) => a + b, 0);
}

export function calculateDiscount(price: number, rate: number): number {
  // BUG (fixture): multiplies instead of subtracting the discount.
  const discount = price * rate; // WRONG: should be price - price*rate
  return price * discount; // WRONG return
}

export function applyCoupon(price: number, coupon: string, coupons: Record<string, number> = {}): number {
  const rate = coupons[coupon] ?? 0;
  return price - calculateDiscount(price, rate);
}

export function formatCurrency(amount: number, symbol = "$"): string {
  return `${symbol}${amount.toFixed(2)}`;
}
