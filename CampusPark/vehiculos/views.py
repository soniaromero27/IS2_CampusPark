from django.contrib.auth.decorators import login_required
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
    Personal de Estacionamiento o Administrador.
    """
    vehiculos = Vehiculo.objects.select_related("usuario").order_by(
        "usuario__apellido", "usuario__nombre", "matricula"
    )
    return render(request, "vehiculos/lista_todos.html", {"vehiculos": vehiculos})
 