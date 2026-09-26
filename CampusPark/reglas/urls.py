from django.urls import path

from . import views

app_name = "reglas"

urlpatterns = [
    path("", views.lista_tarifas_view, name="tarifas_lista"),
    path("nueva/", views.crear_tarifa_view, name="tarifa_crear"),
    path("<int:pk>/editar/", views.editar_tarifa_view, name="tarifa_editar"),
]
