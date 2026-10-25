from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "bintafeln Verwaltung"
admin.site.site_title = "bintafeln"

urlpatterns = [
    # Auch die Verwaltung nutzt die eigene Anmeldung (mit Zwei-Faktor).
    path(
        "admin/login/",
        RedirectView.as_view(pattern_name="konten:anmelden", query_string=True),
    ),
    path("admin/", admin.site.urls),
    path("konten/", include("apps.konten.urls")),
    path("kunden/", include("apps.kunden.urls")),
    path("ausgabe/", include("apps.ausgabe.urls")),
    path("statistik/", include("apps.statistik.urls")),
    path("adressen/", include("apps.adressen.urls")),
    path("spenden/", include("apps.spenden.urls")),
    path("mitglieder/", include("apps.mitglieder.urls")),
    path("serienbriefe/", include("apps.serienbriefe.urls")),
    path("personal/", include("apps.personal.urls")),
    path("antraege/", include("apps.antraege.urls")),
    # Öffentlich, ohne Anmeldung (ADR 0024)
    path("antrag/", include("apps.antraege.urls_oeffentlich")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
