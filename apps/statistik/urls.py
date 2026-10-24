from django.urls import path

from apps.statistik import views

app_name = "statistik"

urlpatterns = [path("", views.uebersicht, name="uebersicht")]
