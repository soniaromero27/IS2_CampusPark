from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from campuspark.paginacion import paginar

from usuarios.decorators import admin_requerido

from .forms import FacultadForm
from .models import Facultad


@admin_requerido
def lista_facultades_view(request):
    """
    Ver todas las facultades, con cuántas zonas y usuarios tiene cada una. Sólo
    Administrador. Admite búsqueda por ?q=... sobre nombre y descripción y se puede
    ordenar por cualquier columna con ?orden=<campo>&dir=<asc|desc>.
    """
    campos_orden = {
        "nombre": ["nombre"],
        "descripcion": ["descripcion", "nombre"],
        "zonas": ["cantidad_zonas", "nombre"],
        "usuarios": ["cantidad_usuarios", "nombre"],
    }
 
    orden = request.GET.get("orden", "nombre")
    if orden not in campos_orden:
        orden = "nombre"
 
    direccion = request.GET.get("dir", "asc")
    if direccion not in ("asc", "desc"):
        direccion = "asc"
 
    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]
 
    q = request.GET.get("q", "").strip()
    facultades = Facultad.objects.annotate(
        cantidad_zonas=Count("zonas", distinct=True),
        cantidad_usuarios=Count("usuarios", distinct=True),
    )
    if q:
        facultades = facultades.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))
    facultades = facultades.order_by(*campos)
 
    return render(
        request,
        "universidad/facultades_lista.html",
        {**paginar(request, facultades, "facultades"), "orden": orden, "dir": direccion, "q": q},
    )
 
@admin_requerido
def crear_facultad_view(request):
    """Alta de una facultad. Sólo Administrador."""
    if request.method == "POST":
        form = FacultadForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("universidad:facultades_lista")
    else:
        form = FacultadForm()
    return render(request, "universidad/facultad_form.html", {"form": form})


@admin_requerido
def editar_facultad_view(request, pk):
    """Modificar una facultad existente. Sólo Administrador."""
    facultad = get_object_or_404(Facultad, pk=pk)
    if request.method == "POST":
        form = FacultadForm(request.POST, instance=facultad)
        if form.is_valid():
            form.save()
            return redirect("universidad:facultades_lista")
    else:
        form = FacultadForm(instance=facultad)
    return render(
        request, "universidad/facultad_form.html", {"form": form, "facultad": facultad}
    )