from django.core.management.base import BaseCommand
from django.utils import timezone

from estacionamiento.models import Espacio, Reserva, TipoEstado


class Command(BaseCommand):
    """
    Tarea programada (correrla una vez al día, al inicio del día, con
    el Programador de tareas de Windows / cron) que:

    1. Activa como 'Reservado' los espacios que tengan una reserva
       vigente para HOY (no cancelada), por si quedaron sin activar
       (por ejemplo si se crearon en un día anterior para este día).
    2. Libera ('Libre') los espacios cuya reserva ya venció (la hora
       de entrada + 30 minutos ya pasó) y nadie registró el ingreso
       -- para no dejar un espacio bloqueado para siempre por un
       usuario que nunca llegó.

    Uso manual: python manage.py actualizar_estados_espacios
    """

    help = (
        "Activa como 'Reservado' los espacios con reserva vigente para hoy, y libera "
        "los que tenían una reserva vencida sin que se haya registrado el ingreso."
    )

    def handle(self, *args, **options):
        ahora = timezone.now()
        hoy = timezone.localdate()
        hoy_inicio = timezone.make_aware(timezone.datetime.combine(hoy, timezone.datetime.min.time()))
        hoy_fin = hoy_inicio + timezone.timedelta(days=1)

        estado_reservado, _ = TipoEstado.objects.get_or_create(nombre_estado="Reservado")
        estado_libre, _ = TipoEstado.objects.get_or_create(nombre_estado="Libre")

        # 1) Activar: reservas de HOY que siguen 'Pendiente' (si ya
        #    están 'Confirmada' o 'Finalizada' no hay que tocarlas -- el
        #    espacio ya está en 'Ocupado' o 'Libre' según corresponda).
        reservas_hoy = (
            Reserva.objects.filter(fecha_inicio__gte=hoy_inicio, fecha_inicio__lt=hoy_fin)
            .exclude(
                tipo_estado_reserva__nombre_estado_reserva__in=[
                    "Cancelada",
                    "Confirmada",
                    "Finalizada",
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

        # 2) Liberar: espacios "Reservado" cuya reserva de hoy ya venció
        #    y nadie tiene un ingreso abierto en ese espacio.
        vencidas = (
            Reserva.objects.filter(
                fecha_fin__lt=ahora,
                espacio__tipo_estado=estado_reservado,
            )
            .exclude(
                tipo_estado_reserva__nombre_estado_reserva__in=[
                    "Cancelada",
                    "Confirmada",
                    "Finalizada",
                ]
            )
            .select_related("espacio")
        )

        liberados = 0
        procesados = set()
        for reserva in vencidas:
            espacio = reserva.espacio
            if espacio.id in procesados:
                continue
            procesados.add(espacio.id)

            tiene_ingreso_abierto = espacio.movimientos.filter(
                fecha_hora_salida__isnull=True
            ).exists()
            if not tiene_ingreso_abierto:
                espacio.tipo_estado = estado_libre
                espacio.save(update_fields=["tipo_estado"])
                liberados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Espacios activados como 'Reservado': {activados}. "
                f"Espacios liberados por reserva vencida sin ingreso: {liberados}."
            )
        )