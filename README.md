# Station geography transfer

Can geographical pooling transfer recorded departure counts when a station history is withheld? This fixed retrospective comparison uses published 2024 departure rows and initial-quarter coordinate medians. It simulates cold start on previously observed station IDs; it does not verify actual openings, relocations, bike stock or dock availability.

Conditional finding. Across 12 held coordinate groups and 2,208 station-days, geographic MAE is 11.621 departures/day versus 21.047 for a pooled weekday baseline, a 44.8% reduction. Two groups have higher errors. Temporal settings also differ between the selected model and baseline, so the comparison does not isolate geography's contribution. All 54 validation candidates and the full held stress grid remain available.

Next evidence. Test count transfer prospectively only after verifying station identity, geometry and input vintages. Immediate complete prior-day donor counts are an idealized assumption; the public files were posted later. Obtain stock, availability and opening/relocation telemetry before a rebalancing decision. No operational benefit or realized savings is established.

Start with the [decision summary and complete tables](DECISION_SUMMARY.md), [protocol](PROTOCOL.md), [frozen selection](FREEZE.json), [source record](data/source/manifest.json), [all results](results) and [independent manuscript](paper/manuscript.pdf).

![All twelve held groups](figures/held_group_errors.png)

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python src/check_reproduction.py
python src/verify_figures.py
python src/verify_paper.py
python src/verify_public_package.py
```

Nineteen fixtures; 24 protected dependencies; exact and tolerance-aware isolated replay; original reviewed figures. Independent program work, not peer reviewed. Formal-publication projects including Azure remain private.
