"""Assemble the backfilled manuscript: inject generated tables, stage figures."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path("D:/Local_Projects/airslot/backfill_20261014")
PAPER = ROOT / "paper"
TAB = ROOT / "tables"
FIG = ROOT / "figures"

MARKERS = {
    "%TABLE_5_1%": "table_5_1.tex",
    "%TABLE_5_2%": "table_5_2.tex",
    "%SUP_SUPPORT%": "table_sup_support.tex",
    "%SUP_E1%": "table_sup_e1.tex",
    "%SUP_E1_Q%": "table_sup_e1_q.tex",
    "%SUP_E2_SUPPORT%": "table_sup_e2_support.tex",
    "%SUP_E3%": "table_sup_e3.tex",
    "%SUP_LADDER%": "table_sup_ladder.tex",
}


def main() -> int:
    tables = {name: (TAB / name).read_text(encoding="utf-8").rstrip("\n") for name in MARKERS.values()}
    for path in (PAPER / "sections" / "05_experiment.tex", PAPER / "SUPPLEMENT.tex"):
        text = path.read_text(encoding="utf-8")
        for marker, name in MARKERS.items():
            if marker in text:
                text = text.replace(marker, tables[name])
                print(f"{path.name}: injected {name}")
        path.write_text(text, encoding="utf-8")
    for source in sorted(FIG.glob("*.pdf")):
        shutil.copy2(source, PAPER / "figures" / source.name)
        print("staged figure", source.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
