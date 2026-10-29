from django.urls import path

from apps.tickets import views

app_name = "tickets"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.neu, name="neu"),
    path("<int:pk>/", views.ticket, name="ticket"),
    path("<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("anhang/<int:pk>/", views.anhang, name="anhang"),
    path("kategorien/", views.kategorien, name="kategorien"),
    path("kategorien/neu/", views.kategorie, name="kategorie_neu"),
    path("kategorien/<int:pk>/", views.kategorie, name="kategorie"),
]
