from django.urls import path
from . import views

urlpatterns = [
    path('vehiculos/', views.vehiculos, name='vehiculos'),
]