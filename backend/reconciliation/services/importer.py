import csv
import logging
from datetime import date
from pathlib import Path
from django.db import transaction

from reconciliation.models import Organization, Location, SystemARecord, SystemBEntry
from reconciliation.services.normalizer import normalize_record_ref, parse_value

logger = logging.getLogger(__name__)


def import_locations(path: Path) -> dict:
    """
    Import locations.csv. Returns location_id -> Location mapping.
    Each location maps to exactly one org (tenant). This file is the
    sole authoritative source for the location -> organization mapping.
    """
    location_map = {}
    with open(path, newline='', encoding='utf-8') as f:
        for row_num, row in enumerate(csv.DictReader(f), start=2):
            location_id = row.get('location_id', '').strip()
            org_id = row.get('org_id', '').strip()
            if not location_id or not org_id:
                logger.warning(f"locations.csv row {row_num}: missing location_id or org_id, skipped")
                continue
            with transaction.atomic():
                org, _ = Organization.objects.get_or_create(org_id=org_id)
                loc, created = Location.objects.update_or_create(
                    location_id=location_id,
                    defaults={'location_name': row.get('location_name', '').strip(), 'org': org}
                )
                location_map[location_id] = loc
                action = 'Imported' if created else 'Updated'
                logger.info(f"  {action} location {location_id} -> {org_id}")
    return location_map


def import_system_a(path: Path, location_map: dict) -> dict:
    """
    Import system_a.csv. Returns record_id -> SystemARecord mapping.
    A blank actor_id (e.g. REC-1050) is preserved as-is — it is not an error.
    """
    from decimal import Decimal, InvalidOperation
    record_map = {}
    with open(path, newline='', encoding='utf-8') as f:
        for row_num, row in enumerate(csv.DictReader(f), start=2):
            if not any(v.strip() for v in row.values()):
                continue  # skip trailing blank rows

            record_id = row.get('record_id', '').strip()
            if not record_id:
                logger.warning(f"system_a.csv row {row_num}: missing record_id, skipped")
                continue

            location_id = row.get('location_id', '').strip()
            location = location_map.get(location_id)
            if not location:
                logger.warning(f"system_a.csv row {row_num} ({record_id}): unknown location_id={location_id!r}, skipped")
                continue

            try:
                event_date = date.fromisoformat(row.get('event_date', '').strip())
            except ValueError as exc:
                logger.warning(f"system_a.csv row {row_num} ({record_id}): bad event_date: {exc}, skipped")
                continue

            def parse_decimal(field_name):
                raw = row.get(field_name, '').strip()
                try:
                    return Decimal(raw)
                except InvalidOperation:
                    logger.warning(f"system_a.csv row {row_num} ({record_id}): invalid {field_name}={raw!r}")
                    return None

            base_value = parse_decimal('base_value')
            adjustment = parse_decimal('adjustment')
            total_value = parse_decimal('total_value')
            if any(v is None for v in [base_value, adjustment, total_value]):
                logger.warning(f"system_a.csv row {row_num} ({record_id}): skipped due to invalid numeric field(s)")
                continue

            actor_id = row.get('actor_id', '').strip()  # blank is valid (e.g. REC-1050)
            if not actor_id:
                logger.info(f"  system_a.csv row {row_num} ({record_id}): actor_id is blank (not an error)")

            with transaction.atomic():
                rec, created = SystemARecord.objects.update_or_create(
                    record_id=record_id,
                    defaults={
                        'location': location,
                        'event_date': event_date,
                        'category_code': row.get('category_code', '').strip(),
                        'actor_id': actor_id,
                        'base_value': base_value,
                        'adjustment': adjustment,
                        'total_value': total_value,
                        'state': row.get('state', '').strip(),
                        'import_row': row_num,
                    }
                )
                record_map[record_id] = rec
    return record_map


def import_system_b(path: Path, location_map: dict, record_map: dict):
    """
    Import system_b.csv. All rows are imported.
    - Raw record_ref is always preserved exactly as in the CSV.
    - Dirty references are normalized and the transformation is noted in import_notes.
    - Blank values are stored as NULL (not zero).
    - Comma-formatted numbers (Indian style) are parsed correctly.
    - An orphan reference (no matching System A record) is still imported.
    """
    with open(path, newline='', encoding='utf-8') as f:
        for row_num, row in enumerate(csv.DictReader(f), start=2):
            if not any(v.strip() for v in row.values()):
                continue  # skip trailing blank rows

            entry_id = row.get('entry_id', '').strip()
            if not entry_id:
                logger.warning(f"system_b.csv row {row_num}: missing entry_id, skipped")
                continue

            location_id = row.get('location_id', '').strip()
            location = location_map.get(location_id)
            if not location:
                logger.warning(f"system_b.csv row {row_num} ({entry_id}): unknown location_id={location_id!r}, skipped")
                continue

            # Normalize record_ref — raw value is always preserved
            raw_ref = row.get('record_ref', '')  # preserve exact CSV value including whitespace
            norm_ref = normalize_record_ref(raw_ref)
            sys_a = record_map.get(norm_ref) if norm_ref else None

            try:
                recorded_on = date.fromisoformat(row.get('recorded_on', '').strip())
            except ValueError as exc:
                logger.warning(f"system_b.csv row {row_num} ({entry_id}): bad recorded_on: {exc}, skipped")
                continue

            # Parse value — raw value is always preserved
            raw_value = row.get('value', '')  # exact CSV value
            parsed_value = parse_value(raw_value)

            # Build import_notes to make every transformation auditable
            notes = []
            stripped_ref = raw_ref.strip()
            if raw_ref != stripped_ref:
                notes.append(f"record_ref had surrounding whitespace: {raw_ref!r}")
            if norm_ref and norm_ref != stripped_ref.upper():
                notes.append(f"record_ref normalized from {stripped_ref!r} to {norm_ref!r}")
            if norm_ref is None and stripped_ref:
                notes.append(f"record_ref {stripped_ref!r} could not be normalized to a known format")
            if norm_ref and not sys_a:
                notes.append(f"normalized ref {norm_ref!r} not found in System A — orphan entry")
            if raw_value.strip() == '':
                notes.append("value is blank; stored as NULL (not zero)")
            elif ',' in raw_value and parsed_value is not None:
                notes.append(f"value used comma formatting ({raw_value!r}); parsed to {parsed_value}")
            elif raw_value.strip() and parsed_value is None:
                notes.append(f"value {raw_value!r} could not be parsed; stored as NULL")

            with transaction.atomic():
                SystemBEntry.objects.update_or_create(
                    entry_id=entry_id,
                    defaults={
                        'raw_record_ref': raw_ref,
                        'normalized_record_ref': norm_ref,
                        'system_a_record': sys_a,
                        'location': location,
                        'recorded_on': recorded_on,
                        'raw_value': raw_value,
                        'parsed_value': parsed_value,
                        'label': row.get('label', '').strip(),
                        'import_row': row_num,
                        'import_notes': '; '.join(notes),
                    }
                )
