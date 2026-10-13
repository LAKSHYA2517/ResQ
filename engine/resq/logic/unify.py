"""Substitutions and unification (most general unifier, with the occurs check)."""

from .terms import Atom, Const, Fn, Term, Var

type Subst = dict[Var, Term]


def substitute(t: Term, s: Subst) -> Term:
    """Apply ``s`` to ``t`` once (simultaneous replacement of variables).

    Substitutions built by ``unify`` are idempotent, so one pass fully resolves them.
    """
    if isinstance(t, Var):
        return s.get(t, t)
    if isinstance(t, Fn):
        return Fn(t.name, tuple(substitute(a, s) for a in t.args))
    return t


def substitute_atom(a: Atom, s: Subst) -> Atom:
    return Atom(a.pred, tuple(substitute(t, s) for t in a.args)) if s else a


def compose(s1: Subst, s2: Subst) -> Subst:
    """The substitution "apply s1, then s2": ``substitute(t, compose(s1, s2))`` equals
    ``substitute(substitute(t, s1), s2)``."""
    out = {v: substitute(t, s2) for v, t in s1.items()}
    for v, t in s2.items():
        out.setdefault(v, t)
    return out


def occurs(v: Var, t: Term) -> bool:
    if isinstance(t, Fn):
        return any(occurs(v, a) for a in t.args)
    return t == v


def unify(x: Term, y: Term, s: Subst | None = None) -> Subst | None:
    """Most general unifier of ``x`` and ``y`` extending ``s``; ``None`` if they do not unify.

    The input substitution is never mutated. The occurs check rejects ``X = f(X)``, which
    would otherwise build an infinite term.
    """
    s = {} if s is None else s
    x, y = substitute(x, s), substitute(y, s)
    if x == y:
        return s
    if isinstance(x, Var):
        return None if occurs(x, y) else compose(s, {x: y})
    if isinstance(y, Var):
        return None if occurs(y, x) else compose(s, {y: x})
    if isinstance(x, Const) or isinstance(y, Const):
        return None  # distinct constants, or constant vs function term
    if x.name != y.name or len(x.args) != len(y.args):
        return None
    for a, b in zip(x.args, y.args, strict=True):
        nxt = unify(a, b, s)
        if nxt is None:
            return None
        s = nxt
    return s


def unify_atoms(a: Atom, b: Atom, s: Subst | None = None) -> Subst | None:
    if a.pred != b.pred or len(a.args) != len(b.args):
        return None
    s = {} if s is None else s
    for x, y in zip(a.args, b.args, strict=True):
        nxt = unify(x, y, s)
        if nxt is None:
            return None
        s = nxt
    return s
