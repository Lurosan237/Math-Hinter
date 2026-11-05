"""Decide whether an equality holds, and refuse to overclaim.

- "vérifié": both sides are the same expression for every value of the letters, read as the parser describes. It can
  be wrong when a lower-case letter is not a number, so the agent has to treat it as evidence.
- "réfuté": no letters are left and the two sides differ. Notation can fake this: (5/3) may be a Legendre symbol, so
  it means "read this again", not "this is wrong".
- "non vérifiable": the expression can't be parsed, or the two sides differ as expressions. A line in a proof such as
  x = 3 may be true because of what came before, and this check can't see that, so it doesn't call the line wrong.
"""

from __future__ import annotations

import random
import signal
from dataclasses import dataclass
from fractions import Fraction

import sympy as sp
from sympy.core.function import AppliedUndef

from .parser import INTEGER_LIKE, Unparseable, parse

VERIFIED = "vérifié"
REFUTED = "réfuté"
UNVERIFIABLE = "non vérifiable"
TIME_LIMIT_SECONDS = 3.0
TRIALS = 8
TOLERANCE = 1e-9


@dataclass(frozen=True)
class Verdict:
    status: str
    reason: str


class _TimedOut(Exception):
    pass


def _alarm(_signum, _frame):
    raise _TimedOut


def _sample_value(symbol: sp.Symbol, rng: random.Random) -> sp.Expr:
    base = symbol.name.split("_")[0]
    if base in INTEGER_LIKE:
        return sp.Integer(rng.randint(2, 7))
    fraction = Fraction(rng.randint(3, 27), rng.randint(7, 13))
    return sp.Rational(fraction.numerator, fraction.denominator)


def _numerically_equal(left: sp.Expr, right: sp.Expr, seed: int) -> bool | None:
    """True if the sides agree at every usable point, False if not, None if no point could be used."""
    rng = random.Random(seed)
    symbols = sorted(left.free_symbols | right.free_symbols, key=str)
    used = 0
    for _ in range(TRIALS):
        point = {s: _sample_value(s, rng) for s in symbols}
        a, b = sp.N(left.subs(point), 30), sp.N(right.subs(point), 30)
        if not (a.is_number and b.is_number) or a.has(sp.zoo, sp.nan, sp.oo) or b.has(sp.zoo, sp.nan, sp.oo):
            continue
        used += 1
        if abs(a - b) > TOLERANCE * max(1, abs(a), abs(b)):
            return False
    return True if used else None


def _is_opaque(expression: sp.Expr) -> bool:
    """Unknown functions and matrices can't be given sample values."""
    return bool(expression.atoms(AppliedUndef)) or not expression.is_commutative or any(
        not s.is_commutative for s in expression.free_symbols)


def _decide(left_latex: str, right_latex: str, seed: int) -> Verdict:
    try:
        left, right = parse(left_latex), parse(right_latex)
    except Unparseable as error:
        return Verdict(UNVERIFIABLE, f"unparseable: {error}")
    if _is_opaque(left) or _is_opaque(right):
        if sp.expand(left - right) == 0 or sp.simplify(left - right) == 0:
            return Verdict(VERIFIED, "identity")
        return Verdict(UNVERIFIABLE, "not an identity: may depend on earlier lines")
    agreement = _numerically_equal(left, right, seed)
    if agreement is None:
        return Verdict(UNVERIFIABLE, "no valid values to test")
    if not (left.free_symbols | right.free_symbols):
        return Verdict(VERIFIED, "same number") if agreement else Verdict(REFUTED, "different numbers")
    if not agreement:
        return Verdict(UNVERIFIABLE, "not an identity: may depend on earlier lines")
    # Agreeing at sample points is evidence, not proof, so an exact simplification must confirm it.
    if sp.simplify(left - right) == 0:
        return Verdict(VERIFIED, "identity")
    return Verdict(UNVERIFIABLE, "agrees numerically but couldn't be proved")


def check_equality(left_latex: str, right_latex: str, seed: int = 0) -> Verdict:
    """The verdict for left = right. A slow simplification is cut off and reported as unverifiable."""
    if not hasattr(signal, "setitimer"):
        return _decide(left_latex, right_latex, seed)
    previous = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, TIME_LIMIT_SECONDS)
    try:
        return _decide(left_latex, right_latex, seed)
    except _TimedOut:
        return Verdict(UNVERIFIABLE, "timed out")
    except (TypeError, ValueError, ZeroDivisionError, OverflowError, RecursionError, AttributeError) as error:
        return Verdict(UNVERIFIABLE, f"failed: {type(error).__name__}")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
