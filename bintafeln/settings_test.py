"""Einstellungen für pytest. Platzhalterwerte, niemals echte Schlüssel."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "nur-fuer-tests-kein-echter-schluessel")
os.environ.setdefault("POSTGRES_PASSWORD", "nur-lokal-test")
os.environ.setdefault("POSTGRES_HOST", "localhost")

from bintafeln.settings import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Im Betrieb liegt der Cache in der Datenbank (ADR 0093); in Tests reicht der prozesslokale
# Speicher-Cache (schnell, kein Datenbankzugriff für reine Prüftests). Dass der Datenbank-Cache
# wirklich funktioniert, prüft test_rollen_und_anmeldung.test_datenbank_cache_funktioniert.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Tests laufen ohne collectstatic; die Prüfsummen-Namen braucht es nur im Betrieb.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
