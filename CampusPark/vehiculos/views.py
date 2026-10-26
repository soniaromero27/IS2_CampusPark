from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
 
from campuspark.paginacion import paginar
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


@login_required
def editar_vehiculo_view(request, pk):
    """Editar los datos de un vehículo PROPIO (uno ajeno da 404)."""
    vehiculo = get_object_or_404(Vehiculo, pk=pk, usuario=request.user.perfil)
    matricula_original = vehiculo.matricula  # antes de que el form pise el objeto
    if request.method == "POST":
        form = VehiculoForm(request.POST, instance=vehiculo)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Se guardaron los cambios del vehículo {vehiculo.matricula}."
            )
            return redirect("vehiculos:lista")
    else:
        form = VehiculoForm(instance=vehiculo)
    return render(
        request,
        "vehiculos/editar.html",
        {"form": form, "matricula": matricula_original},
    )

@personal_requerido
def lista_todos_vehiculos_view(request):
    """
    Consultar todos los vehículos registrados, con su dueño: sólo
    Personal de Estacionamiento o Administrador. Admite búsqueda por
    ?q=... sobre matrícula, marca, modelo, tipo, cédula verde, chassis
    y nombre/apellido del dueño.
    """
    
    campos_orden = {
        "matricula": ["matricula"],
        "tipo": ["tipo_vehiculo"],
        "marca": ["marca"],
        "modelo": ["modelo"],
        "color": ["color"],
        "anho": ["anho"],
        "usuario": ["usuario__apellido", "usuario__nombre"],
        "fecha_registro": ["fecha_registro"],
    }

    orden = request.GET.get("orden", "fecha_registro")
    if orden not in campos_orden:
        orden = "fecha_registro"

    direccion = request.GET.get("dir", "asc")
    if direccion not in ("asc", "desc"):
        direccion = "asc"

    campos = campos_orden[orden]
    if direccion == "desc":
        campos = [f"-{c}" for c in campos]
    
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
    vehiculos = vehiculos.order_by(*campos)
    
    return render(request, "vehiculos/lista_todos.html", {**paginar(request, vehiculos, "vehiculos"), "orden": orden, "dir": direccion, "q": q})