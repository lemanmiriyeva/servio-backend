from django.urls import path
from .views import DashboardView, ReportsSummaryView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("reports/summary/", ReportsSummaryView.as_view(), name="reports-summary"),
]
