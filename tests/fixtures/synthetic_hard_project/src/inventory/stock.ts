// Clearance/stock cost helpers. Shares "discount"/"markdown" vocabulary with
// the pricing modules but is about warehouse stock (hard case: domain-adjacent
// distractor).

import { computeDiscount } from "../discounts/apply";

export interface StockItem {
  sku: string;
  cost: number;
  units: number;
}

export function clearanceMarkdown(item: StockItem, ageDays: number): number {
  // BUG (fixture): double-applies the clearance concession.
  const once = item.cost - computeDiscount(item.cost, Math.min(ageDays / 100, 0.5));
  return once - computeDiscount(once, Math.min(ageDays / 100, 0.5));
}

export function stockValue(items: StockItem[]): number {
  return items.reduce((sum, item) => sum + item.cost * item.units, 0);
}

export function lowStockSkus(items: StockItem[], threshold: number): string[] {
  return items.filter((item) => item.units < threshold).map((item) => item.sku);
}
