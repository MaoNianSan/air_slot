"""Table bundles for the output contract (three-line booktabs style).

OUTPUT_CONTRACT_20260823 section 4/5: main tables use the fixed column
layout Subexperiment | Condition | Metric | Estimate | 95% CI | N episodes,
caption above the table, top/mid/bottom rules only.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd


def _tex_escape(value: Any) -> str:
    rendered = str(value)
    replacements = (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("_", r"\_"),
        ("#", r"\#"),
        ("$", r"\$"),
        ("{", r"\{"),
        ("}", r"\}"),
    )
    for old, new in replacements:
        rendered = rendered.replace(old, new)
    return rendered


def generate_table_bundle(
    rows: Iterable[Mapping[str, Any]], table_id: str, output: Path,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Compatibility table bundle: CSV plus plain LaTeX tabular."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(list(rows))
    frame.to_csv(output / f"{table_id}.csv", index=False)
    (output / f"{table_id}.tex").write_text(
        frame.to_latex(index=False), encoding="utf-8",
    )
    meta = {
        "table_id": table_id,
        **dict(metadata),
        "source_data": f"{table_id}.csv",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / f"{table_id}.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8",
    )
    return meta


def generate_three_line_table(
    rows: Iterable[Mapping[str, Any]], table_id: str, output: Path,
    metadata: Mapping[str, Any], *, caption: str | None = None,
) -> dict[str, Any]:
    """CSV plus booktabs three-line LaTeX table with caption above."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(list(rows))
    frame.to_csv(output / f"{table_id}.csv", index=False)
    columns = list(frame.columns)
    header = " & ".join(_tex_escape(name) for name in columns)
    body = "\n".join(
        " & ".join(_tex_escape(value) for value in row) + r" \\"
        for row in frame.itertuples(index=False)
    )
    caption_line = f"\\caption{{{_tex_escape(caption)}}}\n" if caption else ""
    tex = (
        "\\begin{table}[ht]\n"
        + caption_line
        + "\\centering\n"
        + "\\begin{tabular}{" + "l" * len(columns) + "}\n"
        + "\\toprule\n"
        + header + " \\\\\n"
        + "\\midrule\n"
        + body + "\n"
        + "\\bottomrule\n"
        + "\\end{tabular}\n"
        + "\\end{table}\n"
    )
    (output / f"{table_id}.tex").write_text(tex, encoding="utf-8")
    meta = {
        "table_id": table_id,
        **dict(metadata),
        "source_data": f"{table_id}.csv",
        "caption": caption,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / f"{table_id}.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8",
    )
    return meta


__all__ = ["generate_three_line_table", "generate_table_bundle"]
