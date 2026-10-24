from django.urls import path

from apps.konten import views, views_mitarbeitende

app_name = "konten"

urlpatterns = [
    path("anmelden/", views.anmelden, name="anmelden"),
    path("abmelden/", views.abmelden, name="abmelden"),
    path("", views.mein_konto, name="mein_konto"),
    path("passwort/", views.passwort_aendern, name="passwort_aendern"),
    path("passwort/vergessen/", views.passwort_vergessen, name="passwort_vergessen"),
    path(
        "passwort/setzen/<uidb64>/<token>/",
        views.PasswortSetzen.as_view(),
        name="passwort_setzen",
    ),
    path("mitarbeitende/", views_mitarbeitende.liste, name="mitarbeitende"),
    path("mitarbeitende/archiv/", views_mitarbeitende.archiv, name="mitarbeitende_archiv"),
    path("mitarbeitende/neu/", views_mitarbeitende.anlegen, name="mitarbeiter_neu"),
    path("mitarbeitende/<int:pk>/", views_mitarbeitende.bearbeiten, name="mitarbeiter"),
    path("mitarbeitende/<int:pk>/sperren/", views_mitarbeitende.sperren, name="sperren"),
    path("mitarbeitende/<int:pk>/entsperren/", views_mitarbeitende.entsperren, name="entsperren"),
    path(
        "mitarbeitende/<int:pk>/passwort/",
        views_mitarbeitende.passwort_zuruecksetzen,
        name="passwort_zuruecksetzen",
    ),
    path("mitarbeitende/<int:pk>/link/", views_mitarbeitende.link_senden, name="link_senden"),
    path("mitarbeitende/<int:pk>/stammdaten/", views_mitarbeitende.stammdaten, name="stammdaten"),
    path("mitarbeitende/<int:pk>/kopie/", views_mitarbeitende.kopie_ansehen, name="kopie_ansehen"),
    path(
        "mitarbeitende/<int:pk>/kopie/hochladen/",
        views_mitarbeitende.kopie_hochladen,
        name="kopie_hochladen",
    ),
    path(
        "mitarbeitende/<int:pk>/kopie/loeschen/",
        views_mitarbeitende.kopie_entfernen,
        name="kopie_entfernen",
    ),
    path(
        "mitarbeitende/<int:pk>/schulungen/", views_mitarbeitende.schulung_neu, name="schulung_neu"
    ),
    path(
        "mitarbeitende/<int:pk>/schulungen/<int:schulung>/loeschen/",
        views_mitarbeitende.schulung_loeschen,
        name="schulung_loeschen",
    ),
    path(
        "mitarbeitende/einstellungen/",
        views_mitarbeitende.personal_einstellungen,
        name="personal_einstellungen",
    ),
    path(
        "mitarbeitende/<int:pk>/zwei-faktor/",
        views_mitarbeitende.zwei_faktor_zuruecksetzen,
        name="zwei_faktor_zuruecksetzen",
    ),
    path("zwei-faktor/einrichten/", views.zwei_faktor_einrichten, name="zwei_faktor_einrichten"),
    path("zwei-faktor/notfallcodes/", views.notfallcodes_neu, name="notfallcodes_neu"),
    path("zwei-faktor/abschalten/", views.zwei_faktor_abschalten, name="zwei_faktor_abschalten"),
]
