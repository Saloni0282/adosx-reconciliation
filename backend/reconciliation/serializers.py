from rest_framework import serializers
from .models import Disagreement

class DisagreementSerializer(serializers.ModelSerializer):
    org_id = serializers.SerializerMethodField()
    system_b_org_id = serializers.SerializerMethodField()

    class Meta:
        model = Disagreement
        fields = [
            'id',
            'record_id',
            'reason',
            'org_id',
            'system_b_org_id',
            'system_a_location',
            'system_b_location',
            'system_a_value',
            'system_b_value',
            'system_b_raw_value',
            'system_b_entry_ids',
            'notes',
        ]

    def get_org_id(self, obj):
        return obj.system_a_org.org_id if obj.system_a_org else None

    def get_system_b_org_id(self, obj):
        return obj.system_b_org.org_id if obj.system_b_org else None
