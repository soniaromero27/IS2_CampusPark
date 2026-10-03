# CampusPark
Trabajo Grupal de Ingenieria de Software II

CampusPark — Sistema de Gestión de Estacionamiento para campus universitario

Descripción

CampusPark es un sistema destinado a gestionar usuarios, vehículos y espacios de estacionamiento dentro de un campus universitario, incluyendo reservas, control de ingresos y salidas, reglas de acceso, tarifas y reportes.

Objetivo

Centralizar y mejorar la administración del estacionamiento universitario.

---

## Funcionalidades

| Módulo | Descripción |
| --- | --- |
| **Usuarios** | Registro, inicio y cierre de sesión, perfil editable y listado de usuarios (con búsqueda y ordenamiento). Cada usuario tiene un tipo (Docente, Estudiante, Funcionario, Externo, Personal de estacionamiento o Administrador) y, según el tipo, una facultad. |
| **Vehículos** | Registro de vehículos por usuario, con validación de matrícula duplicada. El personal puede consultar todos los vehículos registrados. |
| **Zonas y espacios** | Alta y edición de zonas con facultad opcional (zona pública si no tiene) y tipos de usuario permitidos. Creación de espacios de forma masiva con numeración automática. |
| **Reservas** | Reserva de espacios por día y franja horaria, con control de solapamientos y restricción por facultad y tipo de usuario. Cancelación de reservas propias. |
| **Ingresos y salidas** | Registro de ingreso por chapa (aunque no esté registrada), asignación automática del espacio reservado o reasignación en la misma zona, y registro de salida con ticket. |
| **Tarifas y cobro** | Configuración de tarifas por tipo de usuario y cálculo automático del monto a cobrar al registrar la salida (por hora, redondeado hacia arriba, con mínimo de 1 hora). |

### Roles y permisos

| Rol | Acceso |
| --- | --- |
| Usuario autenticado (Docente, Estudiante, Funcionario, Externo) | Perfil, vehículos propios y reservas propias. |
| Personal de estacionamiento | Lo anterior, más ingresos y salidas, todas las reservas, listado de usuarios y vehículos, y tarifas. |
| Administrador | Lo anterior, más la gestión de zonas y espacios. |

Las zonas con facultad solo pueden ser usadas por usuarios de esa facultad (y, si la zona define tipos permitidos, solo por esos tipos). Los usuarios Externos y las chapas no registradas solo pueden usar zonas sin facultad.

## Tecnologías

- Python 3.12 o superior
- Django 6.1
- PostgreSQL
- python-decouple (variables de entorno)
- HTML y CSS con plantillas de Django

## Arquitectura

Monolito modular en capas, con una aplicación Django por dominio:

| Aplicación | Responsabilidad |
| --- | --- |
| `usuarios` | Autenticación, perfiles, tipos de usuario y decoradores de permisos. |
| `vehiculos` | Vehículos de los usuarios. |
| `universidad` | Facultades. |
| `estacionamiento` | Zonas, espacios, reservas y movimientos (ingresos y salidas). |
| `reglas` | Tarifas y reglas de acceso. |

## Estructura del repositorio

```
IS2_CampusPark/
├── CampusPark/            # Proyecto Django
│   ├── campuspark/        # Configuración (settings, urls, wsgi, asgi)
│   ├── templates/         # Plantillas base (base.html, 404.html)
│   ├── usuarios/
│   ├── vehiculos/
│   ├── universidad/
│   ├── estacionamiento/
│   ├── reglas/
│   └── manage.py
├── Diagramas/             # DER y diagramas de arquitectura
├── Informes/              # Informes de cada sprint
└── README.md
```

## Instalación y ejecución

### 1. Clonar el repositorio

```bash
git clone https://github.com/soniaromero27/IS2_CampusPark.git
cd IS2_CampusPark/CampusPark
```

### 2. Crear el entorno virtual e instalar dependencias

```bash
python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate
pip install django python-decouple "psycopg[binary]" django-loaddata
```

> Si el repositorio incluye un `requirements.txt`, usar `pip install -r requirements.txt`.

### 3. Crear la base de datos

Crear una base de datos vacía en PostgreSQL, por ejemplo:

```sql
CREATE DATABASE campuspark;
```

### 4. Configurar las variables de entorno

Crear un archivo `.env` en la carpeta `CampusPark/` (junto a `manage.py`). Este archivo está en `.gitignore` y no debe subirse al repositorio.

```env
DB_NAME=campuspark
DB_USER=tu_usuario
DB_PASSWORD=tu_contraseña
DB_HOST=localhost
DB_PORT=5432
```

### 5. Aplicar migraciones y cargar datos iniciales

```bash
python manage.py migrate
python manage.py loaddata tipo_usuario tipo_estado tipo_estado_reserva zona_espacio
```

Los datos iniciales incluyen los tipos de usuario, los estados de espacios y reservas, y una zona de ejemplo con 10 espacios. Las facultades se pueden cargar desde el panel de administración (`/admin/`).

### 6. Crear el primer administrador

```bash
python manage.py createsuperuser
```

Esto crea el acceso al panel `/admin/`. Para usar la aplicación con rol de Administrador, registrar un usuario desde `/usuarios/registro/` eligiendo el tipo «Administrador», o crear su perfil de usuario desde el panel de administración.

### 7. Iniciar el servidor

```bash
python manage.py runserver
```

La aplicación queda disponible en http://127.0.0.1:8000/usuarios/login/.

## Rutas principales

| Ruta | Descripción |
| --- | --- |
| `/usuarios/registro/` | Registro de usuario |
| `/usuarios/login/` | Inicio de sesión |
| `/usuarios/perfil/` | Perfil del usuario |
| `/usuarios/lista/` | Listado de usuarios (personal) |
| `/vehiculos/` | Mis vehículos |
| `/vehiculos/todos/` | Todos los vehículos (personal) |
| `/estacionamiento/reservas/` | Mis reservas |
| `/estacionamiento/reservas/todas/` | Todas las reservas (personal) |
| `/estacionamiento/movimientos/` | Ingresos y salidas (personal) |
| `/estacionamiento/zonas/` | Zonas y espacios (administrador) |
| `/reglas/` | Tarifas (personal) |
| `/admin/` | Panel de administración de Django |

## Gestión del proyecto

- **Backlog en Jira:** https://is2unapark.atlassian.net/jira/software/projects/SCRUM/boards/1/backlog
- **Metodología:** Scrum, con cinco sprints y entregas incrementales.
- **Control de versiones:** Git y GitHub.

## Equipo (Grupo 3)

- Sonia Nila Romero Centurión
- Rodrigo Fabián Ovelar
- Ranulfo Jesús Benítez

**Profesora:** Lic. Lilian Mercedes Raquel Rocío Riveros Valdez

Universidad Nacional de Asunción — Facultad Politécnica — Ingeniería de Software II — San Lorenzo, 2026.
