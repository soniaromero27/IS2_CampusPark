from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def personal_requerido(view_func):
    """
    Restringe el acceso a usuarios cuyo perfil sea de tipo Personal de
    Estacionamiento o Administrador (Usuario.es_personal). Requiere estar
    logueado (aplica login_required primero) y devuelve 403 si no cumple.
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        perfil = getattr(request.user, "perfil", None)
        if perfil is None or not perfil.es_personal:
            raise PermissionDenied(
                "Sólo el personal de estacionamiento (Personal de Estacionamiento "
                "o Administrador) puede acceder a esta función."
            )
        return view_func(request, *args, **kwargs)

    return _wrapped_view
