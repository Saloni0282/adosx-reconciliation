# DECISIONS

Engineering decisions made during this take-home assignment.
Each entry documents what was chosen, what was rejected, and why.

---

## Decision 1 — SQLite instead of PostgreSQL

**Decision:** Use SQLite as the database engine.

**Rejected:** PostgreSQL (as suggested in the assignment brief).

**Reason:** No PostgreSQL server is installed on the development machine; the Django ORM abstracts the engine entirely, so all relational design decisions (foreign keys, indexes, constraints) are identical. For 120 rows, the engine choice has no practical effect. Switching to PostgreSQL in a real deployment requires only a `DATABASES` config change.

---

## Decision 2 — `Decimal` instead of `float` for value comparison

**Decision:** Use Python's `decimal.Decimal` for all monetary/value parsing and comparison.

**Rejected:** `float` (e.g. `float(a) == float(b)`).

**Reason:** Binary floating point cannot represent many decimal fractions exactly — `float('94834.38') != float('94834.38')` is a real risk — and financial comparisons require exact equality. `Decimal` is the correct type for this domain.

---

## Decision 3 — Preserve raw values alongside parsed values

**Decision:** Store both `raw_value` (exact CSV string) and `parsed_value` (parsed Decimal or None) in `SystemBEntry`. Similarly store `raw_record_ref` and `normalized_record_ref`.

**Rejected:** Store only the parsed/normalized value.

**Reason:** The assignment explicitly says no row should be silently dropped and dirty data must survive import. If we only stored the parsed value, a blank or malformed value would become NULL with no trace of the original. Storing both makes every data transformation auditable and traceable back to the source CSV row.

---

## Decision 4 — Deterministic normalization, not fuzzy matching

**Decision:** `normalize_record_ref()` uses a fixed set of explicit rules (strip whitespace, uppercase, collapse spaces around hyphen, handle numeric-only format). If a reference does not match a known pattern, it returns `None`.

**Rejected:** Fuzzy matching (e.g. Levenshtein distance, "closest match" lookup).

**Reason:** Fuzzy matching can incorrectly associate unrelated records — a false association is worse than a missed match. Every normalization in this dataset fits a deterministic rule. References that cannot be resolved deterministically are stored as orphans and flagged, rather than silently associated with a wrong record.

---

## Decision 5 — Compare `SystemA.total_value` against `SystemB.value`

**Decision:** The value field used for reconciliation comparison is `SystemA.total_value` vs `SystemB.value`.

**Rejected:** Comparing against `base_value` or `adjustment`.

**Reason:** Confirmed by data inspection. When System B disagrees, the B value matches System A's `base_value` (not `total_value`), confirming that `total_value` is the intended field. System B records that agree with A all match `total_value`. For example: REC-1003 has `base_value=94834.38`, `total_value=121388.01`; System B has `value=94834.38` — a clear VALUE_MISMATCH against `total_value`.

---

## Decision 6 — `locations.csv` as the sole authoritative tenant mapping

**Decision:** Organization (tenant) is derived exclusively from `locations.csv`. The importer loads all locations first, then uses the in-memory `location_id → Location` map for all subsequent imports.

**Rejected:** Inferring org from System A or System B data directly, or storing org_id redundantly in SystemARecord/SystemBEntry.

**Reason:** The assignment explicitly states: "locations.csv is the only place that mapping exists." Inferring org from any other source would be incorrect. Storing it redundantly would create an inconsistency risk if the location changes.

---

## Decision 7 — `LOCATION_MISMATCH` as a distinct disagreement type

**Decision:** When System A and System B reference the same record ID but report different `location_id` values, classify this as `LOCATION_MISMATCH` — not `VALUE_MISMATCH`.

**Rejected:** Treating it as a value mismatch or ignoring the location difference.

**Reason:** Location determines organization (tenant). A System B entry from ORG-B referencing an ORG-A record is not just a value disagreement — it is a tenant boundary violation. Reporting it as `LOCATION_MISMATCH` makes the severity clear and prevents any downstream code from accidentally merging cross-tenant data. The reconciler checks location before comparing values; if locations differ, value comparison is skipped entirely.

---

## Decision 8 — Store disagreements in a `Disagreement` table, not compute on the fly

**Decision:** After import, compute all disagreements and persist them in a `Disagreement` table. The API reads from this table.

**Rejected:** Computing disagreements live on every API request (querying SystemARecord and SystemBEntry directly with complex SQL).

**Reason:** For this dataset size, both approaches are equally fast. Persisting disagreements makes the API simple (a single SELECT with filters) and keeps reconciliation logic in Python (testable) rather than spread across SQL queries. It also separates import from query concerns cleanly.
