from django.shortcuts import render

from reglas.models import Reglamento


def inicio_view(request):
    """
    Página de inicio (pública): presenta CampusPark y sus funcionalidades.
    Es la página a la que lleva el logo "P" del encabezado. Muestra el
    horario del estacionamiento si ya se cargó el reglamento.
    """
    return render(request, "inicio.html", {"reglamento": Reglamento.objects.first()})
