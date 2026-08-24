from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as rf_filters
from rest_framework.generics import ListAPIView

from .models import Disagreement
from .serializers import DisagreementSerializer


class DisagreementListView(ListAPIView):
    serializer_class = DisagreementSerializer
    filter_backends = [DjangoFilterBackend, rf_filters.OrderingFilter]
    filterset_fields = ['reason']
    ordering_fields = ['system_a_value', 'system_b_value', 'record_id']
    ordering = ['record_id']

    def get_queryset(self):
        qs = Disagreement.objects.select_related('system_a_org', 'system_b_org').all()
        org_id = self.request.query_params.get('org_id')
        if org_id:
            qs = qs.filter(
                system_a_org__org_id=org_id
            ) | qs.filter(
                system_b_org__org_id=org_id,
                system_a_org__isnull=True
            )
        return qs.distinct()
