from django.urls import path

from . import views

app_name = "estacionamiento"

urlpatterns = [
    path("reservas/", views.lista_reservas_view, name="reservas_lista"),
    path("reservas/nueva/", views.crear_reserva_view, name="reserva_crear"),
    path("reservas/<int:pk>/cancelar/", views.cancelar_reserva_view, name="reserva_cancelar"),
    
    path("movimientos/", views.lista_movimientos_view, name="movimientos_lista"),
    path("movimientos/ingreso/", views.registrar_ingreso_view, name="movimiento_ingreso"),
    path("movimientos/<int:pk>/salida/", views.registrar_salida_view, name="movimiento_salida"),
]
