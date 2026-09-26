from django.urls import path

from . import views

app_name = "estacionamiento"

urlpatterns = [
    path("reservas/", views.lista_reservas_view, name="reservas_lista"),
    path("reservas/nueva/", views.crear_reserva_view, name="reserva_crear"),
    path("reservas/<int:pk>/cancelar/", views.cancelar_reserva_view, name="reserva_cancelar"),
    path("reservas/todas/", views.lista_todas_reservas_view, name="reservas_lista_todas"),
 
    path("movimientos/", views.lista_movimientos_view, name="movimientos_lista"),
    path("movimientos/ingreso/", views.registrar_ingreso_view, name="movimiento_ingreso"),
    path("movimientos/<int:pk>/salida/", views.registrar_salida_view, name="movimiento_salida"),
    
    path("zonas/", views.lista_zonas_view, name="zonas_lista"),
    path("zonas/nueva/", views.crear_zona_view, name="zona_crear"),
    path("zonas/espacios/nuevos/", views.crear_espacios_view, name="espacios_crear"),
]
