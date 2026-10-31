"""
Datos del formulario de ingreso en 2 pasos (1: chapa, 2: espacio).

analizar_patente(patente) averigua, para una chapa:
  - a quién pertenece (vehiculo / usuario; None si no está registrada),
  - si ese usuario tiene reservas VIGENTES ahora (Pendientes, dentro de su franja),
  - qué espacios se pueden elegir:
      * con reservas  -> sólo los espacios reservados,
      * sin reservas  -> los espacios Libres de las zonas a las que el usuario
                         tiene acceso (Zona.permitidas_para; una chapa no
                         registrada sólo ve las zonas públicas).
Cada espacio devuelto trae dos atributos extra: .reserva (la Reserva o None) y
.conflicto (True si está Ocupado/Fuera de servicio y habrá que reasignarlo).
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
            Espacio.objects.filter(
                tipo_estado__nombre_estado="Libre",
                zona__in=Zona.permitidas_para(usuario),
            )
            .select_related("zona", "zona__facultad", "tipo_estado")
            .order_by("zona__nombre", "numero")
        )

    for e in espacios:
        e.reserva = por_espacio.get(e.pk)
        e.conflicto = e.tipo_estado.nombre_estado not in ESTADOS_UTILES

    return {
        "vehiculo": vehiculo,
        "usuario": usuario,
        "reservas": reservas,
        "con_reserva": bool(reservas),
        "por_espacio": por_espacio,
        "espacios": espacios,
    }


def agrupar_por_zona(espacios):
    """[{'zona': Zona, 'espacios': [Espacio, ...]}, ...] respetando el orden recibido."""
    grupos, por_zona = [], {}
    for e in espacios:
        g = por_zona.get(e.zona_id)
        if g is None:
            g = {"zona": e.zona, "espacios": []}
            por_zona[e.zona_id] = g
            grupos.append(g)
        g["espacios"].append(e)
    return grupos