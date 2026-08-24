import re

CANONICAL_PATTERN = re.compile(r'^REC-\d+$')
REC_NO_HYPHEN_PATTERN = re.compile(r'^REC(\d+)$')
NUMERIC_ONLY_PATTERN = re.compile(r'^(\d+)$')

def normalize_record_ref(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    s = raw.strip().upper()
    s = re.sub(r'\s*-\s*', '-', s).replace(' ', '')
    if CANONICAL_PATTERN.match(s): return s
    m = REC_NO_HYPHEN_PATTERN.match(s)
    if m: return f'REC-{m.group(1)}'
    m = NUMERIC_ONLY_PATTERN.match(s)
    if m: return f'REC-{m.group(1)}'
    return None

def parse_value(raw: str):
    from decimal import Decimal, InvalidOperation
    if not raw or not raw.strip(): return None
    cleaned = raw.strip().replace(',', '')
    try: return Decimal(cleaned)
    except InvalidOperation: return None
