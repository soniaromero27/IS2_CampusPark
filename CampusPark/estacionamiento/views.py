from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ReservaForm
from .models import Reserva, TipoEstadoReserva


@login_required
def lista_reservas_view(request):
    """Consulta de las reservas del usuario autenticado."""
    reservas = Reserva.objects.filter(
        usuario=request.user.perfil
    ).select_related("espacio", "espacio__zona", "tipo_estado_reserva").order_by("-fecha_inicio")
    return render(request, "estacionamiento/reservas_lista.html", {"reservas": reservas})


@login_required
def crear_reserva_view(request):
    """
    Alta de una reserva: valida solapamiento de fechas para el mismo
    espacio (ver ReservaForm) y la crea en estado 'Pendiente'.
    """
    if request.method == "POST":
        form = ReservaForm(request.POST)
        if form.is_valid():
            reserva = form.save(commit=False)
            reserva.usuario = request.user.perfil
            estado_pendiente, _ = TipoEstadoReserva.objects.get_or_create(
                nombre_estado_reserva="Pendiente"
            )
            reserva.tipo_estado_reserva = estado_pendiente
            reserva.estado_reserva = 1
            reserva.save()
            return redirect("estacionamiento:reservas_lista")
    else:
        form = ReservaForm()
    return render(request, "estacionamiento/reserva_form.html", {"form": form})


@login_required
def cancelar_reserva_view(request, pk):
    """Cancela una reserva propia del usuario autenticado."""
    reserva = get_object_or_404(Reserva, pk=pk, usuario=request.user.perfil)
    if request.method == "POST":
        estado_cancelada, _ = TipoEstadoReserva.objects.get_or_create(
            nombre_estado_reserva="Cancelada"
        )
        reserva.tipo_estado_reserva = estado_cancelada
        reserva.estado_reserva = 0
        reserva.save()
        return redirect("estacionamiento:reservas_lista")
    return render(request, "estacionamiento/reserva_cancelar.html", {"reserva": reserva})
