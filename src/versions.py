"""Upstream source version fetcher for medic-ingest.

MeDIC's figshare URL itself contains only a file ID; the version (e.g.
1.3.0) is encoded in the local_name. We parse that out of download.yaml.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from kozahub_metadata_schema import (
    now_iso,
    urls_from_download_yaml,
)


INGEST_DIR = Path(__file__).resolve().parents[1]
DOWNLOAD_YAML = INGEST_DIR / "download.yaml"


def _medic_version_from_local_name() -> tuple[str, str]:
    try:
        raw = yaml.safe_load(DOWNLOAD_YAML.read_text())
        entries = raw["downloads"] if isinstance(raw, dict) else raw
        for entry in entries or []:
            local = entry.get("local_name") if isinstance(entry, dict) else None
            if not local:
                continue
            m = re.search(r"matrix-indication-list-(\d+\.\d+\.\d+)", local)
            if m:
                return m.group(1), "local_name_regex"
        return "unknown", "unavailable"
    except Exception:
        return "unknown", "unavailable"


def get_source_versions() -> list[dict[str, Any]]:
    ver, method = _medic_version_from_local_name()
    return [
        {
            "id": "infores:medic",
            "name": "MeDIC — Medicines, Diseases, Indications and Contraindications",
            "urls": urls_from_download_yaml(DOWNLOAD_YAML),
            "version": ver,
            "version_method": method,
            "retrieved_at": now_iso(),
        }
    ]
