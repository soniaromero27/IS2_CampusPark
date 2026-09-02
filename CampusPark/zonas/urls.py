from django.urls import path
from . import views

urlpatterns = [
    path('zonas/', views.zonas, name='zonas'),
]