# MeDIC

[MeDIC](https://doi.org/10.6084/m9.figshare.30491081) (Medicines, Diseases, Indications, and Contraindications) is a curated resource linking drugs to their therapeutic indications. It maps drugs identified by CHEBI or DrugBank IDs to diseases identified by Disease Ontology (DOID) terms.

Data is downloaded from Figshare: `https://ndownloader.figshare.com/files/59187533`

The archive contains `indicationList.tsv` (from `matrix-indication-list-1.3.0/merge_lists/`), a tab-separated file listing drug-disease indication pairs.

## Drug to Disease Indications

Each row in the indication list represents a single drug-disease therapeutic indication. Rows where the drug ID is `"NameRes Failed"` (19 rows in the source data) are filtered out, as they lack valid drug identifiers. All remaining rows are ingested directly.

### Source File Fields

* drug|disease (composite key, not used)
* drug ID (CHEBI or DRUGBANK identifier)
* drug ID Label (drug name)
* disease IDs (DOID identifier)
* disease ID labels (disease name)
* active ingredients in therapy
* list of diseases

### Biolink Captured

#### Nodes (NameRes-enriched)

* id (`drug ID` or `disease IDs`)
* category (specific biolink type from NameRes, e.g. `biolink:Drug`, `biolink:Disease`, falling back to `biolink:NamedThing`)
* name (canonical name from NameRes, falling back to source TSV name)
* provided_by (`["infores:medic"]`)

Nodes are emitted for both drug and disease entities, **excluding** any entity whose prefix is `CHEBI` or `MONDO` — those are expected to come from their authoritative ontology sources.

For non-excluded entities, the [NameRes reverse_lookup API](https://name-resolution-sri.renci.org/docs) is called to retrieve the canonical preferred name and the most specific biolink category (e.g. `Drug`, `Disease`). Results are cached per CURIE with `@lru_cache` to avoid redundant HTTP calls. If NameRes is unavailable or returns no result, the node falls back to `NamedThing` with the source-data name.

#### biolink:ChemicalOrDrugOrTreatmentToDiseaseOrPhenotypicFeatureAssociation (edges)

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

* **NameRes Failed filtering:** Rows with `"NameRes Failed"` as the drug ID are skipped entirely — they produce no nodes and no edges.
* **NameRes enrichment:** Non-excluded nodes are enriched via NameRes reverse_lookup to get canonical names and specific biolink categories. Results are cached per CURIE. On failure, nodes fall back to `NamedThing` with the source name.
* **Selective node generation:** Nodes are created for drug and disease entities unless their prefix is `CHEBI` or `MONDO`, since those have authoritative sources elsewhere.
* **Single predicate:** All indications use `biolink:treats` — MeDIC does not distinguish between indication subtypes.
* **Single publication:** All edges cite `PMID:41385096`, the MeDIC resource publication, rather than individual evidence references.

## Citation

Sundar S, et al. MeDIC: Medicines, Diseases, Indications, and Contraindications. 2025. PMID: 41385096.

## License

BSD-3-Clause
