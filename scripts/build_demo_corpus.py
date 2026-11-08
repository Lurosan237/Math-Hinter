"""Build site/data/corpus.json from a clone of github.com/exo7math/cours-exo7 (CC BY-NC-SA 3.0 FR)."""

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

from mathhinter.demo.exo7 import read_course

NOTICE = ("Extraits du cours Exo7 « Analyse 1 » (A. Bodin, L. Blanc-Centi, N. Borne, B. Boutin, L. Desideri, "
          "P. Romon), https://exo7.emath.fr, diffusé sous la licence Creative Commons BY-NC-SA 3.0 FR, "
          "https://creativecommons.org/licenses/by-nc-sa/3.0/fr/. Texte converti automatiquement depuis les sources "
          "LaTeX, sans autre modification.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="a clone of exo7math/cours-exo7")
    args = parser.parse_args()
    source = Path(args.source)
    commit = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    units = read_course(source)
    data = {"notice": NOTICE, "source": "https://github.com/exo7math/cours-exo7", "commit": commit.strip(),
            "units": units}
    Path("site/data/corpus.json").write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(len(units), dict(Counter(u["kind"] for u in units)))


if __name__ == "__main__":
    main()
