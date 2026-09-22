from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .decorators import personal_requerido
from .forms import IngresoForm, ReservaForm
from .models import Movimiento, Reserva, TipoEstado, TipoEstadoReserva


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


@personal_requerido
def lista_movimientos_view(request):
    """
    Consultar ingresos y salidas: sólo Personal de Estacionamiento o
    Administrador. Muestra TODOS los movimientos, de cualquier usuario.
    """
    movimientos = Movimiento.objects.all().select_related(
        "vehiculo", "vehiculo__usuario", "espacio", "espacio__zona"
    ).order_by("-fecha_hora_ingreso")
    return render(request, "estacionamiento/movimientos_lista.html", {"movimientos": movimientos})

'''
@personal_requerido
def registrar_ingreso_view(request):
    """
    Registrar ingreso de vehículo: sólo Personal de Estacionamiento o
    Administrador. Pueden elegir el vehículo de cualquier usuario
    registrado (ver IngresoForm). Crea el Movimiento con la fecha/hora
    actual y marca el espacio elegido como 'Ocupado'.
    """
    if request.method == "POST":
        form = IngresoForm(request.POST)
        if form.is_valid():
            movimiento = form.save(commit=False)
            movimiento.fecha_hora_ingreso = timezone.now()
            movimiento.save()

            estado_ocupado, _ = TipoEstado.objects.get_or_create(nombre_estado="Ocupado")
            espacio = movimiento.espacio
            espacio.tipo_estado = estado_ocupado
            espacio.save()

            return redirect("estacionamiento:movimientos_lista")
    else:
        form = IngresoForm()
    return render(request, "estacionamiento/ingreso_form.html", {"form": form})
'''


@personal_requerido
def registrar_ingreso_view(request):
    """
    Registrar ingreso de vehículo: sólo Personal de Estacionamiento o
    Administrador. Se ingresa únicamente la patente; si coincide con un
    Vehiculo registrado se linkea (y con él su Usuario dueño), y si no,
    el movimiento se crea igual, sin Vehiculo asociado ("Desconocido"),
    sin crear ningún Vehiculo ni Usuario nuevo. Marca el espacio
    elegido como 'Ocupado'.
    """
    if request.method == "POST":
        form = IngresoForm(request.POST)
        if form.is_valid():
            patente = form.cleaned_data["patente"]
            espacio = form.cleaned_data["espacio"]
            vehiculo = Vehiculo.objects.filter(matricula=patente).select_related("usuario").first()
 
            Movimiento.objects.create(
                patente=patente,
                vehiculo=vehiculo,
                espacio=espacio,
                fecha_hora_ingreso=timezone.now(),
            )
 
            estado_ocupado, _ = TipoEstado.objects.get_or_create(nombre_estado="Ocupado")
            espacio.tipo_estado = estado_ocupado
            espacio.save()
 
            return redirect("estacionamiento:movimientos_lista")
    else:
        form = IngresoForm()
    return render(request, "estacionamiento/ingreso_form.html", {"form": form})
 

@personal_requerido
def registrar_salida_view(request, pk):
    """
    Registrar salida de vehículo: sólo Personal de Estacionamiento o
    Administrador. Puede cerrar el movimiento de cualquier usuario
    (mientras siga sin fecha_hora_salida) y libera el espacio.
    """
    movimiento = get_object_or_404(
        Movimiento,
        pk=pk,
        fecha_hora_salida__isnull=True,
    )
    if request.method == "POST":
        movimiento.fecha_hora_salida = timezone.now()
        movimiento.save()

        estado_libre, _ = TipoEstado.objects.get_or_create(nombre_estado="Libre")
        espacio = movimiento.espacio
        espacio.tipo_estado = estado_libre
        espacio.save()

        return redirect("estacionamiento:movimientos_lista")
    return render(request, "estacionamiento/salida_confirmar.html", {"movimiento": movimiento})