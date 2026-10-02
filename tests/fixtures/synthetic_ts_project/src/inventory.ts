// Inventory management (distractor, verbose).
export interface SKU {
  id: string;
  qty: number;
}

export class Inventory {
  private items: Record<string, number> = {};

  add(sku: string, qty: number): void {
    this.items[sku] = (this.items[sku] ?? 0) + qty;
  }

  remove(sku: string, qty: number): number {
    this.items[sku] = Math.max(0, (this.items[sku] ?? 0) - qty);
    return this.items[sku] ?? 0;
  }
}

export function reconcile(inv: Inventory, expected: Record<string, number>): Record<string, [number, number]> {
  const diffs: Record<string, [number, number]> = {};
  for (const [sku, exp] of Object.entries(expected)) {
    const actual = inv.items[sku] ?? 0;
    if (actual !== exp) diffs[sku] = [actual, exp];
  }
  return diffs;
}

export function bulkImport(rows: SKU[]): Inventory {
  const wh = new Inventory();
  for (const r of rows) wh.add(r.id, r.qty);
  return wh;
}
