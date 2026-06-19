#!/usr/bin/env python3
"""Export the JSONL transform output to KGX TSV alongside it.

The canonical output of this ingest is JSONL (it carries nested provenance --
`sources` is a list of Biolink RetrievalSource objects -- which TSV has no
native convention for). This produces a TSV *copy* for consumers that want it.

Koza's graph-ops verbs don't (yet) do a faithful single-file format conversion:
`split` fragments by a field and `join` only builds a DuckDB. So we do here what
a future koza `export`/`convert` verb would do internally -- load the JSONL into
DuckDB and COPY it out (see monarch-initiative/koza#230).

Serialization follows the KGX TSV spec
(https://github.com/biolink/kgx/blob/master/docs/kgx_format.md):

- Multivalued *scalar* columns (`category`, `publications`, `supporting_text`)
  are joined with a pipe `|` and no surrounding brackets -- the KGX convention
  ("Multi-valued fields use pipe (`|`) as delimiter"; the reference TSV sink
  joins lists with `|`).
- *Nested* columns (`sources`, a list of RetrievalSource structs) have NO KGX
  TSV standard: the spec's TSV example omits such columns, and KGX's own sink
  would emit Python `str(dict)` reprs. We serialize them as JSON instead --
  valid, parseable, and lossless. This is a deliberate non-standard extension;
  round-trip via the JSONL if strict KGX TSV is required.

Columns are classed by their DuckDB-inferred type: `T[]` (list of scalars) ->
pipe-join, `STRUCT(...)[]` / `STRUCT(...)` (nested) -> JSON, scalar -> as-is.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

LIST_DELIMITER = "|"


def _column_expr(name: str, dtype: str) -> str:
    """SQL projection for one column, per its DuckDB type (see module docstring)."""
    upper = dtype.upper()
    if "STRUCT" in upper:  # nested objects (e.g. sources) -> JSON; no KGX TSV standard
        return f"to_json({name}) AS {name}"
    if upper.endswith("[]"):  # multivalued scalars -> pipe-delimited, no brackets (KGX spec)
        return f"array_to_string({name}, '{LIST_DELIMITER}') AS {name}"
    return name


def _export(jsonl_path: Path, tsv_path: Path) -> int:
    con = duckdb.connect()
    try:
        con.execute(f"CREATE TABLE t AS SELECT * FROM read_json_auto('{jsonl_path}')")
        described = con.execute("DESCRIBE t").fetchall()  # (name, type, null, key, default, extra)
        select = ", ".join(_column_expr(name, dtype) for name, dtype, *_ in described)
        con.execute(f"COPY (SELECT {select} FROM t) TO '{tsv_path}' (HEADER, DELIMITER '\t')")
        return con.execute("SELECT count(*) FROM t").fetchone()[0]
    finally:
        con.close()


def main() -> None:
    for kind in ("nodes", "edges"):
        jsonl_path = OUTPUT_DIR / f"medic_indication_{kind}.jsonl"
        if not jsonl_path.exists():
            raise FileNotFoundError(f"{jsonl_path} not found; run `just transform-all` first.")
        tsv_path = OUTPUT_DIR / f"medic_indication_{kind}.tsv"
        count = _export(jsonl_path, tsv_path)
        print(f"Exported {count} {kind} -> {tsv_path}")


if __name__ == "__main__":
    main()
