# Data sources

The benchmarks download these databases at run time. None of them is stored in this repository,
its results or its Zenodo dataset, except the aggregates named below.

| Source | Licence | What this project keeps |
| --- | --- | --- |
| USEEIO 1.1, US EPA ([files.brightway.dev](https://files.brightway.dev/USEEIO-1.1.tar.gz)) | Public domain, a US government work | Timings; a fictional test fixture in its format |
| "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2025", FOEN ([files.brightway.dev](https://files.brightway.dev/bafu-2025-v2.tar.gz)) | FOEN terms: use in LCA studies with this citation; no distribution, alone or inside another database | Timings and aggregate statistics |
| ecoinvent 3.12 cut-off, ecoinvent Association | ecoinvent EULA (licensed copy) | Aggregate statistics only (`src/bwbench/profiles/`), with the credit the EULA asks for |
