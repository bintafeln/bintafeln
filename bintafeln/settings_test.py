"""Einstellungen für pytest. Platzhalterwerte, niemals echte Schlüssel."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "nur-fuer-tests-kein-echter-schluessel")
os.environ.setdefault("POSTGRES_PASSWORD", "nur-lokal-test")
os.environ.setdefault("POSTGRES_HOST", "localhost")

from bintafeln.settings import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
