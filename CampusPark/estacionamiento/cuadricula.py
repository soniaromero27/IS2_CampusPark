"""
Datos para la cuadrícula de espacios del formulario de reserva.

Uso en la vista, al armar el contexto del render:

    {"form": form, ..., **contexto_cuadricula(form.fields["espacio"].queryset)}

El template (reserva_form.html) usa:
  grupos        zonas con sus espacios, para dibujar los cuadros
  ocupaciones   {id de espacio: [[inicio, fin], ...]} con las reservas que
                siguen en pie, para que el navegador calcule qué espacios
                están libres en el día y horario que se vaya eligiendo
"""
from collections import defaultdict

from django.utils import timezone

# Fechas como texto "AAAA-MM-DDTHH:MM", en la hora local del sitio. Todas miden
# lo mismo, así que el navegador las puede comparar como texto, sin Date ni
# zonas horarias de por medio.
FORMATO_LOCAL = "%Y-%m-%dT%H:%M"


def armar_grupos(espacios):
    """
    Agrupa los espacios (ya ordenados por zona y número) en
    [{"zona": <Zona>, "espacios": [{"id", "numero", "fuera"}, ...]}, ...].
    'fuera' es True si el espacio está Fuera de servicio.
    """
    grupos = []
    por_zona = {}
    for e in espacios:
        grupo = por_zona.get(e.zona_id)
        if grupo is None:
            grupo = {"zona": e.zona, "espacios": []}
            por_zona[e.zona_id] = grupo
            grupos.append(grupo)
        grupo["espacios"].append(
            {
                "id": e.id,
                "numero": e.numero,
                "fuera": e.tipo_estado.nombre_estado == "Fuera de servicio",
            }
        )
    return grupos


def armar_ocupaciones(filas):
    """
    'filas' son tuplas (id de espacio, inicio, fin) de reservas. Devuelve
    {"<id>": [[inicio_local, fin_local], ...]} listo para json_script.
    """
    ocupaciones = defaultdict(list)
    for espacio_id, inicio, fin in filas:
        ocupaciones[str(espacio_id)].append(
            [
                timezone.localtime(inicio).strftime(FORMATO_LOCAL),
                timezone.localtime(fin).strftime(FORMATO_LOCAL),
            ]
        )
    return dict(ocupaciones)


def contexto_cuadricula(espacios):
    """
    'espacios' es el queryset de espacios que el usuario puede reservar
    (el del campo 'espacio' de ReservaForm). Devuelve el dict con 'grupos' y
    'ocupaciones' para mezclar en el contexto del template.
    """
    from .models import Reserva  # import local: evita ciclos al cargar las apps

    espacios = list(
        espacios.select_related("zona", "zona__facultad", "tipo_estado").order_by(
            "zona__nombre", "numero"
        )
    )

    # Mismo criterio que ReservaForm.clean(): cuentan todas las reservas que
    # no están Canceladas. Las que ya terminaron no pueden pisar una reserva
    # nueva (que no puede ser en el pasado), así que no se envían.
    filas = (
        Reserva.objects.filter(
            espacio_id__in=[e.id for e in espacios], fecha_fin__gte=timezone.now()
        )
        .exclude(tipo_estado_reserva__nombre_estado_reserva="Cancelada")
        .values_list("espacio_id", "fecha_inicio", "fecha_fin")
    )

    return {"grupos": armar_grupos(espacios), "ocupaciones": armar_ocupaciones(filas)}
