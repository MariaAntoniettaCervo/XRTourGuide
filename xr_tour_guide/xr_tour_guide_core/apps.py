from django.apps import AppConfig

class xr_tour_guideCoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'xr_tour_guide_core'

    def ready(self):
            from . import signals_ai_backend