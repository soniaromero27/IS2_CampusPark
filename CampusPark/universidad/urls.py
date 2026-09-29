from django.urls import path

from . import views

app_name = "universidad"

urlpatterns = [
    path("facultades/", views.lista_facultades_view, name="facultades_lista"),
    path("facultades/nueva/", views.crear_facultad_view, name="facultad_crear"),
    path("facultades/<int:pk>/editar/", views.editar_facultad_view, name="facultad_editar"),
]