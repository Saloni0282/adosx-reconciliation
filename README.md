# AdosX Engineering — System Reconciliation

A full-stack application that finds disagreements between two event-recording systems across multiple tenants.

## Project Overview

Two systems (System A and System B) record the same events. Neither is authoritative. This application:

1. Imports both systems' CSV data into a structured database
2. Normalizes dirty System B record references
3. Compares the two systems and flags every disagreement
4. Serves the results via a REST API
5. Displays them in a simple React UI with filtering and sorting

## Architecture

```
CSV files (locations, system_a, system_b)
        │
        ▼
Django management command: python manage.py import_data
        │  ├─ normalize dirty record references
        │  ├─ preserve raw values alongside parsed values
        │  └─ link System B entries to System A records
        ▼
SQLite database (5 tables: Organization, Location, SystemARecord, SystemBEntry, Disagreement)
        │
        ▼
Reconciliation service (pure Python, fully tested)
        │  ├─ MISSING_IN_B      – A record has no B entry
        │  ├─ ORPHAN_IN_B       – B entry references non-existent A record
        │  ├─ DUPLICATE_IN_B    – Multiple B entries for one A record
        │  ├─ LOCATION_MISMATCH – A and B report different locations (cross-tenant)
        │  └─ VALUE_MISMATCH    – Values differ (including blank B value)
        ▼
Django REST Framework API: GET /api/disagreements/
        │  ├─ ?reason=VALUE_MISMATCH
        │  ├─ ?org_id=ORG-A
        │  └─ ?ordering=system_a_value
        ▼
React + Vite frontend
        └─ filterable, sortable disagreements table
```

## Tech Stack

| Technology | Reason |
|---|---|
| Python / Django | Mature web framework with strong ORM for relational data |
| Django REST Framework | Standard DRF makes the API clean and testable |
| SQLite | Keeps the project portable and easy to run without database setup for this take-home |
| `decimal.Decimal` | Exact financial comparison — binary float is wrong for this |
| React + Vite | Fast, minimal frontend setup with no framework overhead |
| pytest + pytest-django | Idiomatic Python testing; easy to isolate the reconciliation logic |

**On SQLite vs PostgreSQL:** The assignment spec suggests PostgreSQL. SQLite was selected because this is a small take-home dataset (120 rows per system), and SQLite allows the project to run immediately out-of-the-box from a clean clone without requiring a separate database server. Django's ORM keeps the application code database-independent. For a production deployment, I would migrate to PostgreSQL and verify any database-specific behavior.

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Clone and enter project

```bash
git clone <repo-url>
cd adosx-reconciliation
```

### 2. Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

python manage.py makemigrations reconciliation
python manage.py migrate
```

### 3. Import data and run reconciliation

```bash
python manage.py import_data
```

Expected output:
```
Data directory: .../adosx-reconciliation/data
Importing locations...
  5 locations imported
Importing System A records...
  120 records imported
Importing System B entries...
  121 entries imported
Running reconciliation...
Reconciliation complete:
  DUPLICATE_IN_B: 2
  LOCATION_MISMATCH: 1
  MISSING_IN_B: 2
  ORPHAN_IN_B: 1
  VALUE_MISMATCH: 5
  TOTAL DISAGREEMENTS: 11
```

If the CSV files are not at `../data/` relative to `backend/`, pass the path explicitly:

```bash
python manage.py import_data --data-dir /path/to/csv/directory
```

### 4. Start the backend server

```bash
python manage.py runserver
```

API available at: http://localhost:8000/api/disagreements/

### 5. Frontend

```bash
cd ../frontend
npm install
npm run dev
```

UI available at: http://localhost:5173

### 6. Run tests

```bash
cd backend
python -m pytest reconciliation/tests/ -v
```

## Data Import

### What "dirty" means here

The CSV files contain real-world messiness:

| Issue | Example | How handled |
|---|---|---|
| Lowercase ref | `rec1034` | Normalized to `REC-1034` |
| Spaces in ref | ` REC - 1070 ` | Normalized to `REC-1070` |
| Numeric-only ref | `1112` | Normalized to `REC-1112` |
| Blank B value | `""` | Stored as `raw_value=""`, `parsed_value=NULL` (not zero) |
| Indian number format | `1,25,400.00` | Parsed to `Decimal("125400.00")` |
| Blank actor_id in A | REC-1050 | Imported as-is — optional field, not an error |
| Orphan reference | `REC-1999` | Imported as orphan; flagged in reconciliation |
| Duplicate references | REC-1042, REC-1055 | Both entries imported; flagged as DUPLICATE_IN_B |

### Nothing is silently dropped

Every source row is imported. For dirty fields:
- The original CSV value is always stored in `raw_record_ref` / `raw_value`
- The cleaned/parsed version is stored in `normalized_record_ref` / `parsed_value`
- The transformation is recorded in `import_notes`

If parsing fails, the parsed field is NULL and the raw field contains the original value.

## Reference Normalization

System B's `record_ref` column uses inconsistent formats. The `normalize_record_ref()` function handles exactly the formats found in the actual data:

```python
normalize_record_ref('REC-1001')      # -> 'REC-1001'  (canonical, unchanged)
normalize_record_ref('rec1034')       # -> 'REC-1034'  (lowercase + no hyphen)
normalize_record_ref(' REC - 1070 ') # -> 'REC-1070'  (whitespace + spaced hyphen)
normalize_record_ref('1112')          # -> 'REC-1112'  (numeric only)
normalize_record_ref('UNKNOWN-XYZ')  # -> None         (unresolvable)
```

This is **deterministic**, not fuzzy. Each transformation follows an explicit rule. If a reference cannot be resolved by a known rule, it returns `None` and is stored as an unresolvable orphan.

## Reconciliation Logic

Disagreements are computed by `reconciler.py` after import. The logic runs in this order:

### 1. ORPHAN_IN_B
A System B entry whose normalized `record_ref` does not match any System A `record_id`.  
Example: `ENT/2026/4901` → `REC-1999` (does not exist in System A).

### 2. LOCATION_MISMATCH
A System B entry that resolves to a System A record, but their `location_id` values differ.  
Example: REC-1077 — A has `LOC-102` (ORG-A), B has `LOC-201` (ORG-B).  
This takes precedence over value comparison. Records from different tenants must not be merged.

### 3. DUPLICATE_IN_B
More than one System B entry resolves to the same System A record (same location).  
Examples: REC-1042 and REC-1055 each have two System B entries.  
When a duplicate is detected, value comparison is skipped (ambiguous which B value is "correct").

### 4. VALUE_MISMATCH
Exactly one System B entry for a System A record (same location), but the values differ.  
Comparison: `SystemA.total_value` vs `SystemB.parsed_value` using `Decimal` (not float).  
A blank B value is a mismatch — it is stored as NULL, not treated as zero.

### 5. MISSING_IN_B
A System A record that has no System B entries at all.  
Examples: REC-1015 and REC-1061.

### Precedence

When multiple conditions could apply to the same record, higher-precedence checks take priority:

```
ORPHAN_IN_B > LOCATION_MISMATCH > DUPLICATE_IN_B > VALUE_MISMATCH
```

A location mismatch is reported as such even if the values happen to agree. A duplicate is reported even if both B values are wrong.

## Tenant Isolation

The `locations.csv` file is the **only** authoritative mapping from location to organization (tenant). The application never infers org from System A or System B data directly.

Organization derivation:
```
SystemARecord.location_id → Location.org → Organization.org_id
SystemBEntry.location_id  → Location.org → Organization.org_id
```

If a System B entry resolves to a System A record but their organizations differ, the result is classified as `LOCATION_MISMATCH` — not as a value comparison. This prevents ORG-A data from ever being matched against ORG-B data.

Because authentication is explicitly out of scope, the organization selector represents the current tenant context for this take-home. The API applies the organization filter rather than relying only on frontend filtering.

## API

### `GET /api/disagreements/`

Returns all disagreements as a JSON array.

**Filter by reason:**
```
GET /api/disagreements/?reason=VALUE_MISMATCH
GET /api/disagreements/?reason=MISSING_IN_B
GET /api/disagreements/?reason=ORPHAN_IN_B
GET /api/disagreements/?reason=DUPLICATE_IN_B
GET /api/disagreements/?reason=LOCATION_MISMATCH
```

**Filter by organization:**
```
GET /api/disagreements/?org_id=ORG-A
GET /api/disagreements/?org_id=ORG-B
```

Note: The org filter covers both `system_a_org` and `system_b_org`, so orphan entries (which only have a B org) are included correctly.

**Sort:**
```
GET /api/disagreements/?ordering=system_a_value
GET /api/disagreements/?ordering=-system_a_value
GET /api/disagreements/?ordering=system_b_value
```

## What Was NOT Built

- **Authentication / authorization** — explicitly out of scope per assignment
- **Pagination** — 11 disagreements don't need it
- **Production deployment** — Docker, Nginx, Gunicorn, environment config
- **Advanced UI** — plain HTML table is the right answer here
- **Performance optimization** — 120 rows, not relevant
- **Background jobs** — Celery, Redis, import queue
- **Audit log** — import history across multiple re-runs is not preserved (see Q&A c)

## How I Worked with the Agent

I used an AI coding assistant throughout this project:

1. **Data inspection first** — I had the agent run a Python script against all three CSVs before writing any application code. This produced the concrete list of dirty cases, disagreement counts, and the "non-error" case (REC-1050's blank actor_id).

2. **Schema review** — The agent proposed the database models. I reviewed them to confirm that `raw_record_ref` + `normalized_record_ref` and `raw_value` + `parsed_value` pairs correctly satisfy the "nothing silently dropped" requirement.

3. **Reconciliation logic** — The agent wrote the initial `_reconcile()` function. I reviewed the precedence order carefully, especially: does a LOCATION_MISMATCH record also get flagged as MISSING_IN_B? (Answer: no — it should not. I verified this is correctly handled.)

4. **Test generation** — The agent generated the initial test skeletons. I added `test_cross_tenant_reference_does_not_match`, `test_duplicate_does_not_also_produce_value_mismatch`, and the non-error test (`test_blank_actor_id_in_a_is_not_a_disagreement`) after reviewing what the agent produced.

5. **Bug found and fixed** — See Q&A section (a) below.

6. **Final review** — I checked every file against the evaluation criteria: raw data preserved, Decimal used, no silent drops, org filter correct, tenant boundary enforced.

---

## Q&A

### a. Name one thing the AI agent got wrong. How did you notice?

The initial `views.py` `get_queryset()` used only:
```python
qs.filter(system_a_org__org_id=org_id)
```

This silently excluded `ORPHAN_IN_B` disagreements when filtering by org_id. Orphan entries have `system_a_org=None` (there is no System A record to derive the org from); their org comes from `system_b_org`. So filtering by `ORG-A` missed `ENT/2026/4901` → `REC-1999`, which maps to `LOC-102` → `ORG-A` via System B's location.

I noticed because after importing and querying `?org_id=ORG-A`, the count was 8 when I expected 9 (the orphan was missing). I fixed it with a combined OR filter:
```python
qs.filter(system_a_org__org_id=org_id) | qs.filter(
    system_b_org__org_id=org_id,
    system_a_org__isnull=True
)
```

### b. Which part of your submission are you least confident about, and why?

The handling of an edge case not present in the actual data: what should happen if a System A record has *both* a same-location B entry *and* a different-location B entry? The current code flags the different-location entry as `LOCATION_MISMATCH` and processes the same-location entry for value comparison independently. This feels correct but there is no real data case to validate it against, so I cannot be fully confident the precedence is right.

### c. If you had a second day, what would you fix first?

I would add an import-run/audit model that records when an import occurred, how many rows were processed, and whether any rows failed parsing or validation. The current importer is safe to rerun, but it does not provide historical visibility into what changed between imports. This would make the reconciliation process easier to debug and more trustworthy in a production environment.
