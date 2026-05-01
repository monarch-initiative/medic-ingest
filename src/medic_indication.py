import logging
import uuid
from functools import lru_cache
from typing import Any

import requests

import koza
from koza import KozaTransform
from biolink_model.datamodel import pydanticmodel_v2 as biolink_model_module
from biolink_model.datamodel.pydanticmodel_v2 import (
    AgentTypeEnum,
    ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation,
    KnowledgeLevelEnum,
    NamedThing,
)

LOG = logging.getLogger(__name__)

EXCLUDED_NODE_PREFIXES = {"CHEBI", "MONDO"}

NAMERES_URL = "https://name-resolution-sri.renci.org/reverse_lookup"


@lru_cache(maxsize=10000)
def _nameres_lookup(curie: str) -> tuple[str, str] | None:
    """Look up canonical name and most specific biolink type for a CURIE via NameRes.

    Returns (preferred_name, biolink_type) or None on failure.
    """
    try:
        resp = requests.post(NAMERES_URL, json={"curies": [curie]}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if curie in data and data[curie]:
            entry = data[curie]
            preferred_name = entry.get("preferred_name")
            types = entry.get("types", [])
            biolink_type = types[0] if types else "NamedThing"
            return (preferred_name, biolink_type)
    except Exception:
        LOG.warning("NameRes lookup failed for %s", curie)
    return None


def _get_biolink_class(type_name: str) -> type:
    """Map a biolink type name (e.g. 'Drug') to its pydantic class, falling back to NamedThing."""
    return getattr(biolink_model_module, type_name, NamedThing)


def _make_node(entity_id: str, name: str) -> NamedThing | None:
    """Create a node for the entity, using NameRes to get canonical name and specific biolink class."""
    prefix = entity_id.split(":")[0]
    if prefix in EXCLUDED_NODE_PREFIXES:
        return None

    node_class = NamedThing
    node_name = name

    result = _nameres_lookup(entity_id)
    if result:
        preferred_name, biolink_type = result
        node_class = _get_biolink_class(biolink_type)
        if preferred_name:
            node_name = preferred_name

    return node_class(
        id=entity_id,
        name=node_name,
        provided_by=["infores:medic"],
    )


@koza.transform_record()
def transform_record(
    koza_transform: KozaTransform, row: dict[str, Any]
) -> list:
    """Transform a MeDIC indication row into a Biolink drug-treats-disease association and nodes."""
    if row["drug ID"] == "NameRes Failed":
        return []

    association = ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation(
        id=f"uuid:{uuid.uuid4()}",
        subject=row["drug ID"],
        predicate="biolink:treats",
        object=row["disease IDs"],
        knowledge_level=KnowledgeLevelEnum.knowledge_assertion,
        agent_type=AgentTypeEnum.automated_agent,
        aggregator_knowledge_source=["infores:medic"],
        primary_knowledge_source="infores:medic",
        publications=["PMID:41385096"],
    )

    entities: list = []

    drug_node = _make_node(row["drug ID"], row["drug ID Label"])
    if drug_node:
        entities.append(drug_node)

    disease_node = _make_node(row["disease IDs"], row["disease ID labels"])
    if disease_node:
        entities.append(disease_node)

    entities.append(association)
    return entities
