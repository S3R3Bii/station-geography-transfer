# Recorded departure transfer under held station geography

## Decision, deliverable and acceptance

Does geographic pooling improve transfer of recorded departures to stations whose count histories are withheld? The deliverable is a reproducible finite comparison of 54 nearest-neighbor configurations, a simple pooled weekday baseline, fixed geographic metadata stresses and all failures. It is a simulated cold-start test on historically observed nominal station IDs. It does not establish true new-station openings, physical relocation behavior, latent demand, bike stock, dock availability, rebalancing benefit, novelty or operational readiness.

Success requires a protocol before trip-file retrieval; source rights, exact hashes, schema and independent parsing/reconciliation; initial-only station geometry and grouped spatial separation; past-only donor histories under an explicitly idealized availability assumption; all validation configurations and frozen selection before held summaries; independent metrics and isolated replay; readable executive presentation, original checked figures and rendered independent manuscript; scoped privacy/canonical audit and exact-head Linux/merge/tag proof. Required failures or unknowns block a release. No tuning or narrative selection from held outcomes.

## Source and permitted publication scope

Use the twelve official JC-2024 monthly ZIP files listed at the operator-linked download bucket. Only object names, sizes and modification metadata have been inspected so far. The listing totals 37,273,638 bytes. First inspect headers after this protocol is committed, and document any exact field-alias clarification before reading trip values.

The provider license permits analysis and source material within noncommercial analyses/reports/studies, with restrictions including standalone source redistribution, unauthorized interfaces/extraction, customer linkage and implied endorsement. This study uses the provided download interface and bounded statistical analysis. It is not a standalone trip-data mirror or a commercial product. Preserve the exact policy link and limitations; do not label the data public domain or grant broader source rights. Raw archives stay private. Public materials are minimal coarse station/day counts, rounded aggregate station geometry and the code/results needed to inspect this independent study. No source logos, private customer correlations or endorsement.

Read only started_at, start_station_id, start_lat and start_lng for analysis. Do not publish or analyze ride/customer/bike IDs, rider types, demographics, ending locations or individual trajectories. Full downloads are necessary because the authorized interface supplies ZIP files; keep them outside every Git repository. Do not infer unique rides or silently deduplicate legitimate same-station/date records. The target is the number of published departure rows. Preserve unknown station IDs, invalid dates and out-of-scope dates in exclusion totals, without public individual records.

Independent standard CSV and separate pandas parsing must reconcile all selected fields, member/month counts, daily aggregates and initial-geometry facts. Hash each archive/member. All expected monthly objects must exist; a missing file is not a zero month. Retain every CSV member except documented OS metadata files. Capture object metadata before/after to detect source replacement. Source accuracy/completeness remains unverified despite file consistency checks.

## Fixed first-quarter cohort and coordinate groups

Use January–March 2024 only for station metadata and eligibility. An ID must have published departures in each initial month, at least 95% valid regional coordinate pairs (latitude 40–41, longitude−75 to−73) and a nearest-rank 95th-percentile distance from its componentwise median no more than 150 m. Compute the dispersion radius from unrounded componentwise medians, then round medians to four decimals for public/model geometry. These are untuned quality screens, not surveyed station truth or verified relocation labels. Keep complete exclusions and all departure counts; coordinate invalidity does not erase a valid station/date record.

Connect IDs with median positions within 100 m; connected components proxy nearby related IDs and prevent such groups crossing folds. They are not independently verified physical sites. Canonical group key is the smallest station ID. SHA-256 of the literal study06-v1| plus group key, first eight digest bytes interpreted big-endian, modulo 5 gives folds. Folds 0–2 are donors, fold 3 validation and fold 4 held. Require at least 10 donor IDs and at least 2 validation/held groups; do not change the hash or thresholds to get favorable groups.

No withheld-station departure history enters a predictor. Its initial coordinates and activity eligibility are known for this simulated experiment, so it is not proof about an actually unopened station. Future station-name/position changes are not verified lineage. The daily grid counts zero published departures when the file has no rows for that ID/day; this does not establish an open station, zero latent demand or complete reporting.

## Predictor, finite search and timing

For each target date t, each donor uses prior dates in[t−W,t), W in{28,56,84} days. Match exact weekday or weekday/weekend; require at least 3 history days. Use no target-date or future donor counts. Donor means update during evaluation using prior donor records only. The source is retrospective and published monthly: immediate complete prior-day inputs are an idealized assumption, not a passed historical-vintage or live-availability gate.

Use spherical great-circle distances with declared radius 6371 km, not road/walking distances. For k in {3,5,10} nearest donors, weights are max(distance,0.100km)^(−p), p in {0,1,2}, normalized to sum1. Ties use donor ID. This yields 54 exploratory configurations, not an asserted globally optimal search. No optimizer or fine-tuning is used. Hyperparameter values and geometry screens are inherited design choices, not empirical best practices or validated physical thresholds.

The fixed baseline equally averages all donor means using an 84-day same-weekday history. Validation is April 1–June 30 on fold 3; held is July 1–December 31 on fold 4. Select geographic configuration by equal-coordinate-group MAE across all validation days/IDs, with exact ties preferring smaller k, lower exponent, shorter W, then weekday before daytype. Export every prediction, donor-history boundary, candidate metric and runtime. Freeze canonical source/protocol/model/checker and selected configuration before held analytical summaries. Source input/quality is visible without blinding. A failed held result stays failed.

## Held outcomes and geographic sensitivity

Report MAE, MSE and RMSE in departures/day, per-ID and per-coordinate-group results, complete month results and equal-group primary comparison. No guaranteed positive benefit or preferred outcome is prespecified. Check weights, convex prediction ranges and all history/label/fold boundaries independently.

For the frozen selected configuration retain unshifted primary coordinates and all 16 synthetic metadata displacements: 100m or500m along bearings0,45,...315 degrees, with count labels unchanged. These stress metadata sensitivity, not observed relocation outcomes. No geometry stress is used to select parameters or discard a station.

Resample held coordinate groups with replacement 1000 times using seed 20261029. Retain every sampled index and independently reconstruct selected-minus-baseline equal-group MAE. A central 95% empirical percentile range is conditional resampling sensitivity, not proof of independent spatial sampling or future coverage; dependence between groups and small group counts remain limitations.

Independent verification must not import model or metric helpers. Use a separate great-circle formulation, SQL histories and integer/rational mean reconstruction, explicit numerical tolerances (prediction/metric absolute 1e−8 for predictions and 1e−7 for metrics, distance absolute 1e−8 km), complete exclusions and deterministic isolated replay. Preserve failed receipts and corrected retrospective labels if any defect is discovered after held inspection.

Reviewed independent program manuscripts may be public after checks. Formal-publication projects including Azure optimization stay private. A protocol, download or source hold is not a completed study.
