"""
Tests for the reconciliation logic.

Uses Django TestCase so each test runs in a transaction that is rolled back.
We test _reconcile() directly — the pure function — so these tests are fast
and do not depend on any external state.

Coverage:
  - Each of the 5 disagreement types
  - Cross-tenant reference (LOCATION_MISMATCH) is NOT treated as a value match
  - Blank B value is mismatch, not zero
  - Blank actor_id in A is NOT a disagreement (the "non-error" case)
  - Clean matching record produces no disagreement
"""
from decimal import Decimal

from django.test import TestCase

from reconciliation.models import (
    Organization, Location, SystemARecord, SystemBEntry, Disagreement,
)
from reconciliation.services.reconciler import _reconcile


class ReconciliationTestCase(TestCase):
    """Base class with minimal org/location fixtures and helper factories."""

    def setUp(self):
        self.org_a = Organization.objects.create(org_id='ORG-A')
        self.org_b = Organization.objects.create(org_id='ORG-B')
        self.loc_101 = Location.objects.create(
            location_id='LOC-101', location_name='Location 101', org=self.org_a
        )
        self.loc_201 = Location.objects.create(
            location_id='LOC-201', location_name='Location 201', org=self.org_b
        )

    def make_a(self, record_id='REC-0001', location=None, total_value='100.00',
               actor_id='USR-01'):
        return SystemARecord.objects.create(
            record_id=record_id,
            location=location or self.loc_101,
            event_date='2026-01-01',
            category_code='CAT-01',
            actor_id=actor_id,
            base_value=Decimal('80.00'),
            adjustment=Decimal('20.00'),
            total_value=Decimal(total_value),
            state='CONFIRMED',
            import_row=1,
        )

    def make_b(self, entry_id='ENT-0001', system_a_record=None, location=None,
               raw_value='100.00', parsed_value=None, raw_record_ref='REC-0001'):
        from reconciliation.services.normalizer import parse_value
        if parsed_value is None:
            parsed_value = parse_value(raw_value)
        return SystemBEntry.objects.create(
            entry_id=entry_id,
            raw_record_ref=raw_record_ref,
            normalized_record_ref='REC-0001',
            system_a_record=system_a_record,
            location=location or self.loc_101,
            recorded_on='2026-01-01',
            raw_value=raw_value,
            parsed_value=parsed_value,
            label='Test entry',
            import_row=1,
            import_notes='',
        )


class TestMissingInB(ReconciliationTestCase):
    def test_missing_in_b(self):
        """A record with no B entry is flagged MISSING_IN_B."""
        a = self.make_a()
        results = _reconcile([a], [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, Disagreement.REASON_MISSING)
        self.assertEqual(results[0].record_id, 'REC-0001')
        self.assertEqual(results[0].system_a_value, Decimal('100.00'))
        self.assertIsNone(results[0].system_b_value)

    def test_clean_match_produces_no_disagreement(self):
        """A record that agrees with B is NOT flagged — this is the happy path."""
        a = self.make_a(total_value='100.00')
        b = self.make_b(system_a_record=a, raw_value='100.00')
        results = _reconcile([a], [b])
        self.assertEqual(results, [])


class TestOrphanInB(ReconciliationTestCase):
    def test_orphan_in_b(self):
        """B entry with no matching A record is flagged ORPHAN_IN_B."""
        b = self.make_b(system_a_record=None, raw_record_ref='REC-9999')
        results = _reconcile([], [b])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, Disagreement.REASON_ORPHAN)
        self.assertIsNone(results[0].system_a_value)
        # B org is preserved from B's location
        self.assertIsNotNone(results[0].system_b_org)


class TestDuplicateInB(ReconciliationTestCase):
    def test_duplicate_in_b(self):
        """Two B entries for the same A record produce exactly one DUPLICATE_IN_B."""
        a = self.make_a()
        b1 = self.make_b(entry_id='ENT-001', system_a_record=a)
        b2 = self.make_b(entry_id='ENT-002', system_a_record=a)
        results = _reconcile([a], [b1, b2])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, Disagreement.REASON_DUPLICATE)
        self.assertIn('ENT-001', results[0].system_b_entry_ids)
        self.assertIn('ENT-002', results[0].system_b_entry_ids)

    def test_duplicate_does_not_also_produce_value_mismatch(self):
        """When there is a duplicate, we do not also flag VALUE_MISMATCH."""
        a = self.make_a(total_value='100.00')
        b1 = self.make_b(entry_id='ENT-001', system_a_record=a, raw_value='999.00')
        b2 = self.make_b(entry_id='ENT-002', system_a_record=a, raw_value='888.00')
        results = _reconcile([a], [b1, b2])
        reasons = [r.reason for r in results]
        self.assertEqual(reasons, [Disagreement.REASON_DUPLICATE])


class TestValueMismatch(ReconciliationTestCase):
    def test_value_mismatch(self):
        """B value differs from A total_value → VALUE_MISMATCH."""
        a = self.make_a(total_value='121388.01')
        b = self.make_b(system_a_record=a, raw_value='94834.38')
        results = _reconcile([a], [b])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, Disagreement.REASON_VALUE)
        self.assertEqual(results[0].system_a_value, Decimal('121388.01'))
        self.assertEqual(results[0].system_b_value, Decimal('94834.38'))

    def test_blank_value_is_mismatch_not_zero(self):
        """
        A blank B value is a VALUE_MISMATCH.
        It must NOT be treated as zero or as agreeing with a zero A value.
        (Reflects ENT/2026/4050 in actual data.)
        """
        a = self.make_a(total_value='160405.85')
        b = self.make_b(system_a_record=a, raw_value='', parsed_value=None)
        results = _reconcile([a], [b])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, Disagreement.REASON_VALUE)
        self.assertIsNone(results[0].system_b_value)  # stored as None, not 0


class TestLocationMismatch(ReconciliationTestCase):
    def test_location_mismatch(self):
        """
        B entry with a different location than A → LOCATION_MISMATCH.
        (Reflects REC-1077: A=LOC-102/ORG-A, B=LOC-201/ORG-B in actual data.)
        """
        a = self.make_a(location=self.loc_101)   # ORG-A
        b = self.make_b(system_a_record=a, location=self.loc_201)  # ORG-B
        results = _reconcile([a], [b])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, Disagreement.REASON_LOCATION)
        self.assertEqual(results[0].system_a_location, 'LOC-101')
        self.assertEqual(results[0].system_b_location, 'LOC-201')
        self.assertEqual(results[0].system_a_org.org_id, 'ORG-A')
        self.assertEqual(results[0].system_b_org.org_id, 'ORG-B')

    def test_cross_tenant_reference_does_not_match(self):
        """
        Even when A and B values agree, a location mismatch (cross-tenant)
        must still be flagged — we must not merge ORG-A and ORG-B records.
        """
        a = self.make_a(location=self.loc_101, total_value='100.00')  # ORG-A
        b = self.make_b(
            system_a_record=a,
            location=self.loc_201,   # ORG-B — wrong tenant
            raw_value='100.00'       # same value, but irrelevant
        )
        results = _reconcile([a], [b])
        # LOCATION_MISMATCH must be flagged even when values agree
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, Disagreement.REASON_LOCATION)

    def test_location_mismatch_does_not_also_produce_missing(self):
        """
        A record with a location-mismatched B entry is NOT also MISSING_IN_B.
        The A record is referenced by B (even if the location is wrong).
        """
        a = self.make_a(location=self.loc_101)
        b = self.make_b(system_a_record=a, location=self.loc_201)
        results = _reconcile([a], [b])
        reasons = [r.reason for r in results]
        self.assertNotIn(Disagreement.REASON_MISSING, reasons)


class TestNonError(ReconciliationTestCase):
    def test_blank_actor_id_in_a_is_not_a_disagreement(self):
        """
        REC-1050 in system_a.csv has a blank actor_id.
        This is an optional field — its absence is NOT a reconciliation disagreement.
        If the B value matches A's total_value, no disagreement is produced.
        This is the 'non-error that must be correctly identified as a non-error'
        per the assignment spec.
        """
        a = self.make_a(
            record_id='REC-1050',
            total_value='160405.85',
            actor_id='',          # blank — the non-error case
        )
        b = self.make_b(
            system_a_record=a,
            raw_value='160405.85',  # matches A
        )
        results = _reconcile([a], [b])
        # blank actor_id is not a disagreement if values agree
        self.assertEqual(results, [])
