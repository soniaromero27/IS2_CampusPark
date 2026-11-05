from django.core.management.base import BaseCommand
from django.utils import timezone

from estacionamiento.models import Reserva, TipoEstado
from estacionamiento.reservas_estado import actualizar_reservas_vencidas


class Command(BaseCommand):
    """
    Tarea programada (la corre correr_tarea_periodica, o cron):

    1. Pasa a 'Vencida' las reservas 'Pendiente' cuya hora de fin ya pasó y
       libera sus espacios (ver reservas_estado.actualizar_reservas_vencidas).
       Es el mismo proceso que se dispara al entrar a la lista de reservas
       y con el botón 'Actualizar'.
    2. Activa como 'Reservado' los espacios con una reserva pendiente para HOY.

    Uso manual: python manage.py actualizar_estados_espacios
    """

    help = (
        "Vence las reservas pendientes cuya hora de fin ya pasó (liberando sus espacios) "
        "y activa como 'Reservado' los espacios con reserva pendiente para hoy."
    )

    def handle(self, *args, **options):
        # Primero vencer, para no volver a activar una reserva de hoy que ya terminó.
        vencidas = actualizar_reservas_vencidas()

        hoy = timezone.localdate()
        hoy_inicio = timezone.make_aware(timezone.datetime.combine(hoy, timezone.datetime.min.time()))
        hoy_fin = hoy_inicio + timezone.timedelta(days=1)

        estado_reservado, _ = TipoEstado.objects.get_or_create(nombre_estado="Reservado")

        reservas_hoy = (
            Reserva.objects.filter(fecha_inicio__gte=hoy_inicio, fecha_inicio__lt=hoy_fin)
            .exclude(
                tipo_estado_reserva__nombre_estado_reserva__in=[
                    "Cancelada",
                    "Confirmada",
                    "Finalizada",
                    "Vencida",
                ]
            )
            .select_related("espacio")
        )

        activados = 0
        for reserva in reservas_hoy:
            espacio = reserva.espacio
            if espacio.tipo_estado_id != estado_reservado.id:
                espacio.tipo_estado = estado_reservado
                espacio.save(update_fields=["tipo_estado"])
                activados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Reservas vencidas: {vencidas}. Espacios activados como 'Reservado': {activados}."
            )
        )