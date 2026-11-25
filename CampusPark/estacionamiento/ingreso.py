"""
Datos del formulario de ingreso en 2 pasos (1: chapa, 2: espacio) y de la
reubicación de un vehículo ya estacionado.

analizar_patente(patente) averigua, para una chapa:
  - a quién pertenece (vehiculo / usuario; None si no está registrada),
  - si ese usuario tiene reservas VIGENTES ahora (Pendientes, dentro de su franja),
  - qué espacios se muestran:
      * con reservas  -> sólo los espacios reservados (todos se pueden elegir),
      * sin reservas  -> TODOS los espacios de las zonas a las que el usuario tiene
                         acceso (Zona.permitidas_para). Sólo se pueden elegir los Libres.
Cada espacio devuelto trae atributos extra:
  .reserva       la Reserva (o None),
  .ocupante      el Movimiento abierto en ese espacio (sólo se calcula para espacios
                 reservados; None si está desocupado),
  .conflicto     True si es un espacio reservado que está ocupado por otro vehículo
                 o Fuera de servicio,
  .seleccionable True si se puede elegir.

opciones_reubicacion(movimiento) decide dónde se puede mover un vehículo ya
estacionado: primero otro espacio libre de su misma zona; si no hay, uno libre
de otra zona que su dueño pueda usar; si tampoco, no hay lugar ("ninguno").
"""
from django.utils import timezone

from vehiculos.models import Vehiculo

from .models import Espacio, Movimiento, Reserva, TipoEstado, Zona

ESTADOS_UTILES = ("Libre", "Reservado")


def marcar_reservados_ahora(espacios, usuario=None):
    """
    Los espacios Libres que tienen una reserva Pendiente vigente AHORA de otro
    usuario se muestran como 'Reservado' (sólo en memoria: no se guarda nada).
    Así quedan como no disponibles únicamente durante la fecha y hora de la reserva.
    """
    if not espacios:
        return
    ahora = timezone.now()
    reservas = Reserva.objects.filter(
        espacio_id__in=[e.pk for e in espacios],
        fecha_inicio__lte=ahora,
        fecha_fin__gte=ahora,
        tipo_estado_reserva__nombre_estado_reserva="Pendiente",
    )
    if usuario is not None:
        reservas = reservas.exclude(usuario=usuario)
    ids = set(reservas.values_list("espacio_id", flat=True))
    if not ids:
        return
    reservado = TipoEstado.objects.filter(nombre_estado="Reservado").first()
    if reservado is None:
        return
    for e in espacios:
        if e.pk in ids and e.tipo_estado.nombre_estado == "Libre":
            e.tipo_estado = reservado
            

def analizar_patente(patente, es_moto=False):
    
    vehiculo = (
        Vehiculo.objects.filter(matricula=patente, usuario__user__is_active=True)
        .select_related("usuario", "usuario__tipo", "usuario__facultad")
        .first()
    )
    usuario = vehiculo.usuario if vehiculo else None
    
    # El checkbox sólo vale para patentes NO registradas.
    # Si está registrada, manda el tipo real del vehículo.
    marcado = es_moto
    if vehiculo is not None:
        es_moto = vehiculo.es_moto
    checkbox_ignorado = vehiculo is not None and marcado != es_moto
    
    reservas = []
    if usuario is not None:
        ahora = timezone.now()
        reservas = list(
            Reserva.objects.filter(
                usuario=usuario, fecha_inicio__lte=ahora, fecha_fin__gte=ahora, espacio__zona__solo_motos=False,
            )
            .exclude(
                tipo_estado_reserva__nombre_estado_reserva__in=[
                    "Cancelada",
                    "Confirmada",
                    "Finalizada",
                ]
            )
            .select_related("espacio", "espacio__zona", "espacio__zona__facultad", "espacio__tipo_estado")
            .order_by("fecha_inicio")
        )

    reservas_ignoradas = []
    if es_moto:
        reservas_ignoradas, reservas = reservas, []
        
    por_espacio = {}
    for r in reservas:
        por_espacio.setdefault(r.espacio_id, r)

    ocupantes = {}
    if reservas:
        unicos = {}
        for r in reservas:
            unicos.setdefault(r.espacio_id, r.espacio)
        espacios = sorted(unicos.values(), key=lambda e: (e.zona.nombre, e.numero))
        # Quién está estacionado ahora en cada espacio reservado (por movimiento
        # abierto, no por el estado del espacio, que puede quedar desactualizado).
        ocupantes = {
            m.espacio_id: m
            for m in Movimiento.objects.filter(
                espacio_id__in=list(unicos), fecha_hora_salida__isnull=True
            )
        }
    else:
        espacios = list(
            Espacio.objects.filter(
                zona__in=Zona.permitidas_para(usuario),
                zona__solo_motos=es_moto,
                )
            .select_related("zona", "zona__facultad", "tipo_estado")
            .order_by("zona__nombre", "numero")
        )
        marcar_reservados_ahora(espacios, usuario)
        
    for e in espacios:
        e.reserva = por_espacio.get(e.pk)
        e.ocupante = ocupantes.get(e.pk)
        estado = e.tipo_estado.nombre_estado
        
        if reservas:
            e.conflicto = e.ocupante is not None or estado == "Fuera de servicio"
            e.seleccionable = True
        else:
            e.conflicto = False
            e.seleccionable = estado == "Libre"
            if e.zona.solo_motos and not es_moto:
                e.seleccionable = False


    return {
        "vehiculo": vehiculo,
        "usuario": usuario,
        "reservas": reservas,
        "con_reserva": bool(reservas),
        "por_espacio": por_espacio,
        "espacios": espacios,
        "reservas_ignoradas": reservas_ignoradas,      # NUEVO
        "es_moto": es_moto,                          # el efectivo, no el marcado
        "checkbox_ignorado": checkbox_ignorado,      # para avisar en pantalla
    }


def opciones_reubicacion(movimiento):
    """
    Dónde se puede mover el vehículo de 'movimiento' (ya estacionado).
    Devuelve {"alcance", "espacios", "usuario"}:
      alcance "zona"    -> hay libres en su misma zona; 'espacios' son los de esa zona.
      alcance "campus"  -> no hay en su zona, pero sí en otras zonas que su dueño puede
                           usar (una chapa no registrada sólo puede usar zonas públicas);
                           'espacios' son los de esas zonas.
      alcance "ninguno" -> no hay ningún lugar: hay que retirarlo.
    Cada espacio trae .seleccionable (True sólo si está Libre y no es el actual).
    """
    usuario = None
    if movimiento.vehiculo_id and movimiento.vehiculo.usuario_id:
        usuario = movimiento.vehiculo.usuario
    actual = movimiento.espacio

    def preparar(zonas):
        espacios = list(
            Espacio.objects.filter(zona__in=zonas)
            .select_related("zona", "zona__facultad", "tipo_estado")
            .order_by("zona__nombre", "numero")
        )
        marcar_reservados_ahora(espacios, usuario)
        
        for e in espacios:
            e.seleccionable = e.pk != actual.pk and e.tipo_estado.nombre_estado == "Libre"
        return espacios

    espacios = preparar(Zona.objects.filter(pk=actual.zona_id))
    if any(e.seleccionable for e in espacios):
        return {"alcance": "zona", "espacios": espacios, "usuario": usuario}

    espacios = preparar(
        Zona.permitidas_para(usuario).exclude(pk=actual.zona_id).filter(solo_motos=False)
    )
    if any(e.seleccionable for e in espacios):
        return {"alcance": "campus", "espacios": espacios, "usuario": usuario}

    return {"alcance": "ninguno", "espacios": [], "usuario": usuario}


def agrupar_por_zona(espacios):
    """[{'zona', 'espacios', 'libres'}, ...] respetando el orden recibido."""
    grupos, por_zona = [], {}
    for e in espacios:
        g = por_zona.get(e.zona_id)
        if g is None:
            g = {"zona": e.zona, "espacios": [], "libres": 0}
            por_zona[e.zona_id] = g
            grupos.append(g)
        g["espacios"].append(e)
        if e.tipo_estado.nombre_estado == "Libre":
            g["libres"] += 1
    return grupos

