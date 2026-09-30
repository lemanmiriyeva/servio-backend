from django.urls import path

from .views import PublicSiteContentView

urlpatterns = [
    path("site-content/", PublicSiteContentView.as_view(), name="public-site-content"),
]
