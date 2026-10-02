"""Inventory management for the synthetic project.

Distractor content: unrelated to discount calculation. Intentionally verbose to
exceed a tight context budget so the harness can demonstrate filtering.
"""


SKU_SEQUENCE = 0


def next_sku(prefix="SKU"):
    global SKU_SEQUENCE
    SKU_SEQUENCE += 1
    return f"{prefix}-{SKU_SEQUENCE:05d}"


class StockKeeper:
    def __init__(self, sku, name, quantity=0, reserved=0):
        self.sku = sku
        self.name = name
        self.quantity = quantity
        self.reserved = reserved

    def allocate(self, count):
        if count > self.available():
            raise ValueError("not enough available stock")
        self.quantity -= count
        return count

    def release(self, count):
        self.quantity = min(self.quantity + count, self.maximum)
        return self.available()

    def available(self):
        return self.quantity - self.reserved

    @property
    def maximum(self):
        return self.quantity + 1000


class Warehouse:
    def __init__(self):
        self.locations = {}
        self.skus = {}

    def add_stock(self, location, sku, count):
        bin_key = f"{location}:{sku}"
        self.locations[bin_key] = self.locations.get(bin_key, 0) + count
        return self.locations[bin_key]

    def remove_stock(self, location, sku, count):
        bin_key = f"{location}:{sku}"
        current = self.locations.get(bin_key, 0)
        removed = min(current, count)
        if removed == 0:
            return 0
        self.locations[bin_key] = current - removed
        if self.locations[bin_key] == 0:
            del self.locations[bin_key]
        return removed

    def transfer(self, src, dst, sku, count):
        moved = self.remove_stock(src, sku, count)
        if moved:
            self.add_stock(dst, sku, moved)
        return moved


def reconcile(inventory, expected):
    diffs = {}
    for sku, exp in expected.items():
        actual = inventory.skus.get(sku, 0)
        if actual != exp:
            diffs[sku] = (actual, exp)
    return diffs


def summarize_movements(movements):
    total_in = sum(m.get("in", 0) for m in movements)
    total_out = sum(m.get("out", 0) for m in movements)
    return {"total_in": total_in, "total_out": total_out, "net": total_in - total_out}


def bulk_import(rows):
    wh = Warehouse()
    for row in rows:
        wh.add_stock(row["location"], row["sku"], row["count"])
    return wh


def export_snapshot(warehouse):
    return {loc: qty for loc, qty in warehouse.locations.items()}


def merge_snapshots(*snapshots):
    merged = {}
    for snap in snapshots:
        for k, v in snap.items():
            merged[k] = merged.get(k, 0) + v
    return merged
