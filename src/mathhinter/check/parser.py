"""Parse a small, safe subset of LaTeX directly into SymPy objects.

No eval and no SymPy string parsing, so nothing from a model or a book can run as code.

Letters are read cautiously, but this can't see context, so a "verified" holds only for the reading below:
- f(x) is an unknown function. If it was really a product, a true identity may go unverified: the safe way round.
- A capital may be a matrix, so capitals don't commute: AB = BA is not an identity here.
- A lower-case letter is an ordinary number. If u and v are really endomorphisms, uv = vu is still "verified", wrongly.
"""

from __future__ import annotations

import re

import sympy as sp

_TOKEN = re.compile(r"\s+|\\[A-Za-z]+|\d+(?:\.\d+)?|[A-Za-z]|[-+*/^_(){}!,']|.", re.S)
_FUNCTIONS = {"sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "ln": sp.log, "exp": sp.exp, "sh": sp.sinh, "ch": sp.cosh}
# Letters that name numbers, so x(x+2) is a product. Others, like f(x) or y(0), are functions.
_VARIABLES = set("abcklmnpqrstxz")
_NAMED_WORDS = sorted(_FUNCTIONS, key=len, reverse=True)
_GREEK = {"alpha", "beta", "gamma", "delta", "varepsilon", "epsilon", "zeta", "eta", "theta", "kappa", "lambda", "mu",
          "nu", "xi", "rho", "sigma", "tau", "varphi", "phi", "chi", "psi", "omega"}
_IGNORED = {r"\left", r"\right", r"\,", r"\;", r"\!", r"\displaystyle"}
INTEGER_LIKE = {"i", "j", "k", "l", "m", "n", "p", "q", "r", "s", "N"}
MAX_TOKENS = 400
# Words stuck to a formula would otherwise read as products: "0 et x" would look like 0.
_FRENCH_WORD = re.compile(r"et|ou|si|donc|car|avec|alors|pour|dans|que|où|soit|on|est")
_FUNCTION_NAMES = re.compile(r"sinh?|cosh?|tanh?|ln|exp|sh|ch")


class Unparseable(ValueError):
    """The expression is outside what this parser will claim to understand."""


def _tokenise(latex: str) -> list[str]:
    if _FRENCH_WORD.search(_FUNCTION_NAMES.sub(" ", re.sub(r"\\[A-Za-z]+", " ", latex))):
        raise Unparseable("contains a French word")
    tokens = [t for t in _TOKEN.findall(latex) if not t.isspace() and t not in _IGNORED]
    if len(tokens) > MAX_TOKENS:
        raise Unparseable("too long")
    return tokens


class _Parser:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.at = 0

    def peek(self) -> str | None:
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def take(self, expected: str | None = None) -> str:
        token = self.peek()
        if token is None or (expected is not None and token != expected):
            raise Unparseable(f"expected {expected!r}")
        self.at += 1
        return token

    def expression(self) -> sp.Expr:
        value = self.term()
        while self.peek() in ("+", "-"):
            value = value + self.term() if self.take() == "+" else value - self.term()
        return value

    def term(self) -> sp.Expr:
        value = self.unary()
        while True:
            token = self.peek()
            if token == "*":
                raise Unparseable("a star is usually an operation of its own, such as a convolution")
            if token in (r"\cdot", r"\times"):
                self.take()
                value = value * self.unary()
            elif token == "/":
                self.take()
                value = value / self.unary()
            elif token is not None and self.starts_atom(token):
                value = value * self.power()
            else:
                return value

    @staticmethod
    def starts_atom(token: str) -> bool:
        return token == "(" or bool(re.fullmatch(r"\d.*|[A-Za-z]", token)) or token in (r"\frac", r"\sqrt", r"\pi") or (
            token.startswith("\\") and (token[1:] in _GREEK or token[1:] in _FUNCTIONS))

    def unary(self) -> sp.Expr:
        token = self.peek()
        if token == "-":
            self.take()
            return -self.unary()
        if token == "+":
            self.take()
            return self.unary()
        return self.power()

    def power(self) -> sp.Expr:
        value = self.atom()
        while self.peek() in ("^", "!"):
            if self.take() == "!":
                value = sp.factorial(value)
            else:
                value = value ** self.script()
                if self.peek() == "(" and value.free_symbols and isinstance(value, sp.Pow) and value.base.is_Symbol:
                    raise Unparseable("f^{(n)}(x) is a derivative or an iterate, not a product")
        return value

    def script(self) -> sp.Expr:
        if self.peek() == "{":
            self.take()
            value = self.expression()
            self.take("}")
            return value
        return self.atom()

    def group(self) -> sp.Expr:
        self.take("{")
        value = self.expression()
        self.take("}")
        return value

    def subscript(self) -> str:
        """The raw text of a subscript: it names a variable, so x_{1} and x_{2} stay different."""
        self.take("_")
        if self.peek() != "{":
            return self.take()
        self.take("{")
        depth, parts = 1, []
        while True:
            token = self.take()
            depth += (token == "{") - (token == "}")
            if depth == 0:
                return "".join(parts)
            parts.append(token)

    def word_function(self) -> str | None:
        for name in _NAMED_WORDS:
            if self.tokens[self.at : self.at + len(name)] == list(name):
                return name
        return None

    def function(self, name: str) -> sp.Expr:
        exponent = None
        if self.peek() == "^":
            self.take()
            exponent = self.script()
        if self.peek() == "(":
            argument = self.atom()
        else:
            argument = self.power()
        value = _FUNCTIONS[name](argument)
        return value**exponent if exponent is not None else value

    def atom(self) -> sp.Expr:
        word = self.word_function()
        if word:
            self.at += len(word)
            return self.function(word)
        token = self.take()
        if re.fullmatch(r"\d+", token):
            return sp.Integer(token)
        if re.fullmatch(r"\d+\.\d+", token):
            return sp.Rational(token)
        if token == "(":
            value = self.expression()
            self.take(")")
            return value
        if token == r"\frac":
            top = self.group()
            return top / self.group()
        if token == r"\sqrt":
            return sp.sqrt(self.group())
        if token == r"\pi":
            return sp.pi
        if token.startswith("\\") and token[1:] in _FUNCTIONS:
            self.at -= 0
            return self.function(token[1:])
        if token.startswith("\\") and token[1:] in _GREEK:
            return self.symbol(token[1:])
        if re.fullmatch(r"[A-Za-z]", token):
            return self.symbol(token)
        raise Unparseable(f"not understood: {token}")

    def symbol(self, name: str) -> sp.Expr:
        full = name
        while self.peek() == "'":
            self.take()
            full += "'"
        if self.peek() == "_":
            full = f"{full}_{self.subscript()}"
        while self.peek() == "'":
            self.take()
            full += "'"
        if name == "e" and full == "e" and self.peek() == "^":
            return sp.E
        if self.peek() == "(" and full not in _VARIABLES:
            return self.applied(full)
        return sp.Symbol(full, commutative=not name[0].isupper())

    def applied(self, name: str) -> sp.Expr:
        self.take("(")
        arguments = [self.expression()]
        while self.peek() == ",":
            self.take()
            arguments.append(self.expression())
        self.take(")")
        return sp.Function(name)(*arguments)


def parse(latex: str) -> sp.Expr:
    parser = _Parser(_tokenise(latex))
    value = parser.expression()
    if parser.peek() is not None:
        raise Unparseable(f"left over: {parser.peek()}")
    return value
