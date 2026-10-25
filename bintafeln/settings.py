"""Django-Einstellungen für bintafeln.

Alle installationsspezifischen Werte kommen aus Umgebungsvariablen (siehe .env.example).
Ist BINTAFELN_DOMAIN gesetzt, läuft bintafeln im Produktionsmodus mit TLS;
ist sie leer, im Entwicklungsmodus über http://IP.
"""

from pathlib import Path

from bintafeln import umgebung

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = umgebung.text("DJANGO_SECRET_KEY")
DEBUG = umgebung.schalter("DJANGO_DEBUG", False)

DOMAIN = umgebung.text("BINTAFELN_DOMAIN", "")
PRODUKTION = bool(DOMAIN)

# Öffentliche Demo mit erfundenen Daten (ADR 0022): Hinweis auf jeder Seite, Zugangsdaten auf
# der Anmeldeseite, `manage.py demo_zuruecksetzen` erlaubt.
DEMO = umgebung.schalter("BINTAFELN_DEMO", False)
# Entwicklungsmodus im Heimnetz: zusätzlich https://ADRESSE mit eigenem Zertifikat (ADR 0041)
HEIMNETZ_ADRESSE = "" if PRODUKTION else umgebung.text("BINTAFELN_HEIMNETZ_ADRESSE", "")
DEMO_PASSWORT = umgebung.text("BINTAFELN_DEMO_PASSWORT", "")

if PRODUKTION:
    ALLOWED_HOSTS = umgebung.liste("DJANGO_ALLOWED_HOSTS", [DOMAIN])
    CSRF_TRUSTED_ORIGINS = umgebung.liste("DJANGO_CSRF_TRUSTED_ORIGINS", [f"https://{DOMAIN}"])
else:
    # Entwicklungsmodus: Zugriff über beliebige IP im lokalen Netz.
    ALLOWED_HOSTS = umgebung.liste("DJANGO_ALLOWED_HOSTS", ["*"])
    CSRF_TRUSTED_ORIGINS = umgebung.liste("DJANGO_CSRF_TRUSTED_ORIGINS", [])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "auditlog",
    "apps.konten",
    "apps.core",
    "apps.kunden",
    "apps.ausgabe",
    "apps.personal",
    "apps.antraege",
    "apps.statistik",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "apps.core.middleware.EinrichtungMiddleware",
    "apps.konten.middleware.PasswortAendernMiddleware",
    "apps.konten.middleware.ZweiFaktorMiddleware",
]

ROOT_URLCONF = "bintafeln.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.tafel",
            ],
        },
    },
]

WSGI_APPLICATION = "bintafeln.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": umgebung.text("POSTGRES_DB", "bintafeln"),
        "USER": umgebung.text("POSTGRES_USER", "bintafeln"),
        "PASSWORD": umgebung.text("POSTGRES_PASSWORD"),
        "HOST": umgebung.text("POSTGRES_HOST", "db"),
        "PORT": umgebung.text("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_USER_MODEL = "konten.Benutzer"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "konten:anmelden"
# Einladungs- und Zurücksetzen-Links gelten 3 Tage (ADR 0016).
PASSWORD_RESET_TIMEOUT = 3 * 24 * 60 * 60


def _otp_aussteller(geraet):
    from apps.konten.zwei_faktor import aussteller

    return aussteller(geraet)


# Name der Tafel als Aussteller in der Authenticator-App
OTP_TOTP_ISSUER = _otp_aussteller
LOGIN_REDIRECT_URL = "core:start"
LOGOUT_REDIRECT_URL = "konten:anmelden"

LANGUAGE_CODE = "de-de"
LANGUAGES = [("de", "Deutsch")]
TIME_ZONE = umgebung.text("BINTAFELN_ZEITZONE", "Europe/Berlin")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = Path(umgebung.text("BINTAFELN_STATIC_ROOT", str(BASE_DIR / "data" / "static")))
STATICFILES_DIRS = [BASE_DIR / "static"]
# Dateinamen mit Prüfsumme (bintafeln.3f9a1c.css): Nach einem Update lädt jeder Browser die
# neue Fassung, obwohl Caddy statische Dateien lange zwischenspeichern lässt.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(umgebung.text("BINTAFELN_MEDIA_ROOT", str(BASE_DIR / "data" / "media")))

# Statusdatei, die der Dienst "backup" nach jeder Sicherung schreibt.
SICHERUNG_STATUSDATEI = Path(
    umgebung.text("BINTAFELN_SICHERUNG_STATUS", str(BASE_DIR / "sicherungen" / "status.txt"))
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Der Proxy (Caddy) setzt X-Forwarded-Proto; die App ist nur über ihn erreichbar.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 10  # eine Schicht

if PRODUKTION:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_SSL_REDIRECT = False  # erledigt Caddy

# Änderungsprotokoll: Anfragen ohne angemeldeten Benutzer bleiben ohne Akteur.
AUDITLOG_INCLUDE_ALL_MODELS = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": umgebung.text("BINTAFELN_LOGLEVEL", "INFO")},
}
