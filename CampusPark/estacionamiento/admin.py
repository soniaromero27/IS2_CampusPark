from django.contrib import admin

from .models import Espacio, Movimiento, Reserva, TipoEstado, TipoEstadoReserva, Zona, Ticket


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre", "descripcion")


@admin.register(TipoEstado)
class TipoEstadoAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre_estado")


@admin.register(Espacio)
class EspacioAdmin(admin.ModelAdmin):
    list_display = ("id", "zona", "numero", "tipo_estado")
    list_filter = ("zona", "tipo_estado")


@admin.register(TipoEstadoReserva)
class TipoEstadoReservaAdmin(admin.ModelAdmin):
    list_display = ("id", "nombre_estado_reserva")


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "espacio", "fecha_inicio", "fecha_fin", "tipo_estado_reserva")
    list_filter = ("tipo_estado_reserva",)


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ("id", "vehiculo", "espacio", "fecha_hora_ingreso", "fecha_hora_salida")
    list_filter = ("espacio",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "patente", "usuario", "horas", "monto", "estado", "fecha_emision")
    list_filter = ("estado", "metodo_pago")
    search_fields = ("patente", "usuario__nombre", "usuario__apellido")
 