
"""
Datos del formulario de ingreso en 2 pasos (1: chapa, 2: espacio).

analizar_patente(patente) averigua, para una chapa:
  - a quién pertenece (vehiculo / usuario; None si no está registrada),
  - si ese usuario tiene reservas VIGENTES ahora (Pendientes, dentro de su franja),
  - qué espacios se muestran:
      * con reservas  -> sólo los espacios reservados (todos se pueden elegir),
      * sin reservas  -> TODOS los espacios de las zonas a las que el usuario tiene
                         acceso (Zona.permitidas_para; una chapa no registrada sólo
                         ve las zonas públicas). Sólo se pueden elegir los Libres:
                         los demás se ven pero no se pueden seleccionar, y nunca se
                         muestra la patente de quien los ocupa.
Cada espacio devuelto trae atributos extra:
  .reserva       la Reserva (o None),
  .conflicto     True si es un espacio reservado que está Ocupado/Fuera de servicio
                 (se reasignará a otro libre de la misma zona),
  .seleccionable True si se puede elegir.
"""
from django.utils import timezone

from vehiculos.models import Vehiculo

from .models import Espacio, Reserva, Zona

ESTADOS_UTILES = ("Libre", "Reservado")


def analizar_patente(patente):
    vehiculo = (
        Vehiculo.objects.filter(matricula=patente)
        .select_related("usuario", "usuario__tipo", "usuario__facultad")
        .first()
    )
    usuario = vehiculo.usuario if vehiculo else None

    reservas = []
    if usuario is not None:
        ahora = timezone.now()
        reservas = list(
            Reserva.objects.filter(
                usuario=usuario, fecha_inicio__lte=ahora, fecha_fin__gte=ahora
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

    por_espacio = {}
    for r in reservas:
        por_espacio.setdefault(r.espacio_id, r)

    if reservas:
        unicos = {}
        for r in reservas:
            unicos.setdefault(r.espacio_id, r.espacio)
        espacios = sorted(unicos.values(), key=lambda e: (e.zona.nombre, e.numero))
    else:
        espacios = list(
            Espacio.objects.filter(zona__in=Zona.permitidas_para(usuario))
            .select_related("zona", "zona__facultad", "tipo_estado")
            .order_by("zona__nombre", "numero")
        )

    for e in espacios:
        e.reserva = por_espacio.get(e.pk)
        estado = e.tipo_estado.nombre_estado
        if reservas:
            e.conflicto = estado not in ESTADOS_UTILES
            e.seleccionable = True
        else:
            e.conflicto = False
            e.seleccionable = estado == "Libre"

    return {
        "vehiculo": vehiculo,
        "usuario": usuario,
        "reservas": reservas,
        "con_reserva": bool(reservas),
        "por_espacio": por_espacio,
        "espacios": espacios,
    }


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

