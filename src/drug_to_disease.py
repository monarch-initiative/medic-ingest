import uuid
from typing import Any

import koza
from koza import KozaTransform
from biolink_model.datamodel.pydanticmodel_v2 import (
    AgentTypeEnum,
    ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation,
    KnowledgeLevelEnum,
)


@koza.transform_record()
def transform_record(
    koza_transform: KozaTransform, row: dict[str, Any]
) -> list[ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation]:
    """Transform a MeDIC indication row into a Biolink drug-treats-disease association."""
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

    return [association]
