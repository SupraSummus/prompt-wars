from django.apps import AppConfig


class WarriorsConfig(AppConfig):
    name = "warriors"

    def ready(self):
        import warriors.scheduler  # noqa
