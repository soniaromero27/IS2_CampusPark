from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from usuarios.decorators import admin_requerido, personal_requerido

from .forms import EspaciosForm, IngresoForm, ReservaForm, ZonaForm
from .models import Espacio, Movimiento, Reserva, TipoEstado, TipoEstadoReserva, Zona
from vehiculos.models import Vehiculo


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
    Alta de una reserva: sólo se pide el día y la hora de entrada (ver
    ReservaForm, que calcula fecha_inicio/fecha_fin), sólo ofrece
    espacios de zonas que el usuario puede usar, y la crea en estado
    'Pendiente'. Si la reserva es para HOY, marca el espacio como
    'Reservado' al toque; si es para un día futuro, lo deja como está
    y lo activa la tarea programada al empezar ese día (ver el comando
    actualizar_estados_espacios).
    """
    usuario = request.user.perfil
    if request.method == "POST":
        form = ReservaForm(request.POST, usuario=usuario)
        if form.is_valid():
            reserva = form.save(commit=False)
            reserva.usuario = usuario
            estado_pendiente, _ = TipoEstadoReserva.objects.get_or_create(
                nombre_estado_reserva="Pendiente"
            )
            reserva.tipo_estado_reserva = estado_pendiente
            reserva.estado_reserva = 1
            reserva.save()

            if timezone.localdate(reserva.fecha_inicio) == timezone.localdate():
                estado_reservado, _ = TipoEstado.objects.get_or_create(nombre_estado="Reservado")
                espacio = reserva.espacio
                espacio.tipo_estado = estado_reservado
                espacio.save()

            return redirect("estacionamiento:reservas_lista")
    else:
        form = ReservaForm(usuario=usuario)
    horas_sugeridas = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]
    return render(
        request,
        "estacionamiento/reserva_form.html",
        {"form": form, "horas_sugeridas": horas_sugeridas},
    )


@login_required
def cancelar_reserva_view(request, pk):
    """Cancela una reserva propia del usuario autenticado y libera el espacio."""
    reserva = get_object_or_404(Reserva, pk=pk, usuario=request.user.perfil)
    if request.method == "POST":
        estado_cancelada, _ = TipoEstadoReserva.objects.get_or_create(
            nombre_estado_reserva="Cancelada"
        )
        reserva.tipo_estado_reserva = estado_cancelada
        reserva.estado_reserva = 0
        reserva.save()

        estado_libre, _ = TipoEstado.objects.get_or_create(nombre_estado="Libre")
        espacio = reserva.espacio
        espacio.tipo_estado = estado_libre
        espacio.save()

        return redirect("estacionamiento:reservas_lista")
    return render(request, "estacionamiento/reserva_cancelar.html", {"reserva": reserva})


@personal_requerido
def lista_todas_reservas_view(request):
    """
    Consultar todas las reservas, de cualquier usuario: sólo Personal
    de Estacionamiento o Administrador.
    """
    reservas = Reserva.objects.select_related(
        "usuario", "espacio", "espacio__zona", "tipo_estado_reserva"
    ).order_by("-fecha_inicio")
    return render(request, "estacionamiento/reservas_lista_todas.html", {"reservas": reservas})


@personal_requerido
def lista_movimientos_view(request):
    """
    Consultar ingresos y salidas: sólo Personal de Estacionamiento o
    Administrador. Muestra TODOS los movimientos, de cualquier usuario.
    Se puede ordenar por cualquier columna, ascendente o descendente,
    con los parámetros GET ?orden=<campo>&dir=<asc|desc>, y buscar con
    ?q=... sobre patente, usuario dueño y zona.
    """
    campos_orden = {
        "vehiculo": ["patente"],
        "usuario": ["vehiculo__usuario__apellido", "vehiculo__usuario__nombre"],
        "zona": ["espacio__zona__nombre"],
        "espacio": ["espacio__numero"],
        "ingreso": ["fecha_hora_ingreso"],
        "salida": ["fecha_hora_salida"],
    }

    orden = request.GET.get("orden", "ingreso")
    if orden not in campos_orden:
        orden = "ingreso"

    direccion = request.GET.get("dir", "desc")
    if direccion not in ("asc", "desc"):
        direccion = "desc"

    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]

    q = request.GET.get("q", "").strip()

    movimientos = Movimiento.objects.select_related(
        "vehiculo", "vehiculo__usuario", "espacio", "espacio__zona"
    )
    if q:
        movimientos = movimientos.filter(
            Q(patente__icontains=q)
            | Q(vehiculo__usuario__nombre__icontains=q)
            | Q(vehiculo__usuario__apellido__icontains=q)
            | Q(espacio__zona__nombre__icontains=q)
        )
    movimientos = movimientos.order_by(*campos)

    return render(
        request,
        "estacionamiento/movimientos_lista.html",
        {"movimientos": movimientos, "orden": orden, "dir": direccion, "q": q},
    )


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
    patentes = Vehiculo.objects.order_by("matricula").values_list("matricula", flat=True)
    return render(
        request,
        "estacionamiento/ingreso_form.html",
        {"form": form, "patentes": patentes},
    )


@personal_requerido
def registrar_salida_view(request, pk):
    """
    Registrar salida de vehículo: sólo Personal de Estacionamiento o
    Administrador. Al confirmar, calcula el monto a cobrar (según la
    tarifa vigente para el tipo de usuario dueño del vehículo, o
    'Externo' si no está registrado) y lo muestra en un recibo.
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

        cobro = movimiento.calcular_cobro()
        return render(
            request, "estacionamiento/salida_recibo.html", {"movimiento": movimiento, "cobro": cobro}
        )

    cobro_estimado = movimiento.calcular_cobro()
    return render(
        request,
        "estacionamiento/salida_confirmar.html",
        {"movimiento": movimiento, "cobro": cobro_estimado},
    )


@admin_requerido
def lista_zonas_view(request):
    """
    Ver todas las zonas y cuántos espacios tiene cada una. Sólo
    Administrador. Admite búsqueda por ?q=... sobre nombre y descripción.
    """
    q = request.GET.get("q", "").strip()
    zonas = Zona.objects.select_related("facultad").annotate(
        cantidad_espacios=Count("espacios")
    ).order_by("nombre")
    if q:
        zonas = zonas.filter(
            Q(nombre__icontains=q) | Q(descripcion__icontains=q) | Q(facultad__nombre__icontains=q)
        )
    return render(request, "estacionamiento/zonas_lista.html", {"zonas": zonas, "q": q})


def _crear_espacios(zona, cantidad):
    """
    Crea 'cantidad' espacios nuevos en 'zona', numerados a partir del
    último número ya usado ahí (o desde 1 si no tiene ninguno). No hace
    nada si cantidad es 0/None. Usado tanto al crear como al editar
    una zona (ZonaForm) y en el alta masiva aparte (EspaciosForm).
    """
    if not cantidad:
        return
    ultimo = Espacio.objects.filter(zona=zona).aggregate(Max("numero"))["numero__max"] or 0
    estado_libre, _ = TipoEstado.objects.get_or_create(nombre_estado="Libre")
    nuevos = [
        Espacio(zona=zona, numero=ultimo + i, tipo_estado=estado_libre)
        for i in range(1, cantidad + 1)
    ]
    Espacio.objects.bulk_create(nuevos)


@admin_requerido
def crear_zona_view(request):
    """Alta manual de una zona, con la opción de crear espacios de una. Sólo Administrador."""
    if request.method == "POST":
        form = ZonaForm(request.POST)
        if form.is_valid():
            zona = form.save()
            _crear_espacios(zona, form.cleaned_data.get("cantidad_espacios"))
            return redirect("estacionamiento:zonas_lista")
    else:
        form = ZonaForm()
    return render(request, "estacionamiento/zona_form.html", {"form": form})


@admin_requerido
def crear_espacios_view(request):
    """
    Alta masiva de espacios dentro de una zona, indicando la cantidad
    a crear. Sólo Administrador.
    """
    if request.method == "POST":
        form = EspaciosForm(request.POST)
        if form.is_valid():
            zona = form.cleaned_data["zona"]
            cantidad = form.cleaned_data["cantidad"]
            numero_inicial = form.cleaned_data["numero_inicial"]

            estado_libre, _ = TipoEstado.objects.get_or_create(nombre_estado="Libre")
            nuevos = [
                Espacio(zona=zona, numero=numero_inicial + i, tipo_estado=estado_libre)
                for i in range(cantidad)
            ]
            Espacio.objects.bulk_create(nuevos)

            return redirect("estacionamiento:zonas_lista")
    else:
        form = EspaciosForm()
    return render(request, "estacionamiento/espacios_form.html", {"form": form})


@admin_requerido
def editar_zona_view(request, pk):
    """
    Modificar una zona existente, incluyendo su facultad. También
    permite crear espacios nuevos de una (ver ZonaForm/_crear_espacios).
    Sólo Administrador.
    """
    zona = get_object_or_404(Zona, pk=pk)
    if request.method == "POST":
        form = ZonaForm(request.POST, instance=zona)
        if form.is_valid():
            zona = form.save()
            _crear_espacios(zona, form.cleaned_data.get("cantidad_espacios"))
            return redirect("estacionamiento:zonas_lista")
    else:
        form = ZonaForm(instance=zona)
    return render(request, "estacionamiento/zona_form.html", {"form": form, "zona": zona})