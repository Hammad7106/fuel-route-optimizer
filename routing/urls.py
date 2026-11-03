from django.urls import path

from . import views

app_name = "routing"

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("route/", views.TripPlanView.as_view(), name="route"),
    path("route/map/", views.TripMapView.as_view(), name="route-map"),
]
