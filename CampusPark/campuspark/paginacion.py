"""
Paginación común a todas las listas del sitio (10 elementos por página).

Uso en una vista: en el diccionario de contexto del render, reemplazar la
entrada de la lista, por ejemplo  "usuarios": usuarios  por:

    **paginar(request, usuarios, "usuarios"),

y en el template agregar, al final del bloque content:

    {% include "_paginacion.html" %}

El template sigue recorriendo la lista con el mismo nombre de siempre
({% for u in usuarios %}), porque la página de Django se recorre igual que
una lista. La lista tiene que venir ORDENADA (order_by) para que las páginas
sean estables.
"""
from django.core.paginator import Paginator

POR_PAGINA = 10


def paginar(request, items, nombre, por_pagina=POR_PAGINA):
    """
    Pagina 'items' (queryset o lista) según el parámetro ?pagina=N de la URL.
    Un número inválido o fuera de rango no da error: se usa la primera o la
    última página. Devuelve un dict para mezclar en el contexto del template:

      <nombre>        la página actual (se recorre como la lista original)
      page_obj        la misma página, con los datos para armar los controles
      qs_pagina       el resto de los parámetros de la URL (búsqueda, orden,
                      filtros...) para conservarlos al cambiar de página
      rango_paginas   números de página a mostrar; None marca un salto "…"
    """
    paginator = Paginator(items, por_pagina)
    page_obj = paginator.get_page(request.GET.get("pagina"))

    params = request.GET.copy()
    params.pop("pagina", None)

    rango = [
        p if isinstance(p, int) else None
        for p in paginator.get_elided_page_range(
            page_obj.number, on_each_side=2, on_ends=1
        )
    ]

    return {
        nombre: page_obj,
        "page_obj": page_obj,
        "qs_pagina": params.urlencode(),
        "rango_paginas": rango,
    }
