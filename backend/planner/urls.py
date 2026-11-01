from django.urls import path

from planner import views

urlpatterns = [
    path("trip-plan", views.trip_plan, name="trip-plan"),
]
