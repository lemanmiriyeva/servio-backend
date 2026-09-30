from django.apps import AppConfig


class SitecontentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sitecontent"
    verbose_name = "Sayt məzmunu"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from tenants.models import Plan
        from . import models as sc_models
        from .cache import invalidate_site_content_cache

        for model in (sc_models.SiteSettings, sc_models.FaqItem, sc_models.FeatureItem,
                      sc_models.AboutValue, sc_models.HomeStep, Plan):
            post_save.connect(invalidate_site_content_cache, sender=model, weak=False)
            post_delete.connect(invalidate_site_content_cache, sender=model, weak=False)
