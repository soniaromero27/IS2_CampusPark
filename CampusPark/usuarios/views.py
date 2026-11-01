from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Q, Count
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST

from .decorators import personal_requerido, admin_requerido
from .forms import RegistroUsuarioForm, UsuarioEditForm, CambiarPasswordForm, TipoUsuarioForm
from .models import Usuario, SolicitudRegistro, TipoUsuario

from campuspark.paginacion import paginar


def registro_view(request):
    """
    HU01 - Registrar usuario. Los Externos se crean y entran al instante; los
    demás tipos quedan como solicitud pendiente hasta que un Administrador la apruebe.
    """
    if request.method == "POST":
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            resultado = form.save()
            if form.requiere_aprobacion:
                return redirect("usuarios:registro_pendiente")
            login(request, resultado)  # inicia sesión automáticamente (sólo Externos)
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
    
    return render(request, "usuarios/usuarios_lista.html", {**paginar(request, usuarios, "usuarios"), "orden": orden, "dir": direccion, "q": q})
    

class CambiarPasswordView(SuccessMessageMixin, PasswordChangeView):
    """
    Cambiar la propia contraseña (requiere estar logueado y conocer la actual).
    Al terminar, la sesión sigue abierta y se vuelve al perfil.
    """
    form_class = CambiarPasswordForm
    template_name = "usuarios/password_cambiar.html"
    success_url = reverse_lazy("usuarios:perfil")
    success_message = "Tu contraseña se cambió correctamente."
 

def registro_pendiente_view(request):
    """Aviso al solicitante: su pedido espera la aprobación de un Administrador."""
    return render(request, "usuarios/registro_pendiente.html")
 
 
@admin_requerido
def lista_solicitudes_view(request):
    """Notificaciones: todos los perfiles que pidieron crearse y esperan aprobación (más antiguos primero)."""
    solicitudes = SolicitudRegistro.objects.select_related("tipo", "facultad").order_by(
        "fecha_solicitud"
    )
    return render(
        request,
        "usuarios/solicitudes_lista.html",
        {**paginar(request, solicitudes, "solicitudes")},
    )
 
 
@admin_requerido
@require_POST
def aprobar_solicitud_view(request, pk):
    """Aprueba una solicitud: se crea el usuario y su perfil, y la solicitud desaparece."""
    try:
        with transaction.atomic():
            solicitud = get_object_or_404(SolicitudRegistro.objects.select_for_update(), pk=pk)
            perfil = solicitud.aprobar()
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        messages.success(
            request,
            f"Se aprobó el perfil de {perfil.nombre} {perfil.apellido} ({perfil.tipo}). "
            f"Ya puede ingresar con el usuario '{perfil.user.username}'.",
        )
    return redirect("usuarios:solicitudes")
 
 
@admin_requerido
@require_POST
def rechazar_solicitud_view(request, pk):
    """Rechaza una solicitud: se borran todos los datos preliminares."""
    with transaction.atomic():
        solicitud = get_object_or_404(SolicitudRegistro.objects.select_for_update(), pk=pk)
        nombre = f"{solicitud.nombre} {solicitud.apellido}"
        solicitud.delete()
    messages.success(request, f"Se rechazó la solicitud de {nombre} y se eliminaron todos sus datos.")
    return redirect("usuarios:solicitudes")
 

@admin_requerido
def lista_tipos_view(request):
    """Todos los tipos de usuario, con su rol y cuántos usuarios tiene cada uno. Sólo Administrador."""
    tipos = TipoUsuario.objects.annotate(cantidad_usuarios=Count("usuarios")).order_by("nombre")
    return render(
        request,
        "usuarios/tipos_lista.html",
        {**paginar(request, tipos, "tipos"), "externo_defecto": TipoUsuario.externo_por_defecto()},
    )
 
 
@admin_requerido
def crear_tipo_view(request):
    """Alta de un tipo de usuario, asignándole uno de los 4 roles. Sólo Administrador."""
    if request.method == "POST":
        form = TipoUsuarioForm(request.POST)
        if form.is_valid():
            tipo = form.save()
            messages.success(request, f"Se creó el tipo de usuario '{tipo.nombre}' ({tipo.get_rol_display()}).")
            return redirect("usuarios:tipos_lista")
    else:
        form = TipoUsuarioForm()
    return render(request, "usuarios/tipo_form.html", {"form": form})
 
 
@admin_requerido
def editar_tipo_view(request, pk):
    """
    Editar un tipo (nombre, descripción, rol). Si pasa a rol Externo, sus usuarios
    pierden la facultad (los Externos no tienen). Sólo Administrador.
    """
    tipo = get_object_or_404(TipoUsuario, pk=pk)
    rol_anterior = tipo.rol
    if request.method == "POST":
        form = TipoUsuarioForm(request.POST, instance=tipo, perfil_actual=request.user.perfil)
        if form.is_valid():
            with transaction.atomic():
                tipo = form.save()
                if rol_anterior != tipo.rol:
                    if tipo.rol == TipoUsuario.Rol.EXTERNO:
                        n = tipo.usuarios.update(facultad=None)
                        if n:
                            messages.info(request, f"{n} usuario(s) de este tipo perdieron su facultad por ser Externos.")
                    elif tipo.rol == TipoUsuario.Rol.UNIVERSITARIO:
                        n = tipo.usuarios.filter(facultad__isnull=True).count()
                        if n:
                            messages.warning(
                                request,
                                f"{n} usuario(s) de este tipo no tienen facultad: sólo podrán usar zonas "
                                "públicas hasta que la completen en su perfil.",
                            )
            messages.success(request, f"Se guardó el tipo de usuario '{tipo.nombre}'.")
            return redirect("usuarios:tipos_lista")
    else:
        form = TipoUsuarioForm(instance=tipo, perfil_actual=request.user.perfil)
    return render(request, "usuarios/tipo_form.html", {"form": form, "tipo": tipo})
 
 
@admin_requerido
def eliminar_tipo_view(request, pk):
    """
    Eliminar un tipo: todos los usuarios que lo tenían pasan a ser Externos (tipo
    Externo por defecto) y pierden su facultad. Hay casos que lo impiden (ver
    TipoUsuario.motivos_bloqueo_eliminar). Sólo Administrador.
    """
    perfil = request.user.perfil
    if request.method == "POST":
        with transaction.atomic():
            tipo = get_object_or_404(TipoUsuario.objects.select_for_update(), pk=pk)
            bloqueos = tipo.motivos_bloqueo_eliminar(perfil)
            if bloqueos:
                for motivo in bloqueos:
                    messages.error(request, f"No se puede eliminar '{tipo.nombre}': {motivo}")
                return redirect("usuarios:tipos_lista")
            externo = TipoUsuario.externo_por_defecto(crear=True)
            movidos = Usuario.objects.filter(tipo=tipo).update(tipo=externo, facultad=None)
            nombre = tipo.nombre
            tipo.delete()
        messages.success(
            request,
            f"Se eliminó el tipo '{nombre}'. {movidos} usuario(s) pasaron a ser '{externo.nombre}'.",
        )
        return redirect("usuarios:tipos_lista")
 
    tipo = get_object_or_404(TipoUsuario, pk=pk)
    return render(
        request,
        "usuarios/tipo_eliminar.html",
        {
            "tipo": tipo,
            "cantidad": tipo.usuarios.count(),
            "bloqueos": tipo.motivos_bloqueo_eliminar(perfil),
            "advertencias": tipo.advertencias_eliminar(),
            "externo": TipoUsuario.externo_por_defecto(),
        },
    )
 