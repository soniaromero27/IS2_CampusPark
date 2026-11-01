
from .models import SolicitudRegistro
 
 
def solicitudes_pendientes(request):
    """Cantidad de solicitudes de registro pendientes, sólo para Administradores (globo de notificaciones)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    perfil = getattr(user, "perfil", None)
    if perfil is None or not perfil.es_administrador:
        return {}
    return {"solicitudes_pendientes": SolicitudRegistro.objects.count()}