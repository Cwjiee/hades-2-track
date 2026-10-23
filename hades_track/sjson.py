"""Minimal parser for Supergiant's .sjson text format.

The format is Lua-table-like rather than JSON:
    {
      lang = "en"        // bare or quoted keys, '=' instead of ':'
      Texts = [
        { Id = "Foo" DisplayName = "Bar" }
      ]
    }
Comments use /* ... */ and //. Array-style tables use [ ... ] with either bare
values or `key = value` pairs. Good enough for the game's Text/en/*.sjson.
"""

from __future__ import annotations


class SjsonError(ValueError):
    pass


class _Lexer:
    def __init__(self, text: str):
        self.text = text
        self.i = 0
        self.n = len(text)

    def skip(self) -> None:
        while self.i < self.n:
            ch = self.text[self.i]
            if ch in " \t\r\n,":
                self.i += 1
            elif self.text.startswith("//", self.i):
                nl = self.text.find("\n", self.i)
                self.i = self.n if nl < 0 else nl + 1
            elif self.text.startswith("/*", self.i):
                end = self.text.find("*/", self.i + 2)
                self.i = self.n if end < 0 else end + 2
            else:
                return

    def peek(self) -> str:
        self.skip()
        return self.text[self.i] if self.i < self.n else ""

    def string(self) -> str:
        quote = self.text[self.i]
        if quote == '"' and self.text.startswith('"""', self.i):
            end = self.text.find('"""', self.i + 3)
            if end < 0:
                raise SjsonError("unterminated triple-quoted string")
            raw = self.text[self.i + 3:end]
            self.i = end + 3
            return raw
        self.i += 1
        out = []
        while self.i < self.n:
            ch = self.text[self.i]
            if ch == "\\" and self.i + 1 < self.n:
                nxt = self.text[self.i + 1]
                out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                self.i += 2
                continue
            if ch == quote:
                self.i += 1
                return "".join(out)
            out.append(ch)
            self.i += 1
        raise SjsonError("unterminated string")

    def bare(self) -> str:
        start = self.i
        while self.i < self.n and self.text[self.i] not in " \t\r\n,=]}{[\"/":
            self.i += 1
        return self.text[start:self.i]


def _value(lx: _Lexer):
    ch = lx.peek()
    if ch == "":
        raise SjsonError("unexpected end of input")
    if ch in "\"'":
        return lx.string()
    if ch == "{":
        return _table(lx, close="}")
    if ch == "[":
        return _table(lx, close="]")
    word = lx.bare()
    if word == "":
        raise SjsonError(f"unexpected {lx.text[lx.i]!r} at {lx.i}")
    low = word.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("nil", "null"):
        return None
    try:
        return int(word) if word.lstrip("+-").isdigit() else float(word)
    except ValueError:
        return word


def _table(lx: _Lexer, close: str):
    lx.i += 1  # consume { or [
    out: dict = {}
    n = 0
    while True:
        ch = lx.peek()
        if ch == "":
            raise SjsonError("unterminated table")
        if ch == close:
            lx.i += 1
            # pure array tables (1..n keys) read better as lists
            if out and all(isinstance(k, int) for k in out):
                return [out[i] for i in range(1, len(out) + 1)]
            return out
        key = _value(lx)
        if lx.peek() == "=":
            lx.i += 1
            out[key] = _value(lx)
        else:
            n += 1
            out[n] = key


def loads(text: str) -> dict:
    lx = _Lexer(text)
    val = _value(lx)
    return val if isinstance(val, dict) else {"value": val}


def load_file(path) -> dict:
    with open(path, encoding="utf-8-sig") as fh:
        return loads(fh.read())
