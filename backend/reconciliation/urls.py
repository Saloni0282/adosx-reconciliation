from django.urls import path
from .views import DisagreementListView

urlpatterns = [
    path('disagreements/', DisagreementListView.as_view(), name='disagreements'),
]
