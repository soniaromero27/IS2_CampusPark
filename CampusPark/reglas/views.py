from datetime import time

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from campuspark.paginacion import paginar

from usuarios.decorators import admin_requerido, personal_requerido
from usuarios.models import TipoUsuario

from .forms import HorariosForm, ReglamentoTextoForm, TarifaForm
from .models import Reglamento, Tarifa


@personal_requerido
def lista_tarifas_view(request):
    """
    Ver todas las tarifas: sólo Personal de Estacionamiento o
    Administrador. Se puede filtrar por el tipo de usuario al que
    afectan con ?tipo=<id>.
    """
    campos_orden = {
        "descripcion": ["descripcion"],
        "tipo": ["tipo"],
        "valor_hora": ["valor_por_hora"],
        "vigencia": ["vigencia"],
    }

    orden = request.GET.get("orden", "vigencia")
    if orden not in campos_orden:
        orden = "vigencia"

    direccion = request.GET.get("dir", "desc")
    if direccion not in ("asc", "desc"):
        direccion = "desc"

    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]
    
    tipos = TipoUsuario.objects.order_by("nombre")
    tipo_id = request.GET.get("tipo", "").strip()

    tarifas = Tarifa.objects.select_related("tipo").order_by("-vigencia", "tipo__nombre")
    if tipo_id:
        tarifas = tarifas.filter(tipo_id=tipo_id)

    tarifas = tarifas.order_by(*campos)

    return render(
        request,
        "reglas/tarifas_lista.html",
        {**paginar(request, tarifas, "tarifas"), "tipos": tipos, "tipo_id": tipo_id, "orden": orden, "dir": direccion},
    )


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


@login_required
def ver_reglamento_view(request):
    """Ver el reglamento (único): cualquier usuario logueado puede verlo."""
    reglamento = Reglamento.objects.first()
    return render(request, "reglas/reglamento_lista.html", {"reglamento": reglamento})


def _reglamento_unico():
    """
    El reglamento (único). Si todavía no existe, devuelve una instancia
    SIN guardar, con el horario inicial 07:00-22:00: el primer guardado
    (sea del texto o de los horarios) la crea; de ahí en adelante sólo
    se modifica ese mismo registro, nunca se crea un segundo.
    """
    return Reglamento.objects.first() or Reglamento(
        hora_apertura=time(7, 0), hora_cierre=time(22, 0)
    )


@admin_requerido
def editar_reglamento_view(request):
    """Editar el texto del reglamento: sólo Administrador."""
    reglamento = _reglamento_unico()
    if request.method == "POST":
        form = ReglamentoTextoForm(request.POST, instance=reglamento)
        if form.is_valid():
            form.save()
            return redirect("reglas:reglamento")
    else:
        form = ReglamentoTextoForm(instance=reglamento)
    return render(
        request, "reglas/reglamento_form.html", {"form": form, "titulo": "Editar reglamento"}
    )


@admin_requerido
def editar_horarios_view(request):
    """Editar la hora de apertura y de cierre: sólo Administrador."""
    reglamento = _reglamento_unico()
    if request.method == "POST":
        form = HorariosForm(request.POST, instance=reglamento)
        if form.is_valid():
            form.save()
            return redirect("reglas:reglamento")
    else:
        form = HorariosForm(instance=reglamento)
    return render(
        request, "reglas/reglamento_form.html", {"form": form, "titulo": "Editar horarios"}
    )