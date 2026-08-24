from django.db import models

class Organization(models.Model):
    org_id = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.org_id

    class Meta:
        ordering = ['org_id']


class Location(models.Model):
    location_id = models.CharField(max_length=50, unique=True)
    location_name = models.CharField(max_length=200)
    org = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='locations')

    def __str__(self):
        return f"{self.location_id} ({self.org.org_id})"

    class Meta:
        ordering = ['location_id']


class SystemARecord(models.Model):
    record_id = models.CharField(max_length=50, unique=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='system_a_records')
    event_date = models.DateField()
    category_code = models.CharField(max_length=50)
    actor_id = models.CharField(max_length=50, blank=True)
    base_value = models.DecimalField(max_digits=14, decimal_places=2)
    adjustment = models.DecimalField(max_digits=14, decimal_places=2)
    total_value = models.DecimalField(max_digits=14, decimal_places=2)
    state = models.CharField(max_length=50)
    import_row = models.PositiveIntegerField(help_text="1-based row number in source CSV")

    def __str__(self):
        return self.record_id

    class Meta:
        ordering = ['record_id']


class SystemBEntry(models.Model):
    entry_id = models.CharField(max_length=50, unique=True)
    raw_record_ref = models.CharField(max_length=200, help_text="Exact value from CSV, preserved as-is")
    normalized_record_ref = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Normalized form, or null if the reference could not be resolved"
    )
    system_a_record = models.ForeignKey(
        SystemARecord, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='b_entries',
        help_text="Null if reference is orphaned or unresolvable"
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='system_b_entries')
    recorded_on = models.DateField()
    raw_value = models.CharField(max_length=200, help_text="Exact value from CSV")
    parsed_value = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Parsed Decimal, or null if raw_value was blank or unparseable"
    )
    label = models.CharField(max_length=200, blank=True)
    import_row = models.PositiveIntegerField(help_text="1-based row number in source CSV")
    import_notes = models.TextField(blank=True, help_text="Notes about normalization or parse errors")

    def __str__(self):
        return f"{self.entry_id} -> {self.raw_record_ref}"

    class Meta:
        ordering = ['entry_id']


class Disagreement(models.Model):
    REASON_MISSING = 'MISSING_IN_B'
    REASON_ORPHAN = 'ORPHAN_IN_B'
    REASON_DUPLICATE = 'DUPLICATE_IN_B'
    REASON_VALUE = 'VALUE_MISMATCH'
    REASON_LOCATION = 'LOCATION_MISMATCH'

    REASON_CHOICES = [
        (REASON_MISSING, 'Missing in B'),
        (REASON_ORPHAN, 'Orphan in B'),
        (REASON_DUPLICATE, 'Duplicate in B'),
        (REASON_VALUE, 'Value Mismatch'),
        (REASON_LOCATION, 'Location Mismatch'),
    ]

    record_id = models.CharField(max_length=50)
    reason = models.CharField(max_length=50, choices=REASON_CHOICES)

    system_a_org = models.ForeignKey(
        Organization, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='disagreements_as_a'
    )
    system_b_org = models.ForeignKey(
        Organization, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='disagreements_as_b'
    )

    system_a_location = models.CharField(max_length=50, blank=True)
    system_b_location = models.CharField(max_length=50, blank=True)

    system_a_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    system_b_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    system_b_raw_value = models.CharField(max_length=200, blank=True)

    system_b_entry_ids = models.JSONField(default=list)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['record_id']

    def __str__(self):
        return f"{self.record_id} — {self.reason}"
