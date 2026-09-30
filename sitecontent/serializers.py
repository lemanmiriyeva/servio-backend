from rest_framework import serializers

from tenants.models import Plan
from .models import AboutValue, FaqItem, FeatureItem, HomeStep, SiteSettings


class SiteSettingsPublicSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = ["brand_name", "tagline", "logo", "hero_title", "hero_subtitle",
                  "email", "phone", "whatsapp", "address", "hours", "footer_note"]

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get("request")
        url = obj.logo.url
        return request.build_absolute_uri(url) if request else url


class FaqItemPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = FaqItem
        fields = ["id", "question", "answer"]


class FeatureItemPublicSerializer(serializers.ModelSerializer):
    points = serializers.SerializerMethodField()

    class Meta:
        model = FeatureItem
        fields = ["id", "icon", "tone", "title", "short_description", "points"]

    def get_points(self, obj):
        return obj.points_list()


class AboutValuePublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = AboutValue
        fields = ["id", "icon", "title", "text"]


class HomeStepPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeStep
        fields = ["id", "number", "title", "description"]


class PublicPlanSerializer(serializers.ModelSerializer):
    features = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = ["id", "name", "price_monthly", "max_branches", "max_users",
                  "public_description", "features", "is_featured"]

    def get_features(self, obj):
        return obj.public_features_list()
