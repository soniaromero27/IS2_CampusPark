from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import personal_requerido

from .forms import TarifaForm
from .models import Tarifa


@personal_requerido
def lista_tarifas_view(request):
    """Ver todas las tarifas: sólo Personal de Estacionamiento o Administrador."""
    tarifas = Tarifa.objects.select_related("tipo").order_by("-vigencia", "tipo__nombre")
    return render(request, "reglas/tarifas_lista.html", {"tarifas": tarifas})


@personal_requerido
def crear_tarifa_view(request):
    """Alta de una nueva tarifa: sólo Personal de Estacionamiento o Administrador."""
    if request.method == "POST":
        form = TarifaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("reglas:tarifas_lista")
    else:
        form = TarifaForm()
    return render(request, "reglas/tarifa_form.html", {"form": form, "modo": "crear"})


@personal_requerido
def editar_tarifa_view(request, pk):
    """Modificar una tarifa existente: sólo Personal de Estacionamiento o Administrador."""
    tarifa = get_object_or_404(Tarifa, pk=pk)
    if request.method == "POST":
        form = TarifaForm(request.POST, instance=tarifa)
        if form.is_valid():
            form.save()
            return redirect("reglas:tarifas_lista")
    else:
        form = TarifaForm(instance=tarifa)
    return render(
        request, "reglas/tarifa_form.html", {"form": form, "modo": "editar", "tarifa": tarifa}
    )
