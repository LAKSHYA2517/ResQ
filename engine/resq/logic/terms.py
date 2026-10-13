"""FOL-lite syntax: constants, variables, function terms, atoms, Horn rules, and a parser.

Convention (as in the brief): inside an argument list an identifier starting with an uppercase
letter is a variable, anything else is a constant. ``f(...)`` in argument position is a function
term. The leading identifier of an atom is its predicate.
"""

import re
from dataclasses import dataclass

type Term = Var | Const | Fn


@dataclass(frozen=True, slots=True)
class Var:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Const:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Fn:
    name: str
    args: tuple[Term, ...]

    def __str__(self) -> str:
        return f"{self.name}({', '.join(map(str, self.args))})"


@dataclass(frozen=True, slots=True)
class Atom:
    pred: str
    args: tuple[Term, ...] = ()

    def __str__(self) -> str:
        return f"{self.pred}({', '.join(map(str, self.args))})" if self.args else self.pred


def variables(x: Term | Atom) -> set[Var]:
    if isinstance(x, Var):
        return {x}
    if isinstance(x, Const):
        return set()
    return set().union(*(variables(a) for a in x.args))


def is_ground(x: Term | Atom) -> bool:
    return not variables(x)


@dataclass(frozen=True, slots=True)
class Rule:
    """Definite (Horn) clause ``body_1 & ... & body_n -> head``. No negation anywhere."""

    name: str
    body: tuple[Atom, ...]
    head: Atom

    def __post_init__(self) -> None:
        body_vars = set().union(*(variables(a) for a in self.body)) if self.body else set()
        loose = variables(self.head) - body_vars
        if loose:  # range restriction: otherwise forward chaining would derive non-ground facts
            names = sorted(v.name for v in loose)
            raise ValueError(f"rule {self.name!r}: head variables {names} do not occur in the body")

    def __str__(self) -> str:
        return f"{' & '.join(map(str, self.body))} -> {self.head}"


def atom(pred: str, *names: str) -> Atom:
    """Ground atom over constants: ``atom("Person", "p1", "c3_4")``."""
    return Atom(pred, tuple(Const(n) for n in names))


# --- parser -----------------------------------------------------------------------------------


class ParseError(ValueError):
    pass


_TOKEN = re.compile(r"\s*(->|[A-Za-z0-9_]+|[(),&])")
_IDENT = re.compile(r"[A-Za-z0-9_]+")


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text.strip()
        self.tokens: list[str] = []
        pos = 0
        while pos < len(self.text):
            m = _TOKEN.match(self.text, pos)
            if m is None:
                raise ParseError(f"unexpected character {self.text[pos]!r} in {self.text!r}")
            self.tokens.append(m.group(1))
            pos = m.end()
        self.i = 0

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, expected: str | None = None) -> str:
        tok = self.peek()
        if tok is None or (expected is not None and tok != expected):
            want = repr(expected) if expected else "an identifier"
            raise ParseError(f"expected {want} but found {tok!r} in {self.text!r}")
        self.i += 1
        return tok

    def ident(self) -> str:
        tok = self.take()
        if not _IDENT.fullmatch(tok):
            raise ParseError(f"expected an identifier but found {tok!r} in {self.text!r}")
        return tok

    def args(self) -> tuple[Term, ...]:
        self.take("(")
        out = [self.term()]
        while self.peek() == ",":
            self.take(",")
            out.append(self.term())
        self.take(")")
        return tuple(out)

    def term(self) -> Term:
        name = self.ident()
        if self.peek() == "(":
            return Fn(name, self.args())
        return Var(name) if name[0].isupper() else Const(name)

    def atom(self) -> Atom:
        name = self.ident()
        return Atom(name, self.args() if self.peek() == "(" else ())

    def end(self) -> None:
        if self.peek() is not None:
            raise ParseError(f"unexpected {self.peek()!r} after the end of {self.text!r}")


def parse_term(text: str) -> Term:
    p = _Parser(text)
    t = p.term()
    p.end()
    return t


def parse_atom(text: str) -> Atom:
    p = _Parser(text)
    a = p.atom()
    p.end()
    return a


def parse_rule(text: str, name: str = "") -> Rule:
    p = _Parser(text)
    body = [p.atom()]
    while p.peek() == "&":
        p.take("&")
        body.append(p.atom())
    p.take("->")
    head = p.atom()
    p.end()
    return Rule(name or text.strip(), tuple(body), head)


def parse_rules(text: str) -> tuple[Rule, ...]:
    """One ``name: body -> head`` per non-blank line; ``#`` starts a comment."""
    rules = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, _, rule = line.partition(":")
            rules.append(parse_rule(rule, name.strip()))
    return tuple(rules)
