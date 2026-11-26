"""Claims a line makes, and how the computer checks them.

A model turns each line into typed claims (see formalise.py); these functions check them with SymPy, never with eval.
Every check answers vérifié, réfuté or non vérifiable, and only calls a claim wrong when the computation is exact or
the numbers disagree beyond doubt: a claim that may depend on context the check can't see stays non vérifiable.

Claim types, with their fields (expressions in LaTeX):
- equality: left, right                      left = right for every value of the letters, or as numbers
- derivative: function, variable, result     d/dvariable of function is result
- antiderivative: function, variable, result result is a primitive of function
- integral: function, variable, lower, upper, result
- limit: function, variable, point, result   point and result may be \\infty, +\\infty, -\\infty
- sum: term, index, start, end, result       sum of term for index from start to end
- solution: equations, values                each equation holds once values are substituted
- ode: equation, function, variable, solution  the solution satisfies the differential equation
- theorem: name                              a theorem is used; not computed, but its statement is looked up
- other                                      nothing to compute
"""

from __future__ import annotations

import random
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass

import sympy as sp

from ..check.equality import REFUTED, UNVERIFIABLE, VERIFIED, check_equality
from ..check.parser import Unparseable, parse

TIME_LIMIT_SECONDS = 4.0
TOLERANCE = 1e-8
CHECKED_TYPES = ("equality", "derivative", "antiderivative", "integral", "limit", "sum", "solution", "ode")


@dataclass(frozen=True)
class Check:
    status: str
    reason: str
    computed: str = ""  # what the computer found, for the judge and the hint (never shown as the answer)


class _TimedOut(Exception):
    pass


def _alarm(_signum, _frame):
    raise _TimedOut


def _expr(latex: object) -> sp.Expr:
    text = str(latex or "").strip().strip("$").strip()
    if not text:
        raise Unparseable("empty")
    infinity = text.replace(" ", "")
    if infinity in (r"\infty", r"+\infty", "oo", "+oo", "∞", "+∞"):
        return sp.oo
    if infinity in (r"-\infty", "-oo", "-∞"):
        return -sp.oo
    expression = parse(text)
    # A lone e in a result such as 2e - 1 is Euler's number; e^x is already read as exp.
    return expression.subs({s: sp.E for s in expression.free_symbols if s.name == "e"})


def _symbol(name: object, expressions: list[sp.Expr]) -> sp.Symbol:
    """The variable a claim names, matched to the symbol the parser produced."""
    wanted = str(name or "x").strip().strip("$").strip() or "x"
    for expression in expressions:
        for s in expression.free_symbols:
            if s.name == wanted:
                return s
    return sp.Symbol(wanted)


def _same(left: sp.Expr, right: sp.Expr, label: str) -> Check:
    """Exact comparison: identical, a proven difference, or unclear."""
    difference = sp.simplify(left - right)
    if difference == 0:
        return Check(VERIFIED, label)
    if not difference.free_symbols:
        value = sp.N(difference)
        if value.is_number and abs(value) > TOLERANCE:
            return Check(REFUTED, label, computed=sp.latex(left))
        return Check(UNVERIFIABLE, label + ": could not decide")
    # Different as expressions: wrong if they differ at sample points where both are defined.
    symbols = sorted(difference.free_symbols, key=str)
    rng = random.Random(0)
    disagreements = agreements = 0
    for _ in range(8):
        point = {s: sp.Rational(rng.randint(3, 29), rng.randint(7, 13)) for s in symbols}
        a, b = sp.N(left.subs(point), 30), sp.N(right.subs(point), 30)
        if not (a.is_real and b.is_real):
            continue
        if abs(a - b) > TOLERANCE * max(1, abs(a), abs(b)):
            disagreements += 1
        else:
            agreements += 1
    if disagreements and not agreements:
        return Check(REFUTED, label, computed=sp.latex(left))
    return Check(UNVERIFIABLE, label + ": could not decide")


def _equality(c: dict) -> Check:
    verdict = check_equality(str(c.get("left", "")).strip("$"), str(c.get("right", "")).strip("$"))
    return Check(verdict.status, "equality: " + verdict.reason)


def _derivative(c: dict) -> Check:
    f, result = _expr(c["function"]), _expr(c["result"])
    x = _symbol(c.get("variable"), [f, result])
    return _same(sp.diff(f, x), result, "derivative")


def _antiderivative(c: dict) -> Check:
    f, result = _expr(c["function"]), _expr(c["result"])
    x = _symbol(c.get("variable"), [f, result])
    check = _same(sp.diff(result, x), f, "antiderivative")
    return Check(check.status, check.reason)  # the computed derivative isn't the answer; don't pass it on


def _integral(c: dict) -> Check:
    f, result = _expr(c["function"]), _expr(c["result"])
    lower, upper = _expr(c["lower"]), _expr(c["upper"])
    x = _symbol(c.get("variable"), [f])
    if result.free_symbols or lower.free_symbols or upper.free_symbols:
        return _same(sp.integrate(f, (x, lower, upper)), result, "integral")
    value = sp.Integral(f, (x, lower, upper)).evalf(30)
    claimed = sp.N(result, 30)
    if not (value.is_number and claimed.is_number) or value.has(sp.nan):
        return Check(UNVERIFIABLE, "integral: could not compute")
    if abs(value - claimed) <= TOLERANCE * max(1, abs(value)):
        return Check(VERIFIED, "integral")
    return Check(REFUTED, "integral", computed=sp.latex(sp.nsimplify(value, [sp.E, sp.pi], tolerance=1e-10)))


def _limit(c: dict) -> Check:
    f, result = _expr(c["function"]), _expr(c["result"])
    x = _symbol(c.get("variable"), [f])
    point = str(c.get("point", "")).replace(" ", "")
    direction = "+-"
    if point.endswith("^+") or point.endswith("^{+}"):
        point, direction = point.split("^")[0], "+"
    elif point.endswith("^-") or point.endswith("^{-}"):
        point, direction = point.split("^")[0], "-"
    at = _expr(point)
    if at in (sp.oo, -sp.oo):
        direction = "-" if at == sp.oo else "+"
    computed = sp.limit(f, x, at, dir=direction)
    if computed.has(sp.Limit) or computed == sp.nan or isinstance(computed, sp.AccumBounds):
        return Check(UNVERIFIABLE, "limit: could not compute")
    if computed in (sp.oo, -sp.oo, sp.zoo) or result in (sp.oo, -sp.oo):
        if computed == result:
            return Check(VERIFIED, "limit")
        return Check(REFUTED, "limit", computed=sp.latex(computed))
    return _same(computed, result, "limit")


def _sum(c: dict) -> Check:
    term, result = _expr(c["term"]), _expr(c["result"])
    start, end = _expr(c["start"]), _expr(c["end"])
    k = _symbol(c.get("index") or "k", [term])
    if not end.free_symbols:
        return _same(sp.summation(term, (k, start, end)), result, "sum")
    # A closed form in n: check it for several values of n rather than trusting a symbolic summation.
    (n,) = sorted(end.free_symbols, key=str)[:1]
    for value in range(0, 7):
        if not start.free_symbols and sp.N(end.subs(n, value)) < sp.N(start):
            continue
        exact = sp.summation(term.subs(n, value), (k, start.subs(n, value), end.subs(n, value)))
        claimed = result.subs(n, value)
        if claimed.free_symbols:
            return Check(UNVERIFIABLE, "sum: the result has other letters")
        if sp.simplify(exact - claimed) != 0:
            return Check(REFUTED, "sum", computed=f"n={value}: {sp.latex(exact)}")
    return Check(VERIFIED, "sum (checked for n = 0 to 6)")


def _solution(c: dict) -> Check:
    values = c.get("values") or {}
    if not isinstance(values, dict) or not values:
        return Check(UNVERIFIABLE, "solution: no values")
    pairs = []
    for equation in c.get("equations") or []:
        text = str(equation).strip("$")
        if text.count("=") != 1:
            return Check(UNVERIFIABLE, "solution: an equation without one '='")
        left, right = text.split("=")
        pairs.append((_expr(left), _expr(right)))
    if not pairs:
        return Check(UNVERIFIABLE, "solution: no equations")
    symbols = {s.name: s for left, right in pairs for s in (left.free_symbols | right.free_symbols)}
    point = {symbols[name]: _expr(value) for name, value in values.items() if name in symbols}
    for left, right in pairs:
        a, b = left.subs(point), right.subs(point)
        if a.free_symbols or b.free_symbols:
            return Check(UNVERIFIABLE, "solution: letters left after substitution")
        if sp.simplify(a - b) != 0:
            return Check(REFUTED, "solution", computed=f"{sp.latex(a)} \\neq {sp.latex(b)}")
    return Check(VERIFIED, "solution")


def _ode(c: dict) -> Check:
    equation = str(c.get("equation", "")).strip("$")
    if equation.count("=") != 1:
        return Check(UNVERIFIABLE, "ode: an equation without one '='")
    name = str(c.get("function") or "y").strip()
    solution = _expr(c["solution"])
    x = _symbol(c.get("variable"), [solution])
    # Replace y'', y' and y by the solution's derivatives before parsing, so the parser sees an ordinary expression.
    derivatives = {f"{name}''": sp.diff(solution, x, 2), f"{name}'": sp.diff(solution, x), name: solution}
    left, right = equation.split("=")
    sides = []
    for side in (left, right):
        text = side
        for key in sorted(derivatives, key=len, reverse=True):
            text = text.replace(f"{key}({x.name})", f"({sp.latex(derivatives[key])})")
            text = text.replace(key, f"({sp.latex(derivatives[key])})")
        sides.append(_expr(text))
    return _same(sides[0], sides[1], "ode")


CHECKS = {"equality": _equality, "derivative": _derivative, "antiderivative": _antiderivative,
          "integral": _integral, "limit": _limit, "sum": _sum, "solution": _solution, "ode": _ode}


_POOL = ThreadPoolExecutor(max_workers=4)


def check_claim(claim: dict) -> Check:
    """The computer's verdict on one claim. Anything it can't read or compute is non vérifiable."""
    kind = claim.get("type")
    if kind not in CHECKS:
        return Check(UNVERIFIABLE, f"{kind}: not computed")
    if threading.current_thread() is not threading.main_thread():
        # Signals only work on the main thread, so elsewhere the check runs in a worker and is abandoned if slow.
        future = _POOL.submit(_check_untimed, claim)
        try:
            return future.result(timeout=TIME_LIMIT_SECONDS)
        except FutureTimeout:
            return Check(UNVERIFIABLE, f"{kind}: timed out")
    use_timer = hasattr(signal, "setitimer")
    if use_timer:
        previous = signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, TIME_LIMIT_SECONDS)
    try:
        return CHECKS[kind](claim)
    except _TimedOut:
        return Check(UNVERIFIABLE, f"{kind}: timed out")
    except (Unparseable, KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError, RecursionError,
            AttributeError, NotImplementedError, sp.SympifyError, sp.PolynomialError) as error:
        return Check(UNVERIFIABLE, f"{kind}: {type(error).__name__}")
    finally:
        if use_timer:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)


def _check_untimed(claim: dict) -> Check:
    kind = claim.get("type")
    try:
        return CHECKS[kind](claim)
    except (Unparseable, KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError, RecursionError,
            AttributeError, NotImplementedError, sp.SympifyError, sp.PolynomialError) as error:
        return Check(UNVERIFIABLE, f"{kind}: {type(error).__name__}")
