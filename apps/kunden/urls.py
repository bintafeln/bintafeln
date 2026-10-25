from django.urls import path

from apps.kunden import views, views_ausgabestellen, views_bearbeiten, views_dokumente

app_name = "kunden"

urlpatterns = [
    path("", views.uebersicht, name="uebersicht"),
    path("haushalt/neu/", views_bearbeiten.haushalt_neu, name="haushalt_neu"),
    path(
        "haushalt/<path:kundennummer>/teil/<str:art>/neu/",
        views_bearbeiten.teil_bearbeiten,
        name="teil_neu",
    ),
    path(
        "haushalt/<path:kundennummer>/teil/<str:art>/<int:pk>/",
        views_bearbeiten.teil_bearbeiten,
        name="teil",
    ),
    path(
        "haushalt/<path:kundennummer>/teil/<str:art>/<int:pk>/loeschen/",
        views_bearbeiten.teil_loeschen,
        name="teil_loeschen",
    ),
    path(
        "haushalt/<path:kundennummer>/abholung/<int:pk>/loeschen/",
        views_bearbeiten.abholung_loeschen,
        name="abholung_loeschen",
    ),
    # Nach den genaueren Mustern: <path:…> würde sonst „…/teil/…/loeschen/“ verschlucken.
    path(
        "haushalt/<path:kundennummer>/bearbeiten/",
        views_bearbeiten.haushalt_bearbeiten,
        name="bearbeiten",
    ),
    path(
        "haushalt/<path:kundennummer>/loeschen/",
        views_bearbeiten.haushalt_loeschen,
        name="haushalt_loeschen",
    ),
    path("ausgabestellen/", views_ausgabestellen.liste, name="ausgabestellen"),
    path("ausgabestellen/neu/", views_ausgabestellen.bearbeiten, name="ausgabestelle_neu"),
    path("ausgabestellen/<int:pk>/", views_ausgabestellen.ausgabestelle, name="ausgabestelle"),
    path(
        "ausgabestellen/<int:pk>/bearbeiten/",
        views_ausgabestellen.bearbeiten,
        name="ausgabestelle_bearbeiten",
    ),
    path("listen/<str:art>/", views_bearbeiten.liste, name="liste"),
    path("listen/<str:art>/neu/", views_bearbeiten.listeneintrag, name="listeneintrag_neu"),
    path("listen/<str:art>/<int:pk>/", views_bearbeiten.listeneintrag, name="listeneintrag"),
    path(
        "listen/<str:art>/<int:pk>/loeschen/",
        views_bearbeiten.listeneintrag_loeschen,
        name="listeneintrag_loeschen",
    ),
    path("haushalt/<path:kundennummer>/notiz/", views.notiz_neu, name="notiz_neu"),
    path("notiz/<int:pk>/loeschen/", views.notiz_loeschen, name="notiz_loeschen"),
    path(
        "haushalt/<path:kundennummer>/dokument/",
        views_dokumente.hochladen,
        name="dokument_hochladen",
    ),
    path("dokument/<int:pk>/", views_dokumente.ansehen, name="dokument"),
    path("dokument/<int:pk>/loeschen/", views_dokumente.loeschen, name="dokument_loeschen"),
    path("haushalt/<path:kundennummer>/auskunft/", views.auskunft, name="auskunft"),
    path("haushalt/<path:kundennummer>/ausweis/", views.ausweis, name="ausweis"),
    path("haushalt/<path:kundennummer>/", views.haushalt, name="haushalt"),
    path("zugriffe/", views.zugriffe, name="zugriffe"),
    path("export/", views.exportieren, name="exportieren"),
    path("ausweise/", views.ausweise, name="ausweise"),
    path("ausweis/gestalten/", views_bearbeiten.ausweis_gestalten, name="ausweis_gestalten"),
    path("import/", views.import_hochladen, name="import"),
    path("import/<uuid:pk>/", views.import_vorschau, name="import_vorschau"),
    path("import/<uuid:pk>/uebernehmen/", views.import_uebernehmen, name="import_uebernehmen"),
    path("import/<uuid:pk>/verwerfen/", views.import_verwerfen, name="import_verwerfen"),
    path("einstellungen/", views.einstellungen, name="einstellungen"),
    path("zusatzfelder/neu/", views.zusatzfeld_bearbeiten, name="zusatzfeld_neu"),
    path("zusatzfelder/<int:pk>/", views.zusatzfeld_bearbeiten, name="zusatzfeld"),
]
