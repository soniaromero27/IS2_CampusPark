from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .decorators import personal_requerido
from .forms import RegistroUsuarioForm
from .models import Usuario
 


def registro_view(request):
    """HU01 - Registrar usuario: alta con tipo de usuario asociado."""
    if request.method == "POST":
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # inicia sesión automáticamente tras el registro
            return redirect("usuarios:perfil")
    else:
        form = RegistroUsuarioForm()
    return render(request, "usuarios/registro.html", {"form": form})


@login_required
def perfil_view(request):
    """Pantalla de confirmación: muestra los datos del usuario registrado."""
    perfil = request.user.perfil
    return render(request, "usuarios/perfil.html", {"perfil": perfil})


@personal_requerido
def lista_usuarios_view(request):
    """
    Consultar todos los usuarios registrados: sólo Personal de
    Estacionamiento o Administrador.
    """
    usuarios = Usuario.objects.select_related("user", "tipo").order_by(
        "apellido", "nombre"
    )
    return render(request, "usuarios/usuarios_lista.html", {"usuarios": usuarios})
 