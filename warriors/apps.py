from django.apps import AppConfig


class WarriorsConfig(AppConfig):
    name = "warriors"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        import warriors.scheduler  # noqa

        from .views import claim_session_warriors
        user_logged_in.connect(claim_session_warriors)
