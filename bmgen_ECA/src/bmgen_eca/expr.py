"""Expression lexer / parser / lowerer for schema_v2 ECA expressions.

Surface: $state.x | $para.x | $[Bus]Frame.Signal | lit | + - * / | compares |
and/or | parens | min/max/abs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Union

from bmgen_eca.diagnostics import Diag, make_diag
from bmgen_eca.signals import SignalId, parse_signal_id

# ── AST ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Lit:
    value: bool | int | float


@dataclass(frozen=True)
class StateRef:
    name: str


@dataclass(frozen=True)
class ParamRef:
    name: str


@dataclass(frozen=True)
class SignalRef:
    signal: SignalId


@dataclass(frozen=True)
class UnaryOp:
    op: str  # "-"
    operand: "ExprAST"


@dataclass(frozen=True)
class BinOp:
    op: str  # + - * /
    left: "ExprAST"
    right: "ExprAST"


@dataclass(frozen=True)
class Compare:
    op: str  # == != > >= < <=
    left: "ExprAST"
    right: "ExprAST"


@dataclass(frozen=True)
class BoolOp:
    op: str  # and | or
    left: "ExprAST"
    right: "ExprAST"


@dataclass(frozen=True)
class Call:
    fn: str  # min | max | abs
    args: tuple["ExprAST", ...]


ExprAST = Union[Lit, StateRef, ParamRef, SignalRef, UnaryOp, BinOp, Compare, BoolOp, Call]

_ALLOWED_FNS = frozenset({"min", "max", "abs"})

# ── Lexer ────────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"""
    \s*
    (
        \$\[ [^\]]+ \] [A-Za-z_][\w]* \. [A-Za-z_][\w]*   # $[Bus]Frame.Signal
      | \$state \. [A-Za-z_][\w]*                         # $state.name
      | \$para  \. [A-Za-z_][\w]*                         # $para.name
      | \$ [A-Za-z_][\w.]*                                # bare $… (error later)
      | == | != | >= | <= | > | <
      | [+\-*/(),]
      | \d+\.\d+ | \d+
      | true | false
      | and | or
      | [A-Za-z_][\w]*
    )
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class _Tok:
    kind: str
    value: Any
    pos: int


def _lex(text: str, *, rule_id: str, path: str) -> tuple[list[_Tok], list[Diag]]:
    toks: list[_Tok] = []
    diags: list[Diag] = []
    i = 0
    n = len(text)
    while i < n:
        m = _TOKEN_RE.match(text, i)
        if not m:
            # skip pure whitespace at end; else bad
            ws = re.match(r"\s+", text[i:])
            if ws and i + ws.end() >= n:
                break
            diags.append(
                make_diag(
                    "E_BAD_EXPR",
                    f"unexpected input near `{text[i:i+20]}`",
                    path=path,
                    rule_id=rule_id,
                    symbol=text,
                )
            )
            return [], diags
        raw = m.group(1)
        pos = m.start(1)
        i = m.end()

        if raw.startswith("$[") and "]" in raw:
            toks.append(_Tok("SIGNAL", raw, pos))
        elif raw.startswith("$state."):
            toks.append(_Tok("STATE", raw[len("$state.") :], pos))
        elif raw.startswith("$para."):
            toks.append(_Tok("PARA", raw[len("$para.") :], pos))
        elif raw.startswith("$"):
            toks.append(_Tok("BARE", raw, pos))
        elif raw in ("==", "!=", ">=", "<=", ">", "<"):
            toks.append(_Tok("CMP", raw, pos))
        elif raw in "+-*/(),":
            toks.append(_Tok(raw, raw, pos))
        elif raw == "true":
            toks.append(_Tok("LIT", True, pos))
        elif raw == "false":
            toks.append(_Tok("LIT", False, pos))
        elif raw == "and":
            toks.append(_Tok("AND", raw, pos))
        elif raw == "or":
            toks.append(_Tok("OR", raw, pos))
        elif re.fullmatch(r"\d+\.\d+", raw):
            toks.append(_Tok("LIT", float(raw), pos))
        elif re.fullmatch(r"\d+", raw):
            toks.append(_Tok("LIT", int(raw), pos))
        elif re.fullmatch(r"[A-Za-z_][\w]*", raw):
            toks.append(_Tok("IDENT", raw, pos))
        else:
            diags.append(
                make_diag(
                    "E_BAD_EXPR",
                    f"unrecognized token `{raw}`",
                    path=path,
                    rule_id=rule_id,
                    symbol=raw,
                )
            )
            return [], diags
    toks.append(_Tok("EOF", None, n))
    return toks, diags


# ── Parser ───────────────────────────────────────────────────────────────────


class _Parser:
    def __init__(self, toks: list[_Tok], *, rule_id: str, path: str, text: str):
        self.toks = toks
        self.i = 0
        self.rule_id = rule_id
        self.path = path
        self.text = text
        self.diags: list[Diag] = []

    def _cur(self) -> _Tok:
        return self.toks[self.i]

    def _eat(self, kind: str | None = None) -> _Tok:
        t = self._cur()
        if kind is not None and t.kind != kind:
            self.diags.append(
                make_diag(
                    "E_BAD_EXPR",
                    f"expected {kind}, got {t.kind}",
                    path=self.path,
                    rule_id=self.rule_id,
                    symbol=self.text,
                )
            )
            return t
        self.i += 1
        return t

    def parse(self) -> ExprAST | None:
        if self._cur().kind == "EOF":
            self.diags.append(
                make_diag(
                    "E_BAD_EXPR",
                    "empty expression",
                    path=self.path,
                    rule_id=self.rule_id,
                    symbol=self.text,
                )
            )
            return None
        node = self._or()
        if self._cur().kind != "EOF":
            self.diags.append(
                make_diag(
                    "E_BAD_EXPR",
                    f"trailing input at `{self._cur().kind}`",
                    path=self.path,
                    rule_id=self.rule_id,
                    symbol=self.text,
                )
            )
        if self.diags:
            return None
        return node

    def _or(self) -> ExprAST | None:
        left = self._and()
        while left is not None and self._cur().kind == "OR":
            self._eat("OR")
            right = self._and()
            if right is None:
                return None
            left = BoolOp("or", left, right)
        return left

    def _and(self) -> ExprAST | None:
        left = self._compare()
        while left is not None and self._cur().kind == "AND":
            self._eat("AND")
            right = self._compare()
            if right is None:
                return None
            left = BoolOp("and", left, right)
        return left

    def _compare(self) -> ExprAST | None:
        left = self._add()
        if left is None:
            return None
        if self._cur().kind == "CMP":
            op = self._eat("CMP").value
            right = self._add()
            if right is None:
                return None
            return Compare(op, left, right)
        return left

    def _add(self) -> ExprAST | None:
        left = self._mul()
        while left is not None and self._cur().kind in ("+", "-"):
            op = self._eat().value
            right = self._mul()
            if right is None:
                return None
            left = BinOp(op, left, right)
        return left

    def _mul(self) -> ExprAST | None:
        left = self._unary()
        while left is not None and self._cur().kind in ("*", "/"):
            op = self._eat().value
            right = self._unary()
            if right is None:
                return None
            left = BinOp(op, left, right)
        return left

    def _unary(self) -> ExprAST | None:
        if self._cur().kind == "-":
            self._eat("-")
            operand = self._unary()
            if operand is None:
                return None
            return UnaryOp("-", operand)
        return self._primary()

    def _primary(self) -> ExprAST | None:
        t = self._cur()
        if t.kind == "LIT":
            self._eat()
            return Lit(t.value)
        if t.kind == "STATE":
            self._eat()
            return StateRef(t.value)
        if t.kind == "PARA":
            self._eat()
            return ParamRef(t.value)
        if t.kind == "SIGNAL":
            self._eat()
            # strip leading $ then parse SignalId
            raw = t.value[1:] if t.value.startswith("$") else t.value
            sid, diag = parse_signal_id(raw, path=self.path)
            if diag is not None or sid is None:
                self.diags.append(
                    make_diag(
                        "E_BAD_EXPR",
                        f"bad signal ref `{t.value}`",
                        path=self.path,
                        rule_id=self.rule_id,
                        symbol=t.value,
                    )
                )
                return None
            return SignalRef(sid)
        if t.kind == "BARE":
            self.diags.append(
                make_diag(
                    "E_BARE_IDENT",
                    f"bare identifier `{t.value}` (need $state./$para./$[Bus])",
                    path=self.path,
                    rule_id=self.rule_id,
                    symbol=t.value,
                )
            )
            self._eat()
            return None
        if t.kind == "IDENT":
            name = t.value
            self._eat()
            if self._cur().kind != "(":
                self.diags.append(
                    make_diag(
                        "E_BAD_EXPR",
                        f"bare identifier `{name}` not allowed (only min/max/abs calls)",
                        path=self.path,
                        rule_id=self.rule_id,
                        symbol=name,
                    )
                )
                return None
            if name not in _ALLOWED_FNS:
                self.diags.append(
                    make_diag(
                        "E_UNKNOWN_FUNCTION",
                        f"unknown function `{name}` (only min/max/abs)",
                        path=self.path,
                        rule_id=self.rule_id,
                        symbol=name,
                    )
                )
                # still try to consume args so we don't cascade
                self._eat("(")
                self._skip_until_rparen()
                return None
            self._eat("(")
            args: list[ExprAST] = []
            if self._cur().kind != ")":
                while True:
                    arg = self._or()
                    if arg is None:
                        return None
                    args.append(arg)
                    if self._cur().kind == ",":
                        self._eat(",")
                        continue
                    break
            if self._cur().kind != ")":
                self.diags.append(
                    make_diag(
                        "E_BAD_EXPR",
                        f"expected `)` after {name}(...)",
                        path=self.path,
                        rule_id=self.rule_id,
                        symbol=self.text,
                    )
                )
                return None
            self._eat(")")
            if name == "abs" and len(args) != 1:
                self.diags.append(
                    make_diag(
                        "E_BAD_EXPR",
                        "abs() takes exactly 1 argument",
                        path=self.path,
                        rule_id=self.rule_id,
                        symbol="abs",
                    )
                )
                return None
            if name in ("min", "max") and len(args) < 1:
                self.diags.append(
                    make_diag(
                        "E_BAD_EXPR",
                        f"{name}() needs at least 1 argument",
                        path=self.path,
                        rule_id=self.rule_id,
                        symbol=name,
                    )
                )
                return None
            return Call(name, tuple(args))
        if t.kind == "(":
            self._eat("(")
            node = self._or()
            if node is None:
                return None
            if self._cur().kind != ")":
                self.diags.append(
                    make_diag(
                        "E_BAD_EXPR",
                        "unbalanced parentheses",
                        path=self.path,
                        rule_id=self.rule_id,
                        symbol=self.text,
                    )
                )
                return None
            self._eat(")")
            return node
        self.diags.append(
            make_diag(
                "E_BAD_EXPR",
                f"unexpected token `{t.kind}`",
                path=self.path,
                rule_id=self.rule_id,
                symbol=self.text,
            )
        )
        return None

    def _skip_until_rparen(self) -> None:
        depth = 1
        while self._cur().kind != "EOF" and depth:
            if self._cur().kind == "(":
                depth += 1
            elif self._cur().kind == ")":
                depth -= 1
            self.i += 1


def parse_expr(
    text: str, *, rule_id: str = "", path: str = ""
) -> tuple[ExprAST | None, list[Diag]]:
    toks, diags = _lex(text, rule_id=rule_id, path=path)
    if diags:
        return None, diags
    p = _Parser(toks, rule_id=rule_id, path=path, text=text)
    node = p.parse()
    return node, p.diags


# ── free_refs ────────────────────────────────────────────────────────────────


def free_refs(expr: ExprAST) -> list[tuple[str, str]]:
    """Return free references as (kind, name_or_raw) where kind ∈ state|para|rx."""
    out: list[tuple[str, str]] = []

    def walk(n: ExprAST) -> None:
        if isinstance(n, StateRef):
            out.append(("state", n.name))
        elif isinstance(n, ParamRef):
            out.append(("para", n.name))
        elif isinstance(n, SignalRef):
            out.append(("rx", n.signal.raw))
        elif isinstance(n, UnaryOp):
            walk(n.operand)
        elif isinstance(n, (BinOp, Compare, BoolOp)):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, Call):
            for a in n.args:
                walk(a)
        # Lit: nothing

    walk(expr)
    return out


# ── lower ────────────────────────────────────────────────────────────────────

_SNAKE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z0-9])([A-Z])")


def _snake_case(name: str) -> str:
    s1 = _SNAKE_1.sub(r"\1_\2", name)
    return _SNAKE_2.sub(r"\1_\2", s1).lower()


def lower_expr(
    expr: ExprAST, *, signal_locals: dict[str, str] | None = None
) -> str:
    """Lower ExprAST to Python source string."""
    locs = signal_locals or {}

    def low(n: ExprAST) -> str:
        if isinstance(n, Lit):
            if n.value is True:
                return "True"
            if n.value is False:
                return "False"
            return repr(n.value)
        if isinstance(n, StateRef):
            return f"self.{n.name}"
        if isinstance(n, ParamRef):
            return f"self.{n.name}"
        if isinstance(n, SignalRef):
            if n.signal.raw in locs:
                return locs[n.signal.raw]
            return _snake_case(n.signal.signal)
        if isinstance(n, UnaryOp):
            return f"({n.op}{low(n.operand)})"
        if isinstance(n, BinOp):
            return f"({low(n.left)} {n.op} {low(n.right)})"
        if isinstance(n, Compare):
            return f"({low(n.left)} {n.op} {low(n.right)})"
        if isinstance(n, BoolOp):
            return f"({low(n.left)} {n.op} {low(n.right)})"
        if isinstance(n, Call):
            args = ", ".join(low(a) for a in n.args)
            if n.fn == "min":
                return f"np.minimum.reduce([{args}])"
            if n.fn == "max":
                return f"np.maximum.reduce([{args}])"
            if n.fn == "abs":
                return f"np.abs({args})"
            raise ValueError(f"unknown fn in lower: {n.fn}")
        raise TypeError(f"unknown AST node: {type(n)}")

    return low(expr)
