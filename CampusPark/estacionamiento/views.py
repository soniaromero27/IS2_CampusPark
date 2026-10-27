from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Prefetch, Q, Count, Sum, F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.functions import TruncDate, TruncHour, TruncMonth

import datetime as dt 

from reglas.models import Reglamento
from campuspark.paginacion import paginar

from usuarios.decorators import admin_requerido, personal_requerido

from .forms import EspacioForm, EspaciosForm, IngresoForm, ReservaForm, ZonaForm, TicketPagoForm
from .models import Espacio, Movimiento, Reserva, TipoEstado, TipoEstadoReserva, Zona, Ticket, Pago


from vehiculos.models import Vehiculo

from .cuadricula import contexto_cuadricula

@login_required
def lista_reservas_view(request):
    """
    Consulta de las reservas del usuario autenticado. Se puede ordenar
    por cualquier columna, ascendente o descendente, con los parámetros
    GET ?orden=<campo>&dir=<asc|desc>, buscar con ?q=... sobre zona y
    estado, y filtrar por rango de fechas (sobre el día de la reserva)
    con ?desde=AAAA-MM-DD y/o ?hasta=AAAA-MM-DD.
    """
    campos_orden = {
        "zona": ["espacio__zona__nombre"],
        "espacio": ["espacio__numero"],
        "desde": ["fecha_inicio"],
        "hasta": ["fecha_fin"],
        "estado": ["tipo_estado_reserva__nombre_estado_reserva"],
    }

    orden = request.GET.get("orden", "desde")
    if orden not in campos_orden:
        orden = "desde"

    direccion = request.GET.get("dir", "desc")
    if direccion not in ("asc", "desc"):
        direccion = "desc"

    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]

    q = request.GET.get("q", "").strip()
    desde = request.GET.get("desde", "").strip()
    hasta = request.GET.get("hasta", "").strip()

    reservas = Reserva.objects.filter(usuario=request.user.perfil).select_related(
        "espacio", "espacio__zona", "tipo_estado_reserva"
    )
    if q:
        reservas = reservas.filter(
            Q(espacio__zona__nombre__icontains=q)
            | Q(tipo_estado_reserva__nombre_estado_reserva__icontains=q)
        )
    if desde:
        reservas = reservas.filter(fecha_inicio__date__gte=desde)
    if hasta:
        reservas = reservas.filter(fecha_inicio__date__lte=hasta)
    reservas = reservas.order_by(*campos)

    return render(
        request,
        "estacionamiento/reservas_lista.html",
        {
            **paginar(request, reservas, "reservas"),
            "orden": orden,
            "dir": direccion,
            "q": q,
            "desde": desde,
            "hasta": hasta,
        },
    )


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
    reglamento = Reglamento.objects.first()
    if reglamento:
        apertura = reglamento.hora_apertura.strftime("%H:%M")
        cierre = reglamento.hora_cierre.strftime("%H:%M")
        horas_sugeridas = [h for h in horas_sugeridas if apertura <= h <= cierre]
    return render(
        request,
        "estacionamiento/reserva_form.html",
        {"form": form, "horas_sugeridas": horas_sugeridas, **contexto_cuadricula(form.fields["espacio"].queryset)}
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
    de Estacionamiento o Administrador. Se puede ordenar por cualquier
    columna, ascendente o descendente, con ?orden=<campo>&dir=<asc|desc>,
    buscar con ?q=... sobre nombre, apellido y documento del usuario,
    zona y estado, y filtrar por rango de fechas (sobre el día de la
    reserva) con ?desde=AAAA-MM-DD y/o ?hasta=AAAA-MM-DD.
    """
    campos_orden = {
        "usuario": ["usuario__apellido", "usuario__nombre"],
        "zona": ["espacio__zona__nombre"],
        "espacio": ["espacio__numero"],
        "desde": ["fecha_inicio"],
        "hasta": ["fecha_fin"],
        "estado": ["tipo_estado_reserva__nombre_estado_reserva"],
    }

    orden = request.GET.get("orden", "desde")
    if orden not in campos_orden:
        orden = "desde"

    direccion = request.GET.get("dir", "desc")
    if direccion not in ("asc", "desc"):
        direccion = "desc"

    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]

    q = request.GET.get("q", "").strip()
    desde = request.GET.get("desde", "").strip()
    hasta = request.GET.get("hasta", "").strip()

    reservas = Reserva.objects.select_related(
        "usuario", "espacio", "espacio__zona", "tipo_estado_reserva"
    )
    if q:
        reservas = reservas.filter(
            Q(usuario__nombre__icontains=q)
            | Q(usuario__apellido__icontains=q)
            | Q(usuario__documento__icontains=q)
            | Q(espacio__zona__nombre__icontains=q)
            | Q(tipo_estado_reserva__nombre_estado_reserva__icontains=q)
        )
    if desde:
        reservas = reservas.filter(fecha_inicio__date__gte=desde)
    if hasta:
        reservas = reservas.filter(fecha_inicio__date__lte=hasta)
    reservas = reservas.order_by(*campos)

    return render(
        request,
        "estacionamiento/reservas_lista_todas.html",
        {
            **paginar(request, reservas, "reservas"),
            "orden": orden,
            "dir": direccion,
            "q": q,
            "desde": desde,
            "hasta": hasta,
        },
    )


@login_required
def lista_espacios_view(request):
    """
    Ver todos los espacios, con su número, zona, facultad de esa zona
    (o 'Ninguna' si es pública) y estado, y (si está Ocupado) la
    patente del vehículo estacionado ahí. Sólo Personal de
    Estacionamiento o Administrador. Se puede ordenar con
    ?orden=<campo>&dir=<asc|desc> y buscar con ?q=... sobre zona,
    facultad, estado y la patente del vehículo estacionado.

    Se muestra en dos vistas, a elección con ?vista=lista|cuadros: una
    tabla, o una lista de zonas desplegables que, al abrirse, muestran
    sus espacios como cuadros coloreados según el estado (como el mapa
    de butacas de una sala de cine). En la vista de cuadros el orden es
    siempre por zona y número. Las zonas se abren con ?abrir=<id de
    zona> (se repite el parámetro para abrir varias) y todas se abren
    si hay una búsqueda activa.
    """
    campos_orden = {
        "numero": ["numero"],
        "zona": ["zona__nombre", "numero"],
        "facultad": ["zona__facultad__nombre", "zona__nombre", "numero"],
        "estado": ["tipo_estado__nombre_estado", "zona__nombre", "numero"],
    }

    orden = request.GET.get("orden", "zona")
    if orden not in campos_orden:
        orden = "zona"

    direccion = request.GET.get("dir", "asc")
    if direccion not in ("asc", "desc"):
        direccion = "asc"

    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]

    vista = request.GET.get("vista", "lista")
    if vista not in ("lista", "cuadros"):
        vista = "lista"
    if vista == "cuadros":
        campos = ["zona__nombre", "numero"]
    
    perfil = getattr(request.user, "perfil", None)
    
    ver_patentes = bool(perfil and perfil.es_personal)

    movimientos_abiertos = (
        Movimiento.objects.filter(fecha_hora_salida__isnull=True)
        if ver_patentes else Movimiento.objects.none()
    )
    
    q = request.GET.get("q", "").strip()

    espacios = Espacio.objects.select_related(
        "zona", "zona__facultad", "tipo_estado"
    ).prefetch_related(
        Prefetch(
            "movimientos",
            queryset=Movimiento.objects.filter(fecha_hora_salida__isnull=True),
            to_attr="movimientos_abiertos",
        )
    )
    if q:
        filtro = (Q(zona__nombre__icontains=q)
                  | Q(zona__facultad__nombre__icontains=q)
                  | Q(tipo_estado__nombre_estado__icontains=q))
        if ver_patentes:
            filtro |= Q(movimientos__patente__icontains=q,
                        movimientos__fecha_hora_salida__isnull=True)
        espacios = espacios.filter(filtro).distinct()
        
    espacios = espacios.order_by(*campos)

    grupos = []
    if vista == "cuadros":
        espacios_por_zona = defaultdict(list)
        for e in espacios:
            espacios_por_zona[e.zona_id].append(e)

        zonas = Zona.objects.select_related("facultad").order_by("nombre")
        if q:
            # Con una búsqueda activa, sólo las zonas que tienen resultados.
            zonas = zonas.filter(id__in=espacios_por_zona.keys())
        for zona in zonas:
            items = espacios_por_zona.get(zona.id, [])
            grupos.append(
                {
                    "zona": zona,
                    "espacios": items,
                    "total": len(items),
                    "libres": sum(
                        1 for e in items if e.tipo_estado.nombre_estado == "Libre"
                    ),
                }
            )

    abiertas = [int(v) for v in request.GET.getlist("abrir") if v.isdigit()]
    params = request.GET.copy()
    params.pop("abrir", None)
    
    if vista == "cuadros":
        paginacion = paginar(request, grupos, "grupos")
    else:
        paginacion = paginar(request, espacios, "espacios")
        
    return render(
        request,
        "estacionamiento/espacios_lista.html",
        {
            **paginacion,
            "vista": vista,
            "orden": orden,
            "dir": direccion,
            "q": q,
            "abiertas": abiertas,
            "querystring": params.urlencode(),
        },
    )


@admin_requerido
def editar_espacio_view(request, pk):
    """
    Editar un espacio a mano (zona, número y estado). Sólo
    Administrador. Al guardar vuelve a la lista de espacios con los
    mismos parámetros (vista, búsqueda y orden) con los que se entró.
    """
    espacio = get_object_or_404(
        Espacio.objects.select_related("zona", "tipo_estado"), pk=pk
    )
    titulo_espacio = str(espacio)  # antes de que el form pise el objeto con valores inválidos
    volver = reverse("estacionamiento:espacios_lista")
    querystring = request.GET.urlencode()
    if querystring:
        volver += "?" + querystring

    if request.method == "POST":
        form = EspacioForm(request.POST, instance=espacio)
        if form.is_valid():
            form.save()
            return redirect(volver)
    else:
        form = EspacioForm(instance=espacio)
    return render(
        request,
        "estacionamiento/espacio_editar.html",
        {"form": form, "titulo_espacio": titulo_espacio, "volver": volver},
    )


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
        "estacionamiento/movimientos_lista.html",{
        **paginar(request, movimientos, "movimientos"),
        "orden": orden,
        "dir": direccion,
        "q": q
        },
    )


@personal_requerido
def registrar_ingreso_view(request):
    """
    Registrar ingreso de vehículo: sólo Personal de Estacionamiento o
    Administrador. Se ingresa únicamente la patente; si coincide con un
    Vehiculo registrado se linkea (y con él su Usuario dueño), y si no,
    el movimiento se crea igual, sin Vehiculo asociado ("No registrado"),
    sin crear ningún Vehiculo ni Usuario nuevo.

    Si el dueño tiene una reserva vigente ahora mismo, IngresoForm ya
    resolvió el espacio como el reservado (ver form.reserva_activa) o,
    si ese espacio estaba ocupado, por otro libre de la misma zona (ver
    form.reasignado/form.espacio_original); acá sólo falta marcar esa
    reserva como 'Confirmada' (actualizando su espacio si hubo
    reasignación) y avisar del cambio. En cualquier caso, marca el
    espacio final como 'Ocupado'.
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

            if form.reserva_activa:
                estado_confirmada, _ = TipoEstadoReserva.objects.get_or_create(
                    nombre_estado_reserva="Confirmada"
                )
                reserva = form.reserva_activa
                reserva.tipo_estado_reserva = estado_confirmada
                reserva.estado_reserva = 2
                if form.reasignado:
                    reserva.espacio = espacio
                reserva.save()

                if form.reasignado:
                    if form.cambio_de_zona:
                        messages.warning(
                            request,
                            f"{patente} tenía reservado el espacio N°{form.espacio_original.numero} "
                            f"de la zona '{form.espacio_original.zona}', pero estaba ocupado y no "
                            f"había otro libre ahí: se lo asignó al espacio N°{espacio.numero} de "
                            f"la zona '{espacio.zona}'.",
                        )
                    else:
                        messages.warning(
                            request,
                            f"{patente} tenía reservado el espacio N°{form.espacio_original.numero} "
                            f"de la zona '{espacio.zona}', pero estaba ocupado: se lo reasignó al "
                            f"espacio N°{espacio.numero} de la misma zona.",
                        )
                else:
                    messages.success(
                        request,
                        f"{patente} tenía una reserva vigente: se lo asignó automáticamente a "
                        f"la zona '{espacio.zona}', espacio N°{espacio.numero}.",
                    )

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
    Registrar salida: sólo Personal o Administrador. Si el ticket está
    validado y dentro de la tolerancia, no se recalcula nada. Si no, se
    cobra sólo el excedente de lo que el usuario ya pagó (ver
    Movimiento.cobro_vigente). Emite el ticket de salida.
    """
    movimiento = get_object_or_404(Movimiento, pk=pk, fecha_hora_salida__isnull=True)
    if request.method == "POST":
        with transaction.atomic():
            # bloqueo: evita que el usuario valide/pague a la vez que se registra la salida
            movimiento = get_object_or_404(
                Movimiento.objects.select_for_update(of=("self",)),
                pk=pk, fecha_hora_salida__isnull=True,
            )
            movimiento.fecha_hora_salida = timezone.now()
            movimiento.save()
 
            estado_libre, _ = TipoEstado.objects.get_or_create(nombre_estado="Libre")
            espacio = movimiento.espacio
            espacio.tipo_estado = estado_libre
            espacio.save()
 
            if movimiento.vehiculo_id and movimiento.vehiculo.usuario_id:
                reserva_en_curso = Reserva.objects.filter(
                    espacio=espacio,
                    usuario=movimiento.vehiculo.usuario,
                    tipo_estado_reserva__nombre_estado_reserva="Confirmada",
                ).first()
                if reserva_en_curso:
                    estado_finalizada, _ = TipoEstadoReserva.objects.get_or_create(
                        nombre_estado_reserva="Finalizada"
                    )
                    reserva_en_curso.tipo_estado_reserva = estado_finalizada
                    reserva_en_curso.save()
 
            cuenta = movimiento.cobro_vigente()
            ticket = Ticket.emitir(movimiento, cuenta, validado_por=request.user.perfil)
 
        return render(
            request,
            "estacionamiento/salida_recibo.html",
            {"movimiento": movimiento, "cuenta": cuenta, "ticket": ticket},
        )
 
    return render(
        request,
        "estacionamiento/salida_confirmar.html",
        {"movimiento": movimiento, "cuenta": movimiento.cobro_vigente()},
    )
 

@admin_requerido
def lista_zonas_view(request):
    """
    Ver todas las zonas y cuántos espacios tiene cada una. Sólo
    Administrador. Admite búsqueda por ?q=... sobre nombre y descripción.
    """
    campos_orden = {
        "nombre": ["nombre"],
        "facultad": ["facultad"],
        "tipos": ["tipos_usuario_permitidos"],
        "descripcion": ["descripcion"],
        "espacios": ["cantidad_espacios"],
    }
    
    orden = request.GET.get("orden", "nombre")
    if orden not in campos_orden:
        orden = "nombre"

    direccion = request.GET.get("dir", "desc")
    if direccion not in ("asc", "desc"):
        direccion = "desc"

    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]
        
        
    q = request.GET.get("q", "").strip()
    zonas = (
        Zona.objects.select_related("facultad")
        .prefetch_related("tipos_usuario_permitidos")
        .annotate(cantidad_espacios=Count("espacios"))
        .order_by("nombre")
    )
    if q:
        zonas = zonas.filter(
            Q(nombre__icontains=q) | Q(descripcion__icontains=q) | Q(facultad__nombre__icontains=q)
        )
        
    zonas = zonas.order_by(*campos)
     
    return render(
        request, 
        "estacionamiento/zonas_lista.html", 
        {
            **paginar(request, zonas, "zonas"), 
            "orden": orden,
            "dir": direccion,
            "q": q
        },
    )


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
    a crear. Sólo Administrador. Vuelve a la lista de espacios si se
    entró desde ahí (?desde=espacios), y a la de zonas en otro caso.
    """
    destino = (
        "estacionamiento:espacios_lista"
        if request.GET.get("desde") == "espacios"
        else "estacionamiento:zonas_lista"
    )
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

            return redirect(destino)
    else:
        form = EspaciosForm()
    return render(
        request,
        "estacionamiento/espacios_form.html",
        {"form": form, "volver_url": reverse(destino)},
    )


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
    
@login_required
def mis_movimientos_view(request):
    """
    Ingresos y salidas de los vehículos del usuario autenticado. Se puede
    ordenar con ?orden=<campo>&dir=<asc|desc> y buscar con ?q=... sobre
    patente y zona.
    """
    campos_orden = {
        "vehiculo": ["patente"],
        "zona": ["espacio__zona__nombre"],
        "espacio": ["espacio__numero"],
        "ingreso": ["fecha_hora_ingreso"],
        "salida": ["fecha_hora_salida"],
        "ticket": ["ticket__estado"],
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
 
    movimientos = Movimiento.objects.filter(
        vehiculo__usuario=request.user.perfil
    ).select_related("vehiculo", "espacio", "espacio__zona", "ticket")
    if q:
        movimientos = movimientos.filter(
            Q(patente__icontains=q) | Q(espacio__zona__nombre__icontains=q)
        )
    movimientos = movimientos.order_by(*campos)
 
    return render(
        request,
        "estacionamiento/mis_movimientos.html",
        {"movimientos": movimientos, "orden": orden, "dir": direccion, "q": q},
    )
 
@personal_requerido
def lista_tickets_view(request):
    """Todos los tickets. Filtros: ?estado=pendiente|pagado|sin_tarifa y ?q=..."""
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
 
    tickets = Ticket.objects.select_related("usuario")
    if estado in Ticket.Estado.values:
        tickets = tickets.filter(estado=estado)
    if q:
        tickets = tickets.filter(
            Q(patente__icontains=q)
            | Q(usuario__nombre__icontains=q)
            | Q(usuario__apellido__icontains=q)
            | Q(usuario__documento__icontains=q)
        )
    return render(
        request,
        "estacionamiento/tickets_lista.html",
        {"tickets": tickets, "q": q, "estado": estado, "estados": Ticket.Estado.choices},
    )
 
 
@login_required
def detalle_ticket_view(request, pk):
    """Ticket: lo ve su dueño o el personal/administrador."""
    ticket = get_object_or_404(
        Ticket.objects.select_related(
            "usuario", "movimiento__espacio__zona", "cobrado_por"
        ),
        pk=pk,
    )
    perfil = request.user.perfil
    if not (perfil.es_personal or ticket.usuario_id == perfil.pk):
        raise PermissionDenied("Este ticket no te pertenece.")
    return render(
        request,
        "estacionamiento/ticket_detalle.html",
        {"ticket": ticket, "form": TicketPagoForm()},
    )
 
 
@personal_requerido
def pagar_ticket_view(request, pk):
    """Registrar el pago de un ticket pendiente. Sólo POST."""
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST":
        form = TicketPagoForm(request.POST)
        if form.is_valid():
            if ticket.estado == Ticket.Estado.PENDIENTE:
                ticket.registrar_pago(form.cleaned_data["metodo"], request.user.perfil)
                messages.success(request, f"Pago del ticket {ticket.numero} registrado.")
            else:
                messages.warning(request, "Este ticket no está pendiente de pago.")
    return redirect("estacionamiento:ticket_detalle", pk=pk)
 


def _rango_periodo(periodo, dia, mes, anio):
    """(inicio, fin) como fechas, con 'fin' exclusivo. ValueError si el valor es inválido."""
    if periodo == "dia":
        d = dt.date.fromisoformat(dia)
        return d, d + dt.timedelta(days=1)
    if periodo == "mes":
        y, m = (int(x) for x in mes.split("-"))
        inicio = dt.date(y, m, 1)
        fin = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
        return inicio, fin
    y = int(anio)
    return dt.date(y, 1, 1), dt.date(y + 1, 1, 1)
 
 
@admin_requerido
def dashboard_view(request):
    """
    Resumen de recaudación (sólo Administrador). Cuenta los tickets PAGADOS
    según su fecha de pago. Filtrable por día, mes o año:
    ?periodo=dia&dia=AAAA-MM-DD | ?periodo=mes&mes=AAAA-MM | ?periodo=anio&anio=AAAA
    """
    hoy = timezone.localdate()
    periodo = request.GET.get("periodo", "mes")
    if periodo not in ("dia", "mes", "anio"):
        periodo = "mes"
    dia = request.GET.get("dia") or hoy.isoformat()
    mes = request.GET.get("mes") or hoy.strftime("%Y-%m")
    anio = request.GET.get("anio") or str(hoy.year)
 
    try:
        inicio_d, fin_d = _rango_periodo(periodo, dia, mes, anio)
    except ValueError:
        messages.error(request, "Fecha inválida: se muestra el mes actual.")
        periodo, dia, mes, anio = "mes", hoy.isoformat(), hoy.strftime("%Y-%m"), str(hoy.year)
        inicio_d, fin_d = _rango_periodo(periodo, dia, mes, anio)
 
    inicio = timezone.make_aware(dt.datetime.combine(inicio_d, dt.time.min))
    fin = timezone.make_aware(dt.datetime.combine(fin_d, dt.time.min))
 
    pagados = Pago.objects.filter(fecha_pago__gte=inicio, fecha_pago__lt=fin)
 
    resumen = pagados.aggregate(total=Sum("monto"), cantidad=Count("id"))
    total = resumen["total"] or 0
 
    # Por forma de pago (se muestran las tres aunque alguna esté en cero)
    agg = {
       r["metodo"]: r
       for r in pagados.values("metodo").annotate(total=Sum("monto"), cantidad=Count("id"))
    }

    por_metodo = []
    for valor, etiqueta in Ticket.Metodo.choices:
        r = agg.get(valor, {})
        t = r.get("total") or 0
        por_metodo.append(
            {
                "etiqueta": etiqueta,
                "total": t,
                "cantidad": r.get("cantidad", 0),
                "pct": round(t * 100 / total) if total else 0,
            }
        )
 
    # Evolución: por hora (día), por día (mes) o por mes (año)
    trunc = {"dia": TruncHour, "mes": TruncDate, "anio": TruncMonth}[periodo]
    serie = list(
        pagados.annotate(p=trunc("fecha_pago"))
        .values("p")
        .annotate(total=Sum("monto"), cantidad=Count("id"))
        .order_by("p")
    )
    maximo = max((s["total"] or 0 for s in serie), default=0)
    for s in serie:
        s["pct"] = round((s["total"] or 0) * 100 / maximo) if maximo else 0
 
    # Lo emitido en el período que todavía no se cobró
    por_cobrar = Ticket.objects.filter(
       estado=Ticket.Estado.PENDIENTE, fecha_emision__gte=inicio, fecha_emision__lt=fin
    ).aggregate(total=Sum(F("monto") - F("monto_pagado_previo")), cantidad=Count("id"))

    sin_cargo = Ticket.objects.filter(
        estado=Ticket.Estado.SIN_CARGO, fecha_pago__gte=inicio, fecha_pago__lt=fin
    ).count()
    
    return render(
        request,
        "estacionamiento/dashboard.html",
        {
            "periodo": periodo,
            "dia": dia,
            "mes": mes,
            "anio": anio,
            "rango_texto": {
                "dia": inicio_d.strftime("%d/%m/%Y"),
                "mes": inicio_d.strftime("%m/%Y"),
                "anio": str(inicio_d.year),
            }[periodo],
            "formato_serie": {"dia": "H:i", "mes": "d/m/Y", "anio": "m/Y"}[periodo],
            "total": total,
            "cantidad": resumen["cantidad"],
            "por_metodo": por_metodo,
            "serie": serie,
            "por_cobrar": por_cobrar,
            "sin_cargo": sin_cargo,
        },
    )


def _abiertos_del_usuario(perfil):
    return Movimiento.objects.filter(
        vehiculo__usuario=perfil, fecha_hora_salida__isnull=True
    ).select_related("espacio", "espacio__zona", "vehiculo", "vehiculo__usuario__tipo")
 
 
@login_required
def pagar_tickets_view(request):
    """Botón 'Pagar Tickets' del encabezado: vehículos propios que están dentro ahora."""
    items = [
        {"movimiento": m, "cuenta": m.cobro_vigente()}
        for m in _abiertos_del_usuario(request.user.perfil).order_by("-fecha_hora_ingreso")
    ]
    return render(
        request,
        "estacionamiento/pagar_tickets.html",
        {"items": items, "tolerancia": Reglamento.tolerancia_actual()},
    )
 
 
@login_required
def validar_ticket_view(request, pk):
    """
    El usuario valida y paga su propio ticket ANTES de salir. Paga sólo lo
    que falta (excedente de lo ya pagado) y queda con la tolerancia del
    Reglamento para salir sin recálculo.
    """
    perfil = request.user.perfil
    movimiento = get_object_or_404(
        _abiertos_del_usuario(perfil), pk=pk
    )
    tolerancia = Reglamento.tolerancia_actual()
 
    if request.method == "POST":
        form = TicketPagoForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    bloqueado = get_object_or_404(
                        Movimiento.objects.select_for_update(of=("self",)),
                        pk=pk, vehiculo__usuario=perfil, fecha_hora_salida__isnull=True,
                    )
                    cobrado = bloqueado.validar(form.cleaned_data["metodo"], perfil)
                hasta = timezone.localtime(bloqueado.validado_hasta)
                messages.success(
                    request,
                    f"Ticket de {bloqueado.patente} validado"
                    f"{f' (pagaste Gs. {int(cobrado)})' if cobrado else ''}. "
                    f"Tenés hasta las {hasta:%H:%M} hs para salir sin recargo.",
                )
                return redirect("estacionamiento:mis_movimientos")
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
                movimiento = get_object_or_404(_abiertos_del_usuario(perfil), pk=pk)
    else:
        form = TicketPagoForm()
 
    return render(
        request,
        "estacionamiento/validar_ticket.html",
        {
            "movimiento": movimiento,
            "cuenta": movimiento.cobro_vigente(),
            "form": form,
            "tolerancia": tolerancia,
        },
    )
 