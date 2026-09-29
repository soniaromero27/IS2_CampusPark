import time

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Corre 'actualizar_estados_espacios' en un bucle infinito (dormido
    con time.sleep entre corrida y corrida), sin depender de ningún
    programador de tareas del sistema operativo. Es puro Python, así
    que funciona igual en Windows, Linux o macOS: lo único que cambia
    entre sistemas es cómo dejar el proceso corriendo en segundo plano.

    Uso:
      python manage.py correr_tarea_periodica
      python manage.py correr_tarea_periodica --intervalo 300
    """

    help = (
        "Corre actualizar_estados_espacios cada N segundos (default 900 = 15 min), "
        "en un bucle infinito multiplataforma. Ctrl+C para detener."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--intervalo",
            type=int,
            default=1800,
            help="Segundos entre cada corrida (default: 900 = 15 minutos).",
        )

    def handle(self, *args, **options):
        intervalo = options["intervalo"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Corriendo actualizar_estados_espacios cada {intervalo} segundos. "
                "Dejá esta terminal abierta (o corré el proceso en segundo plano). "
                "Presioná Ctrl+C para detener."
            )
        )
        try:
            while True:
                call_command("actualizar_estados_espacios")
                time.sleep(intervalo)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Detenido."))
