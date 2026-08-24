import pytest
from decimal import Decimal
from reconciliation.services.normalizer import normalize_record_ref, parse_value

class TestNormalizeRecordRef:
    def test_canonical_form_unchanged(self):
        assert normalize_record_ref('REC-1001') == 'REC-1001'
    def test_lowercase_normalized(self):
        assert normalize_record_ref('rec1034') == 'REC-1034'
    def test_spaces_around_hyphen_normalized(self):
        assert normalize_record_ref(' REC - 1070 ') == 'REC-1070'
    def test_numeric_only_normalized(self):
        assert normalize_record_ref('1112') == 'REC-1112'
    def test_empty_string_returns_none(self):
        assert normalize_record_ref('') is None
        assert normalize_record_ref('   ') is None
        assert normalize_record_ref(None) is None
    def test_unrecognized_format_returns_none(self):
        assert normalize_record_ref('UNKNOWN-FORMAT-XYZ') is None

class TestParseValue:
    def test_normal_decimal(self):
        assert parse_value('125400.00') == Decimal('125400.00')
    def test_indian_formatted_number(self):
        assert parse_value('1,25,400.00') == Decimal('125400.00')
    def test_blank_string_is_null(self):
        assert parse_value('') is None
    def test_none_is_null(self):
        assert parse_value(None) is None
    def test_unparseable_is_null(self):
        assert parse_value('not-a-number') is None
    def test_western_comma_format(self):
        assert parse_value('1,000.00') == Decimal('1000.00')
