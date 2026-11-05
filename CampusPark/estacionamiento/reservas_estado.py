from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone


def actualizar_reservas_vencidas():
    """
    Pasa a 'Vencida' las reservas que siguen 'Pendiente' pero cuya hora de
    fin ya es anterior a la hora actual (nadie registró el ingreso), y
    libera el espacio si quedó 'Reservado' por culpa de ellas.

    Un espacio NO se libera si tiene un vehículo adentro o si todavía tiene
    otra reserva pendiente que no terminó, para hoy. Es idempotente: si no
    hay nada para actualizar no toca nada. Devuelve la cantidad de reservas
    actualizadas.
    """
    from .models import Espacio, Reserva, TipoEstado, TipoEstadoReserva

    ahora = timezone.now()
    pendientes_vencidas = list(
        Reserva.objects.filter(
            tipo_estado_reserva__nombre_estado_reserva="Pendiente", fecha_fin__lt=ahora
        ).values_list("pk", "espacio_id")
    )
    if not pendientes_vencidas:
        return 0

    pks = [pk for pk, _ in pendientes_vencidas]
    espacios_ids = {espacio_id for _, espacio_id in pendientes_vencidas}

    with transaction.atomic():
        estado_vencida, _ = TipoEstadoReserva.objects.get_or_create(
            nombre_estado_reserva="Vencida"
        )
        cantidad = Reserva.objects.filter(pk__in=pks).update(tipo_estado_reserva=estado_vencida)

        estado_libre, _ = TipoEstado.objects.get_or_create(nombre_estado="Libre")
        manana = timezone.localdate() + timedelta(days=1)
        fin_del_dia = timezone.make_aware(datetime.combine(manana, time.min))

        for espacio in Espacio.objects.filter(
            pk__in=espacios_ids, tipo_estado__nombre_estado="Reservado"
        ):
            ocupado = espacio.movimientos.filter(fecha_hora_salida__isnull=True).exists()
            otra_pendiente = Reserva.objects.filter(
                espacio=espacio,
                tipo_estado_reserva__nombre_estado_reserva="Pendiente",
                fecha_fin__gte=ahora,
                fecha_inicio__lt=fin_del_dia,
            ).exists()
            if not ocupado and not otra_pendiente:
                espacio.tipo_estado = estado_libre
                espacio.save(update_fields=["tipo_estado"])

    return cantidad


# ======================= estacionamiento/urls.py =======================
# Agregar en urlpatterns:
#     path("reservas/actualizar/", views.actualizar_reservas_view, name="reservas_actualizar"),
#
# ======================= fixtures/tipo_estado_reserva.json (opcional) =======================
# Agregar:  {"model": "estacionamiento.tipoestadoreserva", "pk": 5, "fields": {"nombre_estado_reserva": "Vencida"}}
# (si no, se crea sola la primera vez con get_or_create)