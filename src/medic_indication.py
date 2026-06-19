import uuid
from typing import Any

import koza
from biolink_model.datamodel.pydanticmodel_v2 import (
    AgentTypeEnum,
    ChemicalEntity,
    ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation,
    Disease,
    KnowledgeLevelEnum,
    PhenotypicFeature,
    ResourceRoleEnum,
    RetrievalSource,
)
from koza import KozaTransform
from koza.model.graphs import KnowledgeGraph

INFORES_MEDIC = "infores:medic"

# The MeDIC method paper, asserted as the publication backing every edge.
MEDIC_PUBLICATION = "PMID:41385096"


def _disease_node(disease_id: str, label: str):
    """Minimal object node. HP terms are phenotypic features; everything else a disease.

    These are *non-authoritative* placeholders -- see the README. We emit only an id,
    category, and name so the graph is self-contained; CHEBI/MONDO/HP remain the
    sources of truth for node metadata.
    """
    cls = PhenotypicFeature if disease_id.startswith("HP:") else Disease
    return cls(id=disease_id, name=label or None)


def _new_id() -> str:
    return f"uuid:{uuid.uuid4()}"


@koza.transform_record()
def transform_record(koza_transform: KozaTransform, record: dict[str, Any]) -> KnowledgeGraph:
    """Transform one MeDIC drug-disease pair into a Biolink drug-treats-disease edge.

    Each record carries every regulator (FDA/EMA/PMDA) that approved the indication.
    Provenance is modeled the way the sibling Multiomics DAKP ingest does it: MeDIC is
    the primary knowledge source, and each approving regulator is its own
    ``supporting_data_source`` retrieval entry -- so an indication approved by more
    than one agency is a single edge with multiple supporting sources (carrying each
    agency's EPAR URL in ``source_record_urls`` where MeDIC provides one).

    Subject/object nodes are emitted too, but only as minimal placeholders -- this
    ingest is not an authoritative source for node metadata (see README).
    """
    agencies = record["agencies"]

    sources = [
        RetrievalSource(
            id=_new_id(),
            resource_id=INFORES_MEDIC,
            resource_role=ResourceRoleEnum.primary_knowledge_source,
            upstream_resource_ids=[a["infores"] for a in agencies],
        )
    ]
    for a in agencies:
        url = a.get("source_url") or ""
        sources.append(
            RetrievalSource(
                id=_new_id(),
                resource_id=a["infores"],
                resource_role=ResourceRoleEnum.supporting_data_source,
                source_record_urls=[url] if url else None,
            )
        )

    # Preserve each regulator's verbatim indication text, attributed by agency.
    description = (
        "\n\n".join(f"[{a['agency']}] {a['indication_text']}" for a in agencies if a.get("indication_text")) or None
    )

    association = ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation(
        id=_new_id(),
        subject=record["drug_id"],
        predicate="biolink:treats",
        object=record["disease_id"],
        knowledge_level=KnowledgeLevelEnum.knowledge_assertion,
        agent_type=AgentTypeEnum.text_mining_agent,
        primary_knowledge_source=INFORES_MEDIC,
        sources=sources,
        description=description,
        publications=[MEDIC_PUBLICATION],
    )

    drug_node = ChemicalEntity(id=record["drug_id"], name=record.get("drug_label") or None)
    disease_node = _disease_node(record["disease_id"], record.get("disease_label") or "")

    return KnowledgeGraph(nodes=[drug_node, disease_node], edges=[association])
