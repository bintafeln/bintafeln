from django.urls import path

from apps.konten import views, views_dokumente, views_mitarbeitende, views_rollen, views_stellen

app_name = "konten"

urlpatterns = [
    path("anmelden/", views.anmelden, name="anmelden"),
    path("anmelden/code/", views.anmelden_code, name="anmelden_code"),
    path("abmelden/", views.abmelden, name="abmelden"),
    path("", views.mein_konto, name="mein_konto"),
    path("passwort/", views.passwort_aendern, name="passwort_aendern"),
    path("passwort/vergessen/", views.passwort_vergessen, name="passwort_vergessen"),
    path(
        "passwort/setzen/<uidb64>/<token>/",
        views.PasswortSetzen.as_view(),
        name="passwort_setzen",
    ),
    path("rollen/", views_rollen.liste, name="rollen"),
    path("rollen/neu/", views_rollen.bearbeiten, name="rolle_neu"),
    path("rollen/<int:pk>/", views_rollen.bearbeiten, name="rolle"),
    path("rollen/<int:pk>/loeschen/", views_rollen.loeschen, name="rolle_loeschen"),
    path("mitarbeitende/", views_mitarbeitende.liste, name="mitarbeitende"),
    path("ausgabestellen/", views_stellen.liste, name="stellen"),
    path("ausgabestellen/<int:pk>/", views_stellen.stelle, name="stelle"),
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
    path("mitarbeitende/<int:pk>/auskunft/", views_mitarbeitende.auskunft_ansehen, name="auskunft"),
    path("meine-daten/", views_mitarbeitende.meine_auskunft, name="meine_auskunft"),
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
        "mitarbeitende/<int:pk>/dokumente/",
        views_dokumente.hochladen,
        name="dokument_hochladen",
    ),
    path(
        "mitarbeitende/<int:pk>/dokumente/<int:dokument>/",
        views_dokumente.ansehen,
        name="dokument_ansehen",
    ),
    path(
        "mitarbeitende/<int:pk>/dokumente/<int:dokument>/loeschen/",
        views_dokumente.loeschen,
        name="dokument_loeschen",
    ),
    path("mitarbeitende/kategorien/", views_dokumente.kategorie_neu, name="kategorie_neu"),
    path(
        "mitarbeitende/kategorien/<int:kategorie>/loeschen/",
        views_dokumente.kategorie_loeschen,
        name="kategorie_loeschen",
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
    path("geraete/entfernen/", views.geraet_entfernen, name="geraete_entfernen"),
    path("geraete/<int:pk>/entfernen/", views.geraet_entfernen, name="geraet_entfernen"),
    path("anmeldung/", views.anmelde_einstellungen, name="anmelde_einstellungen"),
    path(
        "mitarbeitende/<int:pk>/geraete/",
        views_mitarbeitende.geraete_zuruecksetzen,
        name="geraete_zuruecksetzen",
    ),
]
