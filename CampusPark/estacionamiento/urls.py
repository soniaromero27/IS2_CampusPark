from django.urls import path

from . import views

app_name = "estacionamiento"

urlpatterns = [
    path("reservas/", views.lista_reservas_view, name="reservas_lista"),
    path("reservas/nueva/", views.crear_reserva_view, name="reserva_crear"),
    path("reservas/<int:pk>/cancelar/", views.cancelar_reserva_view, name="reserva_cancelar"),
]
