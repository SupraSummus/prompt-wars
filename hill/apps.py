from django.apps import AppConfig


class HillConfig(AppConfig):
    name = 'hill'

    def ready(self):
        import hill.scheduler  # noqa
