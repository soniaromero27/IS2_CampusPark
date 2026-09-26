from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render

from usuarios.decorators import personal_requerido

from .forms import VehiculoForm
from .models import Vehiculo


@login_required
def lista_vehiculos_view(request):
    """Flujo completo HU03: consulta de vehículos del usuario logueado."""
    vehiculos = Vehiculo.objects.filter(usuario=request.user.perfil)
    return render(request, "vehiculos/lista.html", {"vehiculos": vehiculos})


@login_required
def agregar_vehiculo_view(request):
    """HU03 - Registrar vehículo asociado al usuario autenticado."""
    if request.method == "POST":
        form = VehiculoForm(request.POST)
        if form.is_valid():
            vehiculo = form.save(commit=False)
            vehiculo.usuario = request.user.perfil
            vehiculo.save()
            return redirect("vehiculos:lista")
    else:
        form = VehiculoForm()
    return render(request, "vehiculos/agregar.html", {"form": form})


@personal_requerido
def lista_todos_vehiculos_view(request):
    """
    Consultar todos los vehículos registrados, con su dueño: sólo
    Personal de Estacionamiento o Administrador. Admite búsqueda por
    ?q=... sobre matrícula, marca, modelo, tipo, cédula verde, chassis
    y nombre/apellido del dueño.
    """
    q = request.GET.get("q", "").strip()
    vehiculos = Vehiculo.objects.select_related("usuario").order_by(
        "usuario__apellido", "usuario__nombre", "matricula"
    )
    if q:
        vehiculos = vehiculos.filter(
            Q(matricula__icontains=q)
            | Q(marca__icontains=q)
            | Q(modelo__icontains=q)
            | Q(tipo_vehiculo__icontains=q)
            | Q(cedula_verde__icontains=q)
            | Q(chassis__icontains=q)
            | Q(usuario__nombre__icontains=q)
            | Q(usuario__apellido__icontains=q)
        )
    return render(request, "vehiculos/lista_todos.html", {"vehiculos": vehiculos, "q": q})