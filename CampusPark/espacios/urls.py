from django.urls import path
from . import views

urlpatterns = [
    path('espacios/', views.espacios, name='espacios'),
]