# DECISIONS

Engineering decisions made during this take-home assignment.
Each entry documents what was chosen, what was rejected, and why.

---

## Decision 1 — SQLite instead of PostgreSQL

**Decision:** Use SQLite as the database engine.

**Rejected:** PostgreSQL (suggested in the assignment brief).

**Reason:** This is a small take-home dataset (120 rows per system), and SQLite keeps the project easy to run from a clean clone without requiring a separate database server. Django's ORM keeps the application code largely database-independent. For a production deployment, I would use PostgreSQL and verify any database-specific behavior during the migration.

---

## Decision 2 — `Decimal` instead of `float` for value comparison

**Decision:** Use Python's `decimal.Decimal` for all monetary/value parsing and comparison.

**Rejected:** `float` (e.g. `float(a) == float(b)`).

**Reason:** Binary floating point cannot represent many decimal fractions exactly — `float('94834.38') != float('94834.38')` is a real risk — and financial comparisons require exact equality. `Decimal` is appropriate for exact decimal-value comparison and avoids binary floating-point precision issues.

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

## Decision 6 — `locations.csv` as the authoritative tenant mapping

**Decision:** Organization is derived exclusively through the `Location` associated with a record. The importer loads `locations.csv` first and uses the `location_id → organization` mapping when importing System A and System B.

**Rejected:** Inferring organization directly from System A/System B fields or maintaining a separate independent org mapping.

**Reason:** The assignment explicitly states that `locations.csv` is the only source of the location-to-organization mapping. Keeping Location as the source of truth avoids conflicting tenant information and ensures tenant filtering uses the same mapping for both systems.

---

## Decision 7 — `LOCATION_MISMATCH` as a distinct disagreement type

**Decision:** When System A and System B reference the same record ID but report different `location_id` values, classify this as `LOCATION_MISMATCH` — not `VALUE_MISMATCH`.

**Rejected:** Treating it as a value mismatch or ignoring the location difference.

**Reason:** Location determines organization (tenant). A System B entry from ORG-B referencing an ORG-A record is not just a value disagreement — it is a tenant boundary violation. Reporting it as `LOCATION_MISMATCH` makes the severity clear and prevents any downstream code from accidentally merging cross-tenant data. Because authentication is explicitly out of scope, the organization selector represents the current tenant context for this take-home. The API applies the organization filter rather than relying only on frontend filtering.

---

## Decision 8 — Explicit reconciliation precedence

**Decision:** For System B entries that resolve to a System A record, disagreements are evaluated in this order:

`LOCATION_MISMATCH > DUPLICATE_IN_B > VALUE_MISMATCH`

`ORPHAN_IN_B` is handled separately because the referenced System A record does not exist. `MISSING_IN_B` is also handled separately for System A records with no matching System B entry.

**Rejected:** Running independent checks that could produce multiple disagreement classifications for the same reconciliation case.

**Reason:** A reconciliation case should have one clear primary classification. A location mismatch should not also be reported as a value mismatch, and a duplicate should not additionally produce a value mismatch because the correct B value is ambiguous. Orphan and missing cases are separate because they represent absence of a valid counterpart rather than disagreement between two existing records.

---

## Decision 9 — Persist disagreements after reconciliation

**Decision:** After importing the source data, compute the disagreements and persist them in a Disagreement table. The API reads from this table.

**Rejected:** Computing disagreements dynamically on every API request.

**Reason:** For this dataset size, both approaches would perform adequately. Persisting the reconciliation result keeps the API simple and keeps the comparison logic isolated and testable. The import command clears/rebuilds the reconciliation results when a new import is performed (by calling `Disagreement.objects.all().delete()`), so the disagreement table represents the latest imported dataset.
