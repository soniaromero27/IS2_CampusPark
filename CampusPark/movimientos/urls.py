from django.urls import path
from . import views

urlpatterns = [
    path('movimientos/', views.movimientos, name='movimientos'),
]