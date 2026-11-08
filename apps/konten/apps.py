from django.apps import AppConfig


class KontenConfig(AppConfig):
    name = "apps.konten"
    label = "konten"
    verbose_name = "Konten und Rollen"

    def ready(self):
        from apps.konten import anmeldeprotokoll  # noqa: F401  (registriert das Fehlversuch-Signal)
