# Station geography transfer

Source and validation checks pass; held evaluation has not been computed. This independent noncommercial study compares 54 geographic pooling configurations with a simple pooled baseline for recorded daily departures under grouped simulated station-history holdout and fixed future calendar periods.

The source has 1,052,451 published records; independent parser hashes match 4,209,804 selected-field scalars. Initial-only geometry yields 83 nominal station IDs: 49 donor IDs, 22 validation coordinate groups and 12 held groups. Nineteen fixtures and independent reconstruction of all 110,110 validation predictions, 26,754 donor histories, 8,206 weight rows and 2,640 metric rows pass.

Read [fixed design](PROTOCOL.md), [source record](data/source/manifest.json), [full validation search](results/validation-metrics.csv) and [validation-only selection](SELECTION.json). A freeze must precede held summaries. Source values/quality are visible without blinding; past-only donor indices assume idealized prior-day availability. Actual historical vintages remain unverified.

Published departures do not establish bike stock, dock availability, latent demand, true station openings or relocation outcomes. Coordinate groups are proxies, not verified physical sites. No completed-study, operational-benefit, savings or novelty claim. Formal-publication projects including Azure remain private.
