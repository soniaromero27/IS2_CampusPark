from django.urls import path

from . import views

app_name = "vehiculos"

urlpatterns = [
    path("", views.lista_vehiculos_view, name="lista"),
    path("agregar/", views.agregar_vehiculo_view, name="agregar"),
    path("todos/", views.lista_todos_vehiculos_view, name="lista_todos"),
]
