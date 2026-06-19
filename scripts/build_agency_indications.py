#!/usr/bin/env python3
"""Combine MeDIC's per-agency indication lists into one record per drug-disease pair.

The merged ``indicationList.tsv`` MeDIC ships collapses FDA, EMA, and PMDA
indications into a single deduplicated list, discarding which regulator
approved each indication, the verbatim indication text, and (for EMA) the
source EPAR URL. We instead read the three per-agency deduplicated sheets so
that provenance survives onto each edge.

Output (``data/indications_by_agency.jsonl``): one JSON record per
(drug, disease) pair, with an ``agencies`` list naming every regulator that
approved it. A pair approved by two agencies is one record with two agency
entries -- so the transform can emit a single edge carrying multiple
supporting sources, rather than duplicate edges.

Record shape::

    {
      "drug_id": "CHEBI:7915", "drug_label": "...",
      "disease_id": "MONDO:...", "disease_label": "...",
      "agencies": [
        {"agency": "FDA", "infores": "infores:dailymed",
         "source_url": "", "indication_text": "..."},
        ...
      ]
    }
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import openpyxl

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT = DATA_DIR / "indications_by_agency.jsonl"

# agency -> (deduplicated indication sheet, primary regulatory infores)
AGENCIES = {
    "FDA": ("fda_indications_deduplicated.xlsx", "infores:dailymed"),
    "EMA": ("ema_indications_deduplicated.xlsx", "infores:ema"),
    "PMDA": ("pmda_indications_deduplicated.xlsx", "infores:pmda"),
}

DRUG_ID_COL = "final normalized drug id"
DISEASE_ID_COL = "final normalized disease id"
DRUG_LABEL_COL = "final normalized drug label"
DISEASE_LABEL_COL = "final normalized disease label"
DRUG_NAME_COL = "drug name"
TEXT_COL = "indications text"

# EMA-only: the raw drug catalogue carries the EPAR landing-page URL.
EMA_DRUGS = "ema-drugs.xlsx"


def _clean(value: object) -> str:
    """Flatten a cell to a single whitespace-normalized line."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _ingredient_key(value: object) -> frozenset[str]:
    """Normalize a free-text active-ingredient string to a comparable token set."""
    if not value:
        return frozenset()
    parts = re.split(r"[;,/]| and ", str(value))
    return frozenset(p.strip().upper() for p in parts if p.strip())


def _rows(path: Path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    header = [str(c) for c in next(it)]
    return header, it


def _build_ema_url_map() -> dict[frozenset[str], str]:
    """Map normalized active-ingredient set -> EPAR URL from the EMA drug catalogue."""
    path = DATA_DIR / EMA_DRUGS
    if not path.exists():
        return {}
    header, it = _rows(path)
    ai = header.index("Active substance")
    ui = header.index("URL")
    ii = header.index("ingredients_list") if "ingredients_list" in header else None
    mapping: dict[frozenset[str], str] = {}
    for row in it:
        url = row[ui]
        if not url:
            continue
        key = _ingredient_key(row[ai])
        if ii is not None and row[ii]:
            try:
                key = frozenset(str(x).upper() for x in ast.literal_eval(row[ii]))
            except (ValueError, SyntaxError):
                pass
        if key:
            mapping[key] = str(url)
    return mapping


def build() -> tuple[int, int]:
    ema_urls = _build_ema_url_map()
    # (drug_id, disease_id) -> record
    pairs: dict[tuple[str, str], dict] = {}

    for agency, (filename, infores) in AGENCIES.items():
        path = DATA_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Expected {path}; run `just download` first.")
        header, it = _rows(path)
        di = header.index(DRUG_ID_COL)
        xi = header.index(DISEASE_ID_COL)
        dl = header.index(DRUG_LABEL_COL)
        xl = header.index(DISEASE_LABEL_COL)
        ti = header.index(TEXT_COL)
        ni = header.index(DRUG_NAME_COL)
        for row in it:
            drug_id, disease_id = row[di], row[xi]
            # Skip rows where ID normalization failed -- no CURIE, no edge.
            if not drug_id or not disease_id or ":" not in str(drug_id) or ":" not in str(disease_id):
                continue
            drug_id, disease_id = _clean(drug_id), _clean(disease_id)
            key = (drug_id, disease_id)
            record = pairs.get(key)
            if record is None:
                record = pairs[key] = {
                    "drug_id": drug_id,
                    "drug_label": _clean(row[dl]),
                    "disease_id": disease_id,
                    "disease_label": _clean(row[xl]),
                    "agencies": [],
                    "_seen": set(),
                }
            # One entry per agency per pair (sheets are already deduplicated, but guard anyway).
            if agency in record["_seen"]:
                continue
            record["_seen"].add(agency)
            source_url = ema_urls.get(_ingredient_key(row[ni]), "") if agency == "EMA" else ""
            record["agencies"].append(
                {
                    "agency": agency,
                    "infores": infores,
                    "source_url": source_url,
                    "indication_text": _clean(row[ti]),
                }
            )

    with open(OUTPUT, "w") as out:
        for record in pairs.values():
            record.pop("_seen", None)
            out.write(json.dumps(record) + "\n")

    multi = sum(1 for r in pairs.values() if len(r["agencies"]) > 1)
    return len(pairs), multi


if __name__ == "__main__":
    total, multi = build()
    print(f"Wrote {total} drug-disease pairs ({multi} approved by >1 agency) -> {OUTPUT}")
