from django.urls import path

from apps.wetter import views

app_name = "wetter"

urlpatterns = [
    path("kopf/", views.kopf, name="kopf"),
]
