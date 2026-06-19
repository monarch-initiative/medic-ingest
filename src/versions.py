"""Upstream source version fetcher for medic-ingest.

MeDIC's figshare URL itself contains only a file ID; the version (e.g.
1.3.0) is encoded in the local_name. We parse that out of download.yaml.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from kozahub_metadata_schema import (
    now_iso,
    urls_from_download_yaml,
    version_from_github_release,
)

MONDO_SSSOM_URL = "http://purl.obolibrary.org/obo/mondo/mappings/mondo.sssom.tsv"
NODENORM_STATUS_URL = "https://nodenormalization-sri.renci.org/status"
NODENORM_OPENAPI_URL = "https://nodenormalization-sri.renci.org/openapi.json"


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


def _mondo_sssom_version() -> tuple[str, str]:
    """MONDO has no version in the SSSOM header; track the MONDO release tag instead."""
    try:
        return version_from_github_release("monarch-initiative/mondo")
    except Exception:
        return "unknown", "unavailable"


def _nodenorm_versions() -> tuple[str, str | None, str | None]:
    """NodeNorm versions: Babel data release + biolink model (/status) and service code (/openapi).

    The data (Babel) release is the reproducibility anchor; the service code version and biolink
    model tag are recorded for a complete receipt. They are versioned independently.
    """
    babel, biolink, service = "unknown", None, None
    try:
        with urllib.request.urlopen(NODENORM_STATUS_URL, timeout=10) as resp:
            status = json.load(resp)
        babel = status.get("babel_version") or "unknown"
        biolink = (status.get("biolink_model") or {}).get("tag")
    except Exception:
        pass
    try:
        with urllib.request.urlopen(NODENORM_OPENAPI_URL, timeout=10) as resp:
            service = (json.load(resp).get("info") or {}).get("version")
    except Exception:
        pass
    return babel, biolink, service


def get_source_versions() -> list[dict[str, Any]]:
    ver, method = _medic_version_from_local_name()
    mondo_ver, mondo_method = _mondo_sssom_version()
    babel_ver, biolink_tag, service_ver = _nodenorm_versions()
    return [
        {
            "id": "infores:medic",
            "name": "MeDIC — Medicines, Diseases, Indications and Contraindications",
            "urls": urls_from_download_yaml(DOWNLOAD_YAML, contains=["figshare"]),
            "version": ver,
            "version_method": method,
            "retrieved_at": now_iso(),
        },
        {
            "id": "infores:mondo",
            "name": "MONDO disease ontology — SSSOM exact-match mappings (disease id normalization)",
            "urls": [MONDO_SSSOM_URL],
            "version": mondo_ver,
            "version_method": mondo_method,
            "retrieved_at": now_iso(),
        },
        {
            "id": "infores:sri-node-normalizer",
            "name": "SRI Node Normalizer (drug id normalization)",
            "urls": [NODENORM_STATUS_URL],
            # The Babel data release is the reproducibility anchor; service code and biolink
            # model versions are recorded separately (they version independently).
            "version": babel_ver,
            "version_method": "status_endpoint" if babel_ver != "unknown" else "unavailable",
            "service_version": service_ver,
            "biolink_model_version": biolink_tag,
            "retrieved_at": now_iso(),
        },
    ]
