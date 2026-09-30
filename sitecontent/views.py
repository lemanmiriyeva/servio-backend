from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from tenants.models import Plan
from .cache import CACHE_KEY
from .models import AboutValue, FaqItem, FeatureItem, HomeStep, SiteSettings
from .serializers import (
    AboutValuePublicSerializer, FaqItemPublicSerializer, FeatureItemPublicSerializer,
    HomeStepPublicSerializer, PublicPlanSerializer, SiteSettingsPublicSerializer,
)

CACHE_SECONDS = 300


class PublicSiteContentView(APIView):
    """
    GET /api/site-content/  — açıq (autentifikasiya tələb etmir).
    Ana səhifə, Funksiyalar, Qiymətlər, Haqqımızda, FAQ, Əlaqə səhifələrinin
    bazadan gələn bütün məzmununu tək sorğuda qaytarır.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        data = cache.get(CACHE_KEY)
        if data is None:
            settings_obj = SiteSettings.load()
            data = {
                "settings": SiteSettingsPublicSerializer(settings_obj, context={"request": request}).data,
                "faq": FaqItemPublicSerializer(FaqItem.objects.filter(is_active=True), many=True).data,
                "features": FeatureItemPublicSerializer(FeatureItem.objects.filter(is_active=True), many=True).data,
                "about_values": AboutValuePublicSerializer(AboutValue.objects.filter(is_active=True), many=True).data,
                "home_steps": HomeStepPublicSerializer(HomeStep.objects.filter(is_active=True), many=True).data,
                "plans": PublicPlanSerializer(
                    Plan.objects.filter(show_on_pricing_page=True), many=True
                ).data,
            }
            cache.set(CACHE_KEY, data, CACHE_SECONDS)
        return Response(data)
