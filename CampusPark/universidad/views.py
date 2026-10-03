from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import admin_requerido

from .forms import FacultadForm
from .models import Facultad


@admin_requerido
def lista_facultades_view(request):
    """
    Ver todas las facultades, con cuántas zonas y usuarios tiene cada
    una. Sólo Administrador. Admite búsqueda por ?q=... sobre nombre
    y descripción.
    """
    q = request.GET.get("q", "").strip()
    facultades = Facultad.objects.annotate(
        cantidad_zonas=Count("zonas", distinct=True),
        cantidad_usuarios=Count("usuarios", distinct=True),
    ).order_by("nombre")
    if q:
        facultades = facultades.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))
    return render(request, "universidad/facultades_lista.html", {"facultades": facultades, "q": q})


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