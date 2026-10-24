from django.urls import path

from apps.antraege import views_oeffentlich as views

app_name = "antrag"

urlpatterns = [
    path("", views.start, name="start"),
    path("<str:sprache>/", views.formular, name="formular"),
    path("<str:sprache>/danke/", views.danke, name="danke"),
]
