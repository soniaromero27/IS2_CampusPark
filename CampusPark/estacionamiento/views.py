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
from django.http import JsonResponse
from django.views.decorators.http import require_POST

import datetime as dt
import math
from urllib.parse import urlencode 

from reglas.models import Reglamento
from campuspark.paginacion import paginar
from usuarios.decorators import admin_requerido, personal_requerido
from vehiculos.models import Vehiculo

from .forms import EspacioForm, EspaciosForm, IngresoForm, ReservaForm, ZonaForm, TicketPagoForm, PatenteForm
from .models import Espacio, Movimiento, Reserva, TipoEstado, TipoEstadoReserva, Zona, Ticket, Pago
from .ingreso import analizar_patente, agrupar_por_zona
from .cuadricula import contexto_cuadricula
from .reservas_estado import actualizar_reservas_vencidas

@login_required
@require_POST
def actualizar_reservas_view(request):
    """Repite la actualización de reservas vencidas sin recargar la página (la llama el botón Actualizar)."""
    return JsonResponse({"actualizadas": actualizar_reservas_vencidas()})



@login_required
def lista_reservas_view(request):
    """
    Consulta de las reservas del usuario autenticado. Se puede ordenar
    por cualquier columna, ascendente o descendente, con los parámetros
    GET ?orden=<campo>&dir=<asc|desc>, buscar con ?q=... sobre zona y
    estado, y filtrar por rango de fechas (sobre el día de la reserva)
    con ?desde=AAAA-MM-DD y/o ?hasta=AAAA-MM-DD.
    """
    
    actualizadas = actualizar_reservas_vencidas()
    if actualizadas:
        messages.info(
            request,
            f"Se actualizó {actualizadas} reserva vencida."
            if actualizadas == 1
            else f"Se actualizaron {actualizadas} reservas vencidas.",
        )

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
    actualizadas = actualizar_reservas_vencidas()
    if actualizadas:
        messages.info(
            request,
            f"Se actualizó {actualizadas} reserva vencida."
            if actualizadas == 1
            else f"Se actualizaron {actualizadas} reservas vencidas.",
        )    
    
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
    Registrar ingreso de vehículo en 2 pasos (sólo Personal o Administrador):

      Paso 1  GET  ?patente=...   -> se escribe la chapa (PatenteForm).
      Paso 2  GET  (chapa válida) -> se muestran los espacios elegibles, en
              lista o en cuadrícula (?vista=lista|cuadros): los espacios
              RESERVADOS si la chapa tiene reservas vigentes, o los libres
              de las zonas a las que el usuario tiene acceso si no.
              POST                -> se valida de nuevo (IngresoForm) y se
              registra el movimiento.

    Si el ingreso corresponde a una reserva, se la marca 'Confirmada'
    (actualizando su espacio si hubo reasignación) y se avisa; en todos los
    casos el espacio final queda 'Ocupado'.
    """
    vista = request.GET.get("vista") or request.POST.get("vista") or "lista"
    if vista not in ("lista", "cuadros"):
        vista = "lista"

    form = None      # formulario del paso 2
    paso1 = None     # formulario del paso 1
    patente = ""

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
                if form.reasignado:
                    reserva.espacio = espacio
                reserva.save()

                if form.reasignado:
                    messages.warning(
                        request,
                        f"{patente} tenía reservado el espacio N°{form.espacio_original.numero} "
                        f"de la zona '{espacio.zona}', pero estaba ocupado: se lo reasignó al "
                        f"espacio N°{espacio.numero} de la misma zona.",
                    )
                else:
                    messages.success(
                        request,
                        f"{patente} ingresó en su espacio reservado: zona '{espacio.zona}', "
                        f"espacio N°{espacio.numero}.",
                    )

            return redirect("estacionamiento:movimientos_lista")

        patente = form.cleaned_data.get("patente") or ""
        if not patente:  # la chapa dejó de ser válida entre un paso y el otro
            paso1 = PatenteForm({"patente": request.POST.get("patente", "")})
            paso1.is_valid()

    elif request.GET.get("patente"):
        paso1 = PatenteForm(request.GET)
        if paso1.is_valid():
            patente = paso1.cleaned_data["patente"]
            form = IngresoForm(initial={"patente": patente})

    if patente:
        analisis = analizar_patente(patente)
        return render(
            request,
            "estacionamiento/ingreso_form.html",
            {
                "paso": 2,
                "form": form,
                "vista": vista,
                "patente": patente,
                "usuario": analisis["usuario"],
                "reservas": analisis["reservas"],
                "con_reserva": analisis["con_reserva"],
                "espacios": analisis["espacios"],
                "grupos": agrupar_por_zona(analisis["espacios"]),
            },
        )

    patentes = Vehiculo.objects.order_by("matricula").values_list("matricula", flat=True)
    return render(
        request,
        "estacionamiento/ingreso_form.html",
        {"paso": 1, "form": paso1 or PatenteForm(), "vista": vista, "patentes": patentes},
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
    """
    Todos los tickets. Filtros: ?estado=pendiente|pagado|sin_cargo|sin_tarifa y ?q=...
    (número, patente, nombre, apellido o documento). Se puede ordenar por cualquier
    columna con ?orden=<campo>&dir=<asc|desc>.
    """
    campos_orden = {
        "numero": ["numero"],
        "patente": ["patente", "numero"],
        "usuario": ["usuario__apellido", "usuario__nombre", "numero"],
        "salida": ["fecha_salida"],
        "horas": ["horas", "numero"],
        "monto": ["monto", "numero"],
        "estado": ["estado", "numero"],
    }
 
    orden = request.GET.get("orden", "numero")
    if orden not in campos_orden:
        orden = "numero"
 
    direccion = request.GET.get("dir", "desc")
    if direccion not in ("asc", "desc"):
        direccion = "desc"
 
    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]
 
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
 
    tickets = Ticket.objects.select_related("usuario")
    if estado in Ticket.Estado.values:
        tickets = tickets.filter(estado=estado)
    if q:
        tickets = tickets.filter(
            Q(numero__icontains=q)
            | Q(patente__icontains=q)
            | Q(usuario__nombre__icontains=q)
            | Q(usuario__apellido__icontains=q)
            | Q(usuario__documento__icontains=q)
        )
    tickets = tickets.order_by(*campos)
 
    return render(
        request,
        "estacionamiento/tickets_lista.html",
        {
            **paginar(request, tickets, "tickets"),
            "q": q,
            "estado": estado,
            "estados": Ticket.Estado.choices,
            "orden": orden,
            "dir": direccion,
        },
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
 
 
MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
MESES_CORTO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]  # índice: weekday()
DIAS_CORTO_DOM = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]  # índice: (weekday() + 1) % 7


def _abreviar_monto(n):
    """1500000 -> '1,5 M'; 750000 -> '750 mil'; 0 -> '0'. Para las etiquetas del eje."""
    n = float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:g} M".replace(".", ",")
    if n >= 1_000:
        return f"{n / 1_000:g} mil".replace(".", ",")
    return f"{n:g}".replace(".", ",")


def _escala_grafico(maximo):
    """Tope 'redondo' del eje vertical (1, 1,5, 2, 3, 4, 5, 6, 8 o 10 x potencia de 10)."""
    if maximo <= 0:
        return 100000.0
    base = 10 ** (len(str(int(maximo))) - 1)
    for factor in (1, 1.5, 2, 3, 4, 5, 6, 8, 10):
        if maximo <= base * factor:
            return float(base * factor)
    return float(base * 10)


def _url_periodo(periodo, ref, extra=None):
    """Enlace al dashboard en 'periodo', tomando como referencia la fecha 'ref'.
    'extra' agrega otros parámetros (por ejemplo tipo y vista) al enlace."""
    clave, valor = {
        "dia": ("dia", ref.isoformat()),
        "mes": ("mes", ref.strftime("%Y-%m")),
        "anio": ("anio", str(ref.year)),
    }[periodo]
    return "?" + urlencode({"periodo": periodo, clave: valor, **(extra or {})})


def _titulo_periodo(periodo, inicio_d):
    if periodo == "dia":
        return (
            f"{DIAS_ES[inicio_d.weekday()].capitalize()} {inicio_d.day} de "
            f"{MESES_ES[inicio_d.month - 1]} de {inicio_d.year}"
        )
    if periodo == "mes":
        return f"{MESES_ES[inicio_d.month - 1].capitalize()} {inicio_d.year}"
    return str(inicio_d.year)


def _grafico_recaudacion(periodo, inicio_d, fin_d, hoy):
    """
    Datos del gráfico de barras de recaudación (estilo Samsung Health):
      - año: una barra por mes (enero a diciembre);
      - mes: una barra por cada día del mes;
      - día: una barra por cada día de la semana (domingo a sábado) que
        contiene el día elegido, con ese día resaltado.
    Incluye los períodos sin cobros (barra en cero).
    """
    if periodo == "dia":
        ini = inicio_d - dt.timedelta(days=(inicio_d.weekday() + 1) % 7)  # domingo
        fin = ini + dt.timedelta(days=7)
        ultimo = fin - dt.timedelta(days=1)
        subtitulo = (
            f"Semana del {ini.day} de {MESES_ES[ini.month - 1]} "
            f"al {ultimo.day} de {MESES_ES[ultimo.month - 1]}"
        )
        texto_enlace = "Ver este día"
    elif periodo == "mes":
        ini, fin = inicio_d, fin_d
        subtitulo = "Recaudación de cada día del mes"
        texto_enlace = "Ver este día"
    else:
        ini, fin = inicio_d, fin_d
        subtitulo = "Recaudación de cada mes del año"
        texto_enlace = "Ver este mes"

    desde = timezone.make_aware(dt.datetime.combine(ini, dt.time.min))
    hasta = timezone.make_aware(dt.datetime.combine(fin, dt.time.min))
    pagos = Pago.objects.filter(fecha_pago__gte=desde, fecha_pago__lt=hasta)

    barras = []
    if periodo == "anio":
        filas = (
            pagos.annotate(p=TruncMonth("fecha_pago"))
            .values("p")
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by()
        )
        datos = {(r["p"].year, r["p"].month): r for r in filas}
        for m in range(1, 13):
            r = datos.get((inicio_d.year, m), {})
            primero = dt.date(inicio_d.year, m, 1)
            barras.append(
                {
                    "eje": MESES_CORTO[m - 1],
                    "mostrar_eje": True,
                    "titulo": f"{MESES_ES[m - 1].capitalize()} {inicio_d.year}",
                    "total": r.get("total") or 0,
                    "cantidad": r.get("cantidad", 0),
                    "href": _url_periodo("mes", primero),
                    "actual": False,
                    "hoy": (hoy.year, hoy.month) == (inicio_d.year, m),
                    "futuro": primero > hoy,
                }
            )
    else:
        filas = (
            pagos.annotate(p=TruncDate("fecha_pago"))
            .values("p")
            .annotate(total=Sum("monto"), cantidad=Count("id"))
            .order_by()
        )
        datos = {r["p"]: r for r in filas}
        d = ini
        while d < fin:
            r = datos.get(d, {})
            if periodo == "dia":
                eje = DIAS_CORTO_DOM[(d.weekday() + 1) % 7]
                titulo = f"{DIAS_ES[d.weekday()].capitalize()} {d.day} de {MESES_ES[d.month - 1]}"
                mostrar = True
            else:
                eje = str(d.day)
                titulo = f"{d.day} de {MESES_ES[d.month - 1]}"
                mostrar = d.day == 1 or d.day % 5 == 0
            barras.append(
                {
                    "eje": eje,
                    "mostrar_eje": mostrar,
                    "titulo": titulo,
                    "total": r.get("total") or 0,
                    "cantidad": r.get("cantidad", 0),
                    "href": _url_periodo("dia", d),
                    "actual": periodo == "dia" and d == inicio_d,
                    "hoy": d == hoy,
                    "futuro": d > hoy,
                }
            )
            d += dt.timedelta(days=1)

    escala = _escala_grafico(max((float(b["total"]) for b in barras), default=0))
    for b in barras:
        b["pct"] = int(round(max(float(b["total"]) * 100 / escala, 3))) if b["total"] > 0 else 0

    return {
        "barras": barras,
        "subtitulo": subtitulo,
        "texto_enlace": texto_enlace,
        "lineas": [
            {"pos": 0, "etiqueta": _abreviar_monto(escala)},
            {"pos": 50, "etiqueta": _abreviar_monto(escala / 2)},
            {"pos": 100, "etiqueta": "0"},
        ],
    }


@admin_requerido
def dashboard_view(request):
    """
    Resumen de recaudación (sólo Administrador). Cuenta los pagos según su
    fecha de pago. Filtrable por día, mes o año:
    ?periodo=dia&dia=AAAA-MM-DD | ?periodo=mes&mes=AAAA-MM | ?periodo=anio&anio=AAAA

    Arriba muestra una barra con el total recaudado del período elegido y,
    debajo, un gráfico de barras: por mes (año), por día (mes) o por día de
    la semana, de domingo a sábado (día).
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
    cantidad = resumen["cantidad"] or 0
    promedio = total / cantidad if cantidad else 0

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

    # Lo emitido en el período que todavía no se cobró
    por_cobrar = Ticket.objects.filter(
        estado=Ticket.Estado.PENDIENTE, fecha_emision__gte=inicio, fecha_emision__lt=fin
    ).aggregate(total=Sum(F("monto") - F("monto_pagado_previo")), cantidad=Count("id"))

    sin_cargo = Ticket.objects.filter(
        estado=Ticket.Estado.SIN_CARGO, fecha_pago__gte=inicio, fecha_pago__lt=fin
    ).count()

    # ---- Barra de estadísticas: pestañas Día/Mes/Año y flechas anterior/siguiente ----
    ref = hoy if inicio_d <= hoy < fin_d else inicio_d   # fecha que se conserva al cambiar de pestaña
    tabs = [
        {"clave": c, "etiqueta": e, "url": _url_periodo(c, ref), "activo": c == periodo}
        for c, e in (("dia", "Día"), ("mes", "Mes"), ("anio", "Año"))
    ]
    if periodo == "dia":
        anterior = inicio_d - dt.timedelta(days=1)
    elif periodo == "mes":
        anterior = (inicio_d - dt.timedelta(days=1)).replace(day=1)
    else:
        anterior = dt.date(inicio_d.year - 1, 1, 1)
    siguiente = fin_d   # primer día del período siguiente

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
            "titulo_periodo": _titulo_periodo(periodo, inicio_d),
            "tabs": tabs,
            "url_anterior": _url_periodo(periodo, anterior),
            "url_siguiente": _url_periodo(periodo, siguiente),
            "siguiente_ok": siguiente <= hoy,
            "total": total,
            "cantidad": cantidad,
            "promedio": promedio,
            "por_metodo": por_metodo,
            "grafico": _grafico_recaudacion(periodo, inicio_d, fin_d, hoy),
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
    El usuario valida (y paga, si hay algo que pagar) su propio ticket ANTES de salir.
    Si no hay nada para cobrar (0 Gs.), no se piden formas de pago: alcanza con
    el botón Validar. El monto se vuelve a calcular al confirmar, con el movimiento
    bloqueado: si mientras tanto pasó a haber algo que pagar, pide la forma de pago.
    """
    perfil = request.user.perfil
    movimiento = get_object_or_404(_abiertos_del_usuario(perfil), pk=pk)
    tolerancia = Reglamento.tolerancia_actual()
    form = TicketPagoForm()
 
    if request.method == "POST":
        form = TicketPagoForm(request.POST)
        metodo = form.cleaned_data["metodo"] if form.is_valid() else None
        try:
            with transaction.atomic():
                bloqueado = get_object_or_404(
                    Movimiento.objects.select_for_update(of=("self",)),
                    pk=pk, vehiculo__usuario=perfil, fecha_hora_salida__isnull=True,
                )
                cobrado = bloqueado.validar(metodo, perfil)
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
            form = TicketPagoForm()  # formulario limpio, sin errores de campo
 
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
 


def _leer_periodo(request):
    """
    Lee el filtro ?periodo=dia|mes|anio (&dia= / &mes= / &anio=) y devuelve
    lo que necesitan los dashboards: el rango [inicio, fin) y datos para el formulario.
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

    return {
        "periodo": periodo,
        "dia": dia,
        "mes": mes,
        "anio": anio,
        "inicio": timezone.make_aware(dt.datetime.combine(inicio_d, dt.time.min)),
        "fin": timezone.make_aware(dt.datetime.combine(fin_d, dt.time.min)),
        "rango_texto": {
            "dia": inicio_d.strftime("%d/%m/%Y"),
            "mes": inicio_d.strftime("%m/%Y"),
            "anio": str(inicio_d.year),
        }[periodo],
        "formato_serie": {"dia": "H:i", "mes": "d/m/Y", "anio": "m/Y"}[periodo],
    }


COLOR_ENTRADAS = "#1d5fa7"
COLOR_SALIDAS = "#f59e0b"
COLORES_ZONA = [
    "#1d5fa7", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed",
    "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569",
]


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _escala_conteo(maximo):
    """Tope del eje para cantidades: entero y par, para que la mitad también lo sea."""
    if maximo <= 0:
        return 4.0
    return float(max(4, math.ceil(_escala_grafico(maximo) / 2) * 2))


def _valor_texto(ent, sal, tipo):
    if tipo == "entradas":
        return _plural(ent, "entrada", "entradas")
    if tipo == "salidas":
        return _plural(sal, "salida", "salidas")
    return f"{_plural(ent, 'entrada', 'entradas')} · {_plural(sal, 'salida', 'salidas')}"


def _sub_zonas(por_tipo, tipo, nombres):
    """Desglose por zona en texto. 'por_tipo' = {"entradas": {zona_id: n}, "salidas": {...}}."""
    partes = []
    for clave, etiqueta in (("entradas", "Entradas"), ("salidas", "Salidas")):
        if clave not in por_tipo:
            continue
        items = ", ".join(
            f"{nombres[z]} {n}"
            for z, n in sorted(por_tipo[clave].items(), key=lambda kv: nombres[kv[0]])
            if n
        )
        if tipo == "ambas":
            partes.append(f"{etiqueta}: {items or '—'}")
        else:
            partes.append(items or "Sin movimientos")
    return " | ".join(partes)


def _barra_periodo(periodo, inicio_d, fin_d, hoy, extra):
    """Pestañas Día/Mes/Año, flechas anterior/siguiente y título, conservando 'extra' en los enlaces."""
    ref = hoy if inicio_d <= hoy < fin_d else inicio_d
    if periodo == "dia":
        anterior = inicio_d - dt.timedelta(days=1)
    elif periodo == "mes":
        anterior = (inicio_d - dt.timedelta(days=1)).replace(day=1)
    else:
        anterior = dt.date(inicio_d.year - 1, 1, 1)
    siguiente = fin_d
    return {
        "titulo_periodo": _titulo_periodo(periodo, inicio_d),
        "tabs": [
            {"clave": c, "etiqueta": e, "url": _url_periodo(c, ref, extra), "activo": c == periodo}
            for c, e in (("dia", "Día"), ("mes", "Mes"), ("anio", "Año"))
        ],
        "url_anterior": _url_periodo(periodo, anterior, extra),
        "url_siguiente": _url_periodo(periodo, siguiente, extra),
        "siguiente_ok": siguiente <= hoy,
    }


def _grafico_movimientos(periodo, inicio_d, fin_d, hoy, tipo, vista, extra, zona_id=None):
    """
    Gráfico de barras de movimientos (entradas y/o salidas):
      - año: una barra por mes; mes: una por día; día: los 7 días de la
        semana (domingo a sábado) que contiene el día elegido.
      - tipo 'entradas' / 'salidas': una barra por período; 'ambas': dos
        barras lado a lado (entradas y salidas).
      - vista 'total': una sola pila; vista 'zona': la barra se apila por
        zona, con un color por zona.
      - zona_id: si se indica, sólo cuenta los movimientos de esa zona.
    """
    if periodo == "dia":
        ini = inicio_d - dt.timedelta(days=(inicio_d.weekday() + 1) % 7)  # domingo
        fin = ini + dt.timedelta(days=7)
        ultimo = fin - dt.timedelta(days=1)
        subtitulo = (
            f"Semana del {ini.day} de {MESES_ES[ini.month - 1]} "
            f"al {ultimo.day} de {MESES_ES[ultimo.month - 1]}"
        )
        texto_enlace = "Ver este día"
    elif periodo == "mes":
        ini, fin = inicio_d, fin_d
        subtitulo = "Movimientos de cada día del mes"
        texto_enlace = "Ver este día"
    else:
        ini, fin = inicio_d, fin_d
        subtitulo = "Movimientos de cada mes del año"
        texto_enlace = "Ver este mes"

    desde = timezone.make_aware(dt.datetime.combine(ini, dt.time.min))
    hasta = timezone.make_aware(dt.datetime.combine(fin, dt.time.min))

    zonas = list(Zona.objects.order_by("nombre").values_list("id", "nombre"))
    nombres = dict(zonas)
    orden = {zid: i for i, (zid, _) in enumerate(zonas)}
    colores = {zid: COLORES_ZONA[i % len(COLORES_ZONA)] for i, (zid, _) in enumerate(zonas)}

    trunc = TruncMonth if periodo == "anio" else TruncDate

    def contar(campo):
        """{clave_del_período: {zona_id (o None si vista total): cantidad}}"""
        qs = Movimiento.objects.filter(**{f"{campo}__gte": desde, f"{campo}__lt": hasta})
        if zona_id:
            qs = qs.filter(espacio__zona_id=zona_id)
        valores = ["p"] + (["espacio__zona"] if vista == "zona" else [])
        filas = qs.annotate(p=trunc(campo)).values(*valores).annotate(n=Count("id")).order_by()
        salida = defaultdict(dict)
        for r in filas:
            p = r["p"]
            clave = (p.year, p.month) if periodo == "anio" else p
            salida[clave][r.get("espacio__zona")] = r["n"]
        return salida

    series = []
    if tipo in ("entradas", "ambas"):
        series.append(("entradas", contar("fecha_hora_ingreso")))
    if tipo in ("salidas", "ambas"):
        series.append(("salidas", contar("fecha_hora_salida")))

    # Períodos (columnas) del gráfico
    columnas = []
    if periodo == "anio":
        for m in range(1, 13):
            primero = dt.date(inicio_d.year, m, 1)
            columnas.append(
                {
                    "clave": (inicio_d.year, m),
                    "eje": MESES_CORTO[m - 1],
                    "mostrar_eje": True,
                    "titulo": f"{MESES_ES[m - 1].capitalize()} {inicio_d.year}",
                    "href": _url_periodo("mes", primero, extra),
                    "actual": False,
                    "hoy": (hoy.year, hoy.month) == (inicio_d.year, m),
                    "futuro": primero > hoy,
                }
            )
    else:
        d = ini
        while d < fin:
            if periodo == "dia":
                eje = DIAS_CORTO_DOM[(d.weekday() + 1) % 7]
                titulo = f"{DIAS_ES[d.weekday()].capitalize()} {d.day} de {MESES_ES[d.month - 1]}"
                mostrar = True
            else:
                eje = str(d.day)
                titulo = f"{d.day} de {MESES_ES[d.month - 1]}"
                mostrar = d.day == 1 or d.day % 5 == 0
            columnas.append(
                {
                    "clave": d,
                    "eje": eje,
                    "mostrar_eje": mostrar,
                    "titulo": titulo,
                    "href": _url_periodo("dia", d, extra),
                    "actual": periodo == "dia" and d == inicio_d,
                    "hoy": d == hoy,
                    "futuro": d > hoy,
                }
            )
            d += dt.timedelta(days=1)

    zonas_usadas = set()
    maximo = 0
    for col in columnas:
        grupos = []
        por_tipo = {}
        totales_tipo = {"entradas": 0, "salidas": 0}
        for nombre, datos in series:
            zdict = datos.get(col["clave"], {})
            total = sum(zdict.values())
            totales_tipo[nombre] = total
            por_tipo[nombre] = zdict
            if vista == "zona":
                segmentos = []
                for z, n in sorted(zdict.items(), key=lambda kv: orden[kv[0]]):
                    if n:
                        zonas_usadas.add(z)
                        segmentos.append({"n": n, "color": colores[z], "zona": nombres[z]})
            else:
                color = COLOR_ENTRADAS if nombre == "entradas" else COLOR_SALIDAS
                segmentos = [{"n": total, "color": color, "zona": ""}] if total else []
            maximo = max(maximo, total)
            grupos.append(
                {
                    "clase": nombre,
                    "total": total,
                    "segmentos": segmentos,
                    "rayado": vista == "zona" and tipo == "ambas" and nombre == "salidas",
                }
            )
        col["grupos"] = grupos
        col["vacio"] = all(g["total"] == 0 for g in grupos)
        col["valor"] = _valor_texto(totales_tipo["entradas"], totales_tipo["salidas"], tipo)
        col["sub"] = _sub_zonas(por_tipo, tipo, nombres) if vista == "zona" else ""

    escala = _escala_conteo(maximo)
    for col in columnas:
        for g in col["grupos"]:
            g["pct"] = f"{max(g['total'] * 100 / escala, 3):.1f}" if g["total"] else "0"

    # Leyenda
    leyenda = []
    nota = ""
    if vista == "zona":
        leyenda = [
            {"color": colores[z], "etiqueta": nombres[z]}
            for z, _ in zonas
            if z in zonas_usadas
        ]
        if tipo == "ambas":
            nota = "En cada día o mes, la barra de la izquierda son las entradas y la de la derecha (rayada), las salidas."
    elif tipo == "ambas":
        leyenda = [
            {"color": COLOR_ENTRADAS, "etiqueta": "Entradas"},
            {"color": COLOR_SALIDAS, "etiqueta": "Salidas"},
        ]

    return {
        "columnas": columnas,
        "subtitulo": subtitulo,
        "texto_enlace": texto_enlace,
        "leyenda": leyenda,
        "nota": nota,
        "lineas": [
            {"pos": 0, "etiqueta": _abreviar_monto(escala)},
            {"pos": 50, "etiqueta": _abreviar_monto(escala / 2)},
            {"pos": 100, "etiqueta": "0"},
        ],
    }


@admin_requerido
def dashboard_ocupacion_view(request):
    """
    Dashboard de ocupación (sólo Administrador; cambiá el decorador por
    personal_requerido si querés que también lo vea el personal).

    - Estado ACTUAL de los espacios (libres/ocupados/reservados/fuera de
      servicio) por zona y en total: es una foto de "ahora", no depende del filtro.
    - Movimientos (entradas y salidas) del período elegido (día, mes o año):
      barra de estadísticas arriba y gráfico de barras. Se puede ver
      ?tipo=entradas|salidas|ambas, ?vista=total|zona y, para ver una sola
      zona, ?zona=<id> (en ese caso la barra de estadísticas y el gráfico
      sólo cuentan esa zona y la vista "por zona" no aplica).
    """
    f = _leer_periodo(request)
    inicio, fin, periodo = f["inicio"], f["fin"], f["periodo"]

    tipo = request.GET.get("tipo", "ambas")
    if tipo not in ("entradas", "salidas", "ambas"):
        tipo = "ambas"
    vista = request.GET.get("vista", "total")
    if vista not in ("total", "zona"):
        vista = "total"

    hoy = timezone.localdate()
    inicio_d = timezone.localtime(inicio).date()
    fin_d = timezone.localtime(fin).date()

    entradas = Movimiento.objects.filter(fecha_hora_ingreso__gte=inicio, fecha_hora_ingreso__lt=fin)
    salidas = Movimiento.objects.filter(fecha_hora_salida__gte=inicio, fecha_hora_salida__lt=fin)

    # ---- Espacios por zona (estado actual) + entradas/salidas del período por zona ----
    zonas = list(
        Zona.objects.select_related("facultad")
        .annotate(
            total=Count("espacios"),
            libres=Count("espacios", filter=Q(espacios__tipo_estado__nombre_estado="Libre")),
            ocupados=Count("espacios", filter=Q(espacios__tipo_estado__nombre_estado="Ocupado")),
            reservados=Count("espacios", filter=Q(espacios__tipo_estado__nombre_estado="Reservado")),
            fuera=Count("espacios", filter=Q(espacios__tipo_estado__nombre_estado="Fuera de servicio")),
        )
        .order_by("nombre")
    )
    ent_zona = {r["espacio__zona"]: r["n"] for r in entradas.values("espacio__zona").annotate(n=Count("id"))}
    sal_zona = {r["espacio__zona"]: r["n"] for r in salidas.values("espacio__zona").annotate(n=Count("id"))}

    def pct(parte, todo):
        return round(parte * 100 / todo) if todo else 0

    for z in zonas:
        z.entradas = ent_zona.get(z.pk, 0)
        z.salidas = sal_zona.get(z.pk, 0)
        z.pct_ocupado = pct(z.ocupados, z.total - z.fuera)   # sobre espacios operativos

    totales = {
        campo: sum(getattr(z, campo) for z in zonas)
        for campo in ("total", "libres", "ocupados", "reservados", "fuera", "entradas", "salidas")
    }
    totales["pct_ocupado"] = pct(totales["ocupados"], totales["total"] - totales["fuera"])
    dentro_total = Movimiento.objects.filter(fecha_hora_salida__isnull=True).count()

    # ---- Zona elegida (opcional) ----
    zona_obj = None
    zona_raw = request.GET.get("zona", "").strip()
    if zona_raw.isdigit():
        zona_obj = next((z for z in zonas if z.pk == int(zona_raw)), None)
    zona_id = zona_obj.pk if zona_obj else None
    zona_extra = {"zona": zona_id} if zona_id else {}
    extra = {"tipo": tipo, "vista": vista, **zona_extra}
    vista_grafico = "total" if zona_id else vista   # con una sola zona no hay nada que apilar

    # ---- Números de la barra de estadísticas (de la zona elegida, o de todas) ----
    if zona_obj:
        stats = {
            "entradas": zona_obj.entradas,
            "salidas": zona_obj.salidas,
            "dentro": Movimiento.objects.filter(
                fecha_hora_salida__isnull=True, espacio__zona_id=zona_id
            ).count(),
            "pct_ocupado": zona_obj.pct_ocupado,
        }
    else:
        stats = {
            "entradas": totales["entradas"],
            "salidas": totales["salidas"],
            "dentro": dentro_total,
            "pct_ocupado": totales["pct_ocupado"],
        }

    nombres = {z.pk: z.nombre for z in zonas}
    por_tipo_total = {}
    if tipo in ("entradas", "ambas"):
        por_tipo_total["entradas"] = ent_zona
    if tipo in ("salidas", "ambas"):
        por_tipo_total["salidas"] = sal_zona
    detalle_total = {
        "valor": _valor_texto(stats["entradas"], stats["salidas"], tipo),
        "sub": _sub_zonas(por_tipo_total, tipo, nombres) if vista_grafico == "zona" else "",
    }

    # ---- Selectores (conservan período, tipo, vista y zona) ----
    selector_tipo = [
        {"etiqueta": e, "activo": c == tipo,
         "url": _url_periodo(periodo, inicio_d, {"tipo": c, "vista": vista, **zona_extra})}
        for c, e in (("entradas", "Entradas"), ("salidas", "Salidas"), ("ambas", "Ambas"))
    ]
    selector_vista = [
        {"etiqueta": e, "activo": c == vista,
         "url": _url_periodo(periodo, inicio_d, {"tipo": tipo, "vista": c, **zona_extra})}
        for c, e in (("total", "Total"), ("zona", "Por zona"))
    ]
    selector_zona = [
        {"etiqueta": "Todas las zonas", "activo": zona_id is None,
         "url": _url_periodo(periodo, inicio_d, {"tipo": tipo, "vista": vista})}
    ] + [
        {"etiqueta": z.nombre, "activo": z.pk == zona_id,
         "url": _url_periodo(periodo, inicio_d, {"tipo": tipo, "vista": vista, "zona": z.pk})}
        for z in zonas
    ]

    return render(
        request,
        "estacionamiento/dashboard_ocupacion.html",
        {
            **f,
            **_barra_periodo(periodo, inicio_d, fin_d, hoy, extra),
            "tipo": tipo,
            "vista": vista,
            "zona_sel": zona_obj,
            "stats": stats,
            "selector_tipo": selector_tipo,
            "selector_vista": selector_vista,
            "selector_zona": selector_zona,
            "zonas": zonas,
            "totales": totales,
            "dentro_ahora": dentro_total,
            "detalle_total": detalle_total,
            "grafico": _grafico_movimientos(
                periodo, inicio_d, fin_d, hoy, tipo, vista_grafico, extra, zona_id
            ),
        },
    )