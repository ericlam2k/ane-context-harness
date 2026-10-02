"""Tests for symbol extraction (Python AST + JS/TS regex)."""
from __future__ import annotations

from src.ane_context_harness.indexing.symbols import extract_symbols, _python_symbols, _js_symbols

PY_SRC = """\
import os

class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

def helper(x):
    return x * 2
"""


def test_python_function_and_class_symbols():
    syms = _python_symbols(PY_SRC)
    names = [s[0] for s in syms]
    assert "Calculator" in names
    assert "add" in names
    assert "subtract" in names
    assert "helper" in names


def test_python_symbol_line_spans():
    syms = dict((s[0], (s[1], s[2])) for s in _python_symbols(PY_SRC))
    start, end = syms["Calculator"]
    assert start < end
    a_start, a_end = syms["add"]
    assert a_start <= a_end


def test_python_syntax_error_returns_empty():
    assert _python_symbols("def (") == []


def test_extract_symbols_dispatches_by_language():
    assert extract_symbols("python", PY_SRC) == _python_symbols(PY_SRC)
    assert extract_symbols("unknown", PY_SRC) == []


TS_SRC = """\
export function calculateDiscount(price: number, rate: number): number {
  return price - price * rate;
}

export class Inventory {
  add(sku: string, qty: number): void {}
}
"""


def test_js_function_and_class_symbols():
    syms = _js_symbols(TS_SRC)
    names = [s[0] for s in syms]
    assert "calculateDiscount" in names
    assert "Inventory" in names


def test_js_symbol_line_positive():
    syms = dict((s[0], s[1]) for s in _js_symbols(TS_SRC))
    assert syms["calculateDiscount"] > 0


TS_TYPES_SRC = """\
export interface CartLine {
  sku: string;
  qty: number;
}

export type LoyaltyTier = "bronze" | "silver" | "gold" | "none";

type InternalAlias = number;

export enum Color { Red, Green }

import type { RemoteFoo } from "./foo";
export type { ReExportedBar };
"""


def test_js_interface_type_enum_extracted():
    names = [s[0] for s in _js_symbols(TS_TYPES_SRC)]
    assert "CartLine" in names
    assert "LoyaltyTier" in names
    assert "InternalAlias" in names
    assert "Color" in names
    # `import type {` / `export type {` are not declarations
    assert "RemoteFoo" not in names
    assert "ReExportedBar" not in names


def test_js_type_symbol_spans():
    syms = dict((s[0], (s[1], s[2])) for s in _js_symbols(TS_TYPES_SRC))
    start, end = syms["CartLine"]
    assert start <= end
    # block interface spans past its declaration line
    assert end > start
    # `;`-terminated union alias is single-line
    ls, le = syms["LoyaltyTier"]
    assert ls == le
