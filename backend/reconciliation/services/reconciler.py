import logging
from collections import defaultdict
from reconciliation.models import SystemARecord, SystemBEntry, Disagreement

logger = logging.getLogger(__name__)

def run_reconciliation():
    Disagreement.objects.all().delete()
    disagreements = compute_disagreements()
    Disagreement.objects.bulk_create(disagreements)
    counts = defaultdict(int)
    for d in disagreements: counts[d.reason] += 1
    return dict(counts)

def compute_disagreements() -> list:
    all_a = list(SystemARecord.objects.select_related('location__org').all())
    all_b = list(SystemBEntry.objects.select_related('location__org', 'system_a_record').all())
    return _reconcile(all_a, all_b)

def _reconcile(all_a: list, all_b: list) -> list:
    disagreements = []
    a_by_id = {rec.record_id: rec for rec in all_a}
    b_by_a_record = defaultdict(list)
    orphaned_b = []

    for entry in all_b:
        if entry.system_a_record_id is None:
            orphaned_b.append(entry)
        else:
            b_by_a_record[entry.system_a_record.record_id].append(entry)

    for entry in orphaned_b:
        b_org = entry.location.org if entry.location else None
        disagreements.append(Disagreement(
            record_id=entry.normalized_record_ref or entry.raw_record_ref.strip(),
            reason=Disagreement.REASON_ORPHAN,
            system_a_org=None,
            system_b_org=b_org,
            system_a_location='',
            system_b_location=entry.location.location_id if entry.location else '',
            system_a_value=None,
            system_b_value=entry.parsed_value,
            system_b_raw_value=entry.raw_value,
            system_b_entry_ids=[entry.entry_id],
            notes=f"System B references non-existent System A record (Raw ref: {entry.raw_record_ref!r})",
        ))

    matched_a_ids = set()

    for record_id, b_entries in b_by_a_record.items():
        a_rec = a_by_id[record_id]
        matched_a_ids.add(record_id)

        a_loc_id = a_rec.location.location_id
        a_org = a_rec.location.org

        same_loc_entries = []
        diff_loc_entries = []
        for entry in b_entries:
            if a_loc_id == entry.location.location_id:
                same_loc_entries.append(entry)
            else:
                diff_loc_entries.append(entry)

        for entry in diff_loc_entries:
            disagreements.append(Disagreement(
                record_id=record_id,
                reason=Disagreement.REASON_LOCATION,
                system_a_org=a_org,
                system_b_org=entry.location.org,
                system_a_location=a_loc_id,
                system_b_location=entry.location.location_id,
                system_a_value=a_rec.total_value,
                system_b_value=entry.parsed_value,
                system_b_raw_value=entry.raw_value,
                system_b_entry_ids=[entry.entry_id],
                notes=f"Tenant boundary violation: System A has Location {a_loc_id} ({a_org}), but System B has Location {entry.location.location_id} ({entry.location.org})",
            ))

        if len(same_loc_entries) > 1:
            disagreements.append(Disagreement(
                record_id=record_id,
                reason=Disagreement.REASON_DUPLICATE,
                system_a_org=a_org,
                system_b_org=a_org,
                system_a_location=a_loc_id,
                system_b_location=a_loc_id,
                system_a_value=a_rec.total_value,
                system_b_value=None,
                system_b_raw_value='',
                system_b_entry_ids=[e.entry_id for e in same_loc_entries],
                notes=f"System B contains {len(same_loc_entries)} duplicate entries mapping to this record",
            ))
            continue

        if len(same_loc_entries) == 1:
            entry = same_loc_entries[0]
            a_val = a_rec.total_value
            b_val = entry.parsed_value
            if (b_val is None) or (a_val != b_val):
                note_text = ""
                if b_val is None:
                    note_text = f"System B value is blank (Raw value: {entry.raw_value!r})"
                else:
                    note_text = f"Value mismatch: System A Total Value is {a_val}, but System B Value is {b_val}"
                disagreements.append(Disagreement(
                    record_id=record_id,
                    reason=Disagreement.REASON_VALUE,
                    system_a_org=a_org,
                    system_b_org=a_org,
                    system_a_location=a_loc_id,
                    system_b_location=a_loc_id,
                    system_a_value=a_val,
                    system_b_value=b_val,
                    system_b_raw_value=entry.raw_value,
                    system_b_entry_ids=[entry.entry_id],
                    notes=note_text,
                ))

    for a_rec in all_a:
        if a_rec.record_id not in matched_a_ids:
            disagreements.append(Disagreement(
                record_id=a_rec.record_id,
                reason=Disagreement.REASON_MISSING,
                system_a_org=a_rec.location.org,
                system_b_org=None,
                system_a_location=a_rec.location.location_id,
                system_b_location='',
                system_a_value=a_rec.total_value,
                system_b_value=None,
                system_b_raw_value='',
                system_b_entry_ids=[],
                notes="System A record has no matching entry in System B",
            ))

    return disagreements
