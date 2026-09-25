# El decorador vive ahora en usuarios.decorators (depende de Usuario.es_personal).
# Se re-exporta acá para no romper los `from .decorators import personal_requerido`
# que ya existen en estacionamiento/views.py.
from usuarios.decorators import admin_requerido, personal_requerido  # noqa: F401