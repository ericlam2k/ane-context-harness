"""Symbol extraction for priority languages.

Python: uses the stdlib `ast` parser for robust, correct symbol spans.
JS/TS (js, ts, jsx, tsx): regex-based extraction (no JS parser dependency).
Each entry is (name, start_line, end_line) with 1-based inclusive line numbers.
"""
from __future__ import annotations

import ast
import re


def extract_symbols(language: str, content: str) -> list:
    if language == "python" or (not language and content.lstrip().startswith(("def ", "class ", "import"))):
        return _python_symbols(content)
    if language in ("javascript", "typescript", "jsx", "tsx"):
        return _js_symbols(content)
    return []


def _line_for(ast_node, src_lines: list) -> int:
    # ast uses 1-based lineno already
    return getattr(ast_node, "lineno", 1)


def _python_symbols(content: str) -> list:
    """Return [(name, start, end)] using ast. end = last line of the node block."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            # end_lineno available in 3.8+
            end = getattr(node, "end_lineno", start)
            # if no body lines, end_lineno may be start
            out.append((node.name, start, end or start))
    return out


_JS_IDENT = r"[A-Za-z_$][\w$]*"
_JS_FUNC = re.compile(
    r"(?:export\s+)?(?:async\s+|static\s+|get\s+|set\s+|default\s+)?"
    r"function(?:\s+\*)?\s+(" + _JS_IDENT + r")\s*\(",
)
_JS_CLASS = re.compile(r"(?:export\s+)?class\s+(" + _JS_IDENT + r")")
_JS_METHOD = re.compile(r"(?:static\s+|async\s+)?(" + _JS_IDENT + r")\s*\(")
_JS_VAR = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(" + _JS_IDENT + r")\s*="
)
# TS type-level declarations: interface Foo {...}, type Bar = ...
# (export/declare modifiers optional; `import type {` / `export type {` do not
# match because `{` is not an identifier.)
_JS_TYPE = re.compile(
    r"\b(?:(?:export|declare|abstract)\s+)*(?:interface|type|enum)\s+("
    + _JS_IDENT + r")\b"
)


def _js_symbols(content: str) -> list:
    out = []
    seen_ranges = set()
    lines = content.splitlines()

    def _end_for(start_idx: int) -> int:
        """Best-effort end line: brace balance from start until balanced (cap at 200)."""
        depth = 0
        started = False
        for idx in range(start_idx, min(len(lines), start_idx + 200)):
            for ch in lines[idx]:
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
            if started and depth <= 0:
                return idx + 1  # 1-based inclusive
        return min(start_idx + 60, len(lines))

    for m in _JS_FUNC.finditer(content):
        name = m.group(1)
        ln = content[:m.start()].count("\n") + 1
        end = _end_for(ln - 1)
        out.append((name, ln, end))
    for m in _JS_CLASS.finditer(content):
        name = m.group(1)
        ln = content[:m.start()].count("\n") + 1
        end = _end_for(ln - 1)
        out.append((name, ln, end))
    def _type_end_for(start_idx: int) -> int:
        """End line for a type-level declaration.

        Brace-balanced when the declaration opens a block (interface/object
        type); otherwise the line that terminates it with `;` (union/alias).
        """
        depth = 0
        started = False
        for idx in range(start_idx, min(len(lines), start_idx + 100)):
            for ch in lines[idx]:
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
            if started and depth <= 0:
                return idx + 1
            if not started and ";" in lines[idx]:
                return idx + 1
        return start_idx + 1

    for m in _JS_TYPE.finditer(content):
        name = m.group(1)
        ln = content[:m.start()].count("\n") + 1
        end = _type_end_for(ln - 1)
        out.append((name, ln, end))
    for m in _JS_VAR.finditer(content):
        name = m.group(1)
        ln = content[:m.start()].count("\n") + 1
        out.append((name, ln, ln + 1))
    # de-dup by (name, start)
    dedup = {}
    for name, s, e in out:
        dedup.setdefault((name, s), (name, s, e))
    return list(dedup.values())
