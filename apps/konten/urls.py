from django.urls import path

from apps.konten import views

app_name = "konten"

urlpatterns = [
    path("anmelden/", views.anmelden, name="anmelden"),
    path("abmelden/", views.abmelden, name="abmelden"),
    path("", views.mein_konto, name="mein_konto"),
    path("zwei-faktor/einrichten/", views.zwei_faktor_einrichten, name="zwei_faktor_einrichten"),
    path("zwei-faktor/notfallcodes/", views.notfallcodes_neu, name="notfallcodes_neu"),
    path("zwei-faktor/abschalten/", views.zwei_faktor_abschalten, name="zwei_faktor_abschalten"),
]
