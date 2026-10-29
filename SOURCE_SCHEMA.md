# Exact source schema checked before values

The January 2024 official archive header matches all four declared fields without an alias change:

| Field | Analysis use |
|---|---|
| started_at | Nominal source civil calendar date; no timezone conversion or elapsed-duration inference |
| start_station_id | Published station key, preserved as text |
| start_lat | Initial-quarter coordinate median/quality only |
| start_lng | Initial-quarter coordinate median/quality only |

The header was read after protocol commit 220524119c6234d78ce8fc3bb708ac6464da3b43 and before any trip values were inspected. Other fields are excluded from analysis/public output. The ZIP has one eligible CSV member, JC-202401-citibike-tripdata.csv. Archive SHA-256: d59d149f200fb81e204099afb0f76f1b02267bb2d605e92309e6f9974b176e15; 1,883,296 bytes. Every later archive/member must pass the same selected-column contract and retain its own hash.

These are provider-published departure rows, not verified unique trips, demand or station-stock labels. The unshifted primary bootstrap scope is clarified before values; source/design parameters and held boundaries remain unchanged.
