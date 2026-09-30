from django.contrib import admin

from .models import AboutValue, FaqItem, FeatureItem, HomeStep, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("brand_name", "email", "phone")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FaqItem)
class FaqItemAdmin(admin.ModelAdmin):
    list_display = ("question", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(FeatureItem)
class FeatureItemAdmin(admin.ModelAdmin):
    list_display = ("title", "icon", "tone", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(AboutValue)
class AboutValueAdmin(admin.ModelAdmin):
    list_display = ("title", "icon", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(HomeStep)
class HomeStepAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "order", "is_active")
    list_editable = ("order", "is_active")
