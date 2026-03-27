# MeDIC

[MeDIC](https://doi.org/10.6084/m9.figshare.30491081) (Medicines, Diseases, Indications, and Contraindications) is a curated resource linking drugs to their therapeutic indications. It maps drugs identified by CHEBI or DrugBank IDs to diseases identified by Disease Ontology (DOID) terms.

Data is downloaded from Figshare: `https://ndownloader.figshare.com/files/59187533`

The archive contains `indicationList.tsv` (from `matrix-indication-list-1.3.0/merge_lists/`), a tab-separated file listing drug-disease indication pairs.

## Drug to Disease Indications

Each row in the indication list represents a single drug-disease therapeutic indication. All rows are ingested directly — no filtering is applied, as every entry represents a validated indication from MeDIC.

### Source File Fields

* drug|disease (composite key, not used)
* drug ID (CHEBI or DRUGBANK identifier)
* drug ID Label (drug name)
* disease IDs (DOID identifier)
* disease ID labels (disease name)
* active ingredients in therapy
* list of diseases

### Biolink Captured

#### biolink:ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation

* id (UUID)
* subject (`drug ID` — CHEBI or DRUGBANK identifier, e.g. `CHEBI:7915`, `DRUGBANK:DB00028`)
* predicate (`biolink:treats`)
* object (`disease IDs` — DOID identifier, e.g. `DOID:10017`)
* knowledge_level (`knowledge_assertion`)
* agent_type (`automated_agent`)
* primary_knowledge_source (`infores:medic`)
* aggregator_knowledge_source (`["infores:medic"]`)
* publications (`["PMID:41385096"]`)

### Design Decisions

* **No filtering:** All source rows are transformed 1:1 into edges. The MeDIC indication list is already curated, so no additional exclusion criteria are applied.
* **No node generation:** Drug and disease nodes are expected to exist in external ontologies (CHEBI, DrugBank, Disease Ontology) and are not created by this ingest.
* **Single predicate:** All indications use `biolink:treats` — MeDIC does not distinguish between indication subtypes.
* **Single publication:** All edges cite `PMID:41385096`, the MeDIC resource publication, rather than individual evidence references.

## Citation

Sundar S, et al. MeDIC: Medicines, Diseases, Indications, and Contraindications. 2025. PMID: 41385096.

## License

BSD-3-Clause
