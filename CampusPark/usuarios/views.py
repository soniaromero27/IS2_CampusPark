from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render

from .decorators import personal_requerido
from .forms import RegistroUsuarioForm, UsuarioEditForm
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


@login_required
def editar_perfil_view(request):
    """
    Cada usuario puede editar su propio perfil (nombre, apellido,
    documento, fecha de nacimiento, correo, teléfono, n° de licencia).
    No se puede cambiar el tipo de usuario ni el username de login.
    """
    perfil = request.user.perfil
    if request.method == "POST":
        form = UsuarioEditForm(request.POST, instance=perfil)
        if form.is_valid():
            form.save()
            return redirect("usuarios:perfil")
    else:
        form = UsuarioEditForm(instance=perfil)
    return render(request, "usuarios/perfil_editar.html", {"form": form})


@personal_requerido
def lista_usuarios_view(request):
    """
    Consultar todos los usuarios registrados: sólo Personal de
    Estacionamiento o Administrador. Admite búsqueda por ?q=... sobre
    nombre, apellido, documento, correo y tipo de usuario.
    """
    campos_orden = {
        "nombre": ["nombre"],
        "apellido": ["apellido"],
        "documento": ["documento"],
        "correo": ["correo"],
        "telefono": ["telefono"],
        "tipo": ["tipo_id"],
        "facultad": ["facultad_id"],
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
    usuarios = Usuario.objects.select_related("user", "tipo", "facultad").order_by("apellido", "nombre")
    if q:
        usuarios = usuarios.filter(
            Q(nombre__icontains=q)
            | Q(apellido__icontains=q)
            | Q(documento__icontains=q)
            | Q(correo__icontains=q)
            | Q(tipo__nombre__icontains=q)
            | Q(facultad__nombre__icontains=q)
        )
        
    usuarios = usuarios.order_by(*campos)
    
    return render(request, "usuarios/usuarios_lista.html", {"usuarios": usuarios, "orden": orden, "dir": direccion, "q": q})