# CampusPark

Trabajo Grupal de Ingeniería de Software II

**CampusPark — Sistema de Gestión de Estacionamiento para campus universitario**

## Descripción

CampusPark es un sistema web para gestionar usuarios, vehículos y espacios de estacionamiento dentro de un campus universitario. Incluye reservas con control de horarios y solapamientos, control de ingresos y salidas por patente, restricciones de acceso por facultad y tipo de usuario, tarifas con cálculo automático de cobro, reglamento con horario de apertura y cierre, y herramientas de administración.

**Objetivo:** centralizar y mejorar la administración del estacionamiento universitario.

---

## Tabla de contenidos

1. [Funcionalidades](#funcionalidades)
2. [Roles y permisos](#roles-y-permisos)
3. [Reglas de negocio](#reglas-de-negocio)
4. [Tecnologías](#tecnologías)
5. [Arquitectura](#arquitectura)
6. [Estructura del repositorio](#estructura-del-repositorio)
7. [Instalación y ejecución](#instalación-y-ejecución)
8. [Configuración inicial del sistema](#configuración-inicial-del-sistema)
9. [Rutas principales](#rutas-principales)
10. [Gestión del proyecto](#gestión-del-proyecto)
11. [Equipo](#equipo-grupo-3)

---

## Funcionalidades

| Módulo | Descripción |
| --- | --- |
| **Usuarios** | Registro con inicio de sesión automático, login y logout, perfil propio visible y editable (nombre, apellido, documento, fecha de nacimiento, correo, teléfono, n° de licencia y facultad). Listado de usuarios para el personal, con búsqueda, ordenamiento por columna y paginación. Cada usuario tiene un tipo (Docente, Estudiante, Funcionario, Externo, Personal de estacionamiento o Administrador) y, según el tipo, una facultad. |
| **Vehículos** | Registro de vehículos por usuario (matrícula, tipo, cédula verde, marca, modelo, color, año y chassis), con validación de matrícula duplicada. El personal puede consultar todos los vehículos con su dueño, con búsqueda y ordenamiento. |
| **Facultades** | Alta, edición y listado de facultades, con la cantidad de zonas y usuarios de cada una. Solo Administrador. |
| **Zonas y espacios** | Alta y edición de zonas con facultad opcional (sin facultad = zona pública) y tipos de usuario permitidos. Creación de espacios al crear o editar una zona, o de forma masiva con numeración automática. Edición manual de un espacio (zona, número y estado) por el Administrador. |
| **Mapa de espacios** | Vista de todos los espacios en **lista** o en **cuadrícula** (zonas desplegables con un cuadro por espacio, coloreado según su estado: Libre, Ocupado, Reservado o Fuera de servicio). Búsqueda y ordenamiento. El personal ve además la patente del vehículo estacionado. |
| **Reservas** | Reserva de un espacio por día y franja horaria, eligiendo el lugar en una cuadrícula que muestra en tiempo real qué espacios están disponibles para el horario elegido. Control de solapamientos, restricción por facultad y tipo de usuario, y validación contra el horario del reglamento. Consulta de reservas propias y cancelación de las que están pendientes. El personal consulta todas las reservas. Ambos listados admiten búsqueda, ordenamiento y filtro por rango de fechas. |
| **Ingresos y salidas** | Registro de ingreso por patente (aunque no esté registrada). Si el dueño tiene una reserva vigente se le asigna automáticamente su espacio; si está ocupado, se reasigna a otro libre de la misma zona. Registro de salida con confirmación, cálculo del monto y recibo. |
| **Tarifas y cobro** | Configuración de tarifas por tipo de usuario con fecha de vigencia. Al registrar la salida se calcula el monto a cobrar (por hora, redondeando hacia arriba, con un mínimo de 1 hora). Las patentes no registradas se cobran con la tarifa del tipo «Externo». Las tarifas se pueden filtrar por tipo de usuario. |
| **Reglamento y horarios** | Texto del reglamento del estacionamiento y horario de apertura y cierre, visibles para todos los usuarios con sesión iniciada. Solo el Administrador los edita. Las reservas deben quedar dentro de ese horario; los ingresos y salidas no están sujetos a él. |
| **Página de inicio** | Portada pública con la presentación del sistema, sus funcionalidades, cómo funciona y el horario del estacionamiento. |
| **Dashboards, tickets y solicitudes** | El menú de la aplicación incluye un dashboard de cobros, un dashboard de ocupación, el pago de tickets, el historial «Mis movimientos», el listado de tickets (personal), las solicitudes de registro pendientes de aprobación y la gestión de tipos de usuario (Administrador). Ver la nota al final de esta sección. |
| **Panel de administración** | Panel de Django en `/admin/` con todos los modelos registrados (usuarios, vehículos, zonas, espacios, reservas, movimientos, tarifas, reglamento, etc.). |

> **Nota:** los últimos elementos del menú (dashboards, pago de tickets, mis movimientos, tickets, solicitudes y tipos de usuario) figuran en la plantilla `base.html`, pero las vistas y URLs correspondientes deben estar presentes en el código para que esas pantallas funcionen. Conviene completar o ajustar esta fila de la tabla según el estado real de esas funciones en cada entrega.

### Otras características técnicas

- Paginación común de 10 elementos por página en todos los listados.
- Fechas y horas con formato `dd/mm/aaaa` y `HH:MM`; números con punto como separador de miles.
- Zona horaria `America/Asuncion`; los montos se muestran en guaraníes (Gs.).
- Página 404 personalizada.

---

## Roles y permisos

| Rol | Acceso |
| --- | --- |
| **Visitante (sin sesión)** | Página de inicio, registro e inicio de sesión. |
| **Usuario autenticado** (Docente, Estudiante, Funcionario, Externo) | Perfil, vehículos propios, reservas propias, mapa de espacios, tarifas y reglamento. |
| **Personal de estacionamiento** | Todo lo anterior, más ingresos y salidas, todas las reservas, listado de usuarios y de vehículos, patentes en el mapa de espacios, y alta y edición de tarifas. |
| **Administrador** | Todo lo anterior, más la gestión de zonas, espacios, facultades y reglamento (texto y horarios), y el acceso a `/admin/`. |

Las vistas protegidas usan los decoradores `personal_requerido` y `admin_requerido` (`usuarios/decorators.py`), que devuelven un error 403 si el usuario no tiene el rol necesario.

---

## Reglas de negocio

### Acceso a zonas

- Una **zona sin facultad** es pública: la puede usar cualquier usuario.
- Una **zona con facultad** solo la pueden usar usuarios de esa facultad y, si la zona define tipos de usuario permitidos, solo esos tipos. Si no define ninguno, cualquier tipo de esa facultad puede entrar.
- Los usuarios **Externos** y las **patentes no registradas** solo pueden usar zonas sin facultad.
- Los tipos Docente, Estudiante y Funcionario **deben** indicar una facultad; los Externos **no pueden** tener una.

### Reservas

- Se reserva un único día, con hora de inicio y hora de fin posterior a la de inicio.
- No se puede reservar una fecha ni un horario que ya pasó.
- La reserva debe estar dentro del horario de apertura y cierre del reglamento (si ya fue cargado).
- No se puede reservar un espacio fuera de servicio.
- No se aceptan reservas que se solapen con otra no cancelada del mismo espacio.
- Estados de una reserva: **Pendiente**, **Confirmada**, **Cancelada** y **Finalizada**.
- Si la reserva es para hoy, el espacio pasa a **Reservado** de inmediato; si es para un día futuro, lo activa la tarea programada al empezar ese día.
- Al cancelar una reserva, el espacio vuelve a **Libre**.

### Ingresos y salidas

- Se ingresa solo la patente. Si coincide con un vehículo registrado, el movimiento queda vinculado a su dueño; si no, se registra igual como «No registrado», sin crear vehículos ni usuarios.
- Una patente no puede tener dos ingresos abiertos a la vez.
- Si el dueño tiene una reserva pendiente y vigente en ese momento, se usa el espacio reservado y la reserva pasa a **Confirmada**.
- Si ese espacio está ocupado, se reasigna a otro libre de la misma zona. Si no hay ninguno, el personal debe elegir otro espacio a mano (que puede ser de otra zona, respetando las restricciones de facultad).
- Si no hay reserva vigente, el espacio se elige a mano entre los libres.
- Al registrar la salida, el espacio vuelve a **Libre** y la reserva confirmada (si había) pasa a **Finalizada**.
- No se puede cambiar a mano el estado de un espacio que tiene un vehículo estacionado: primero hay que registrar la salida.

### Cobro

- Monto = horas × valor por hora de la tarifa vigente para el tipo de usuario del dueño.
- Las horas se redondean hacia arriba, con un mínimo de 1.
- Se usa la tarifa con vigencia más reciente que no supere la fecha de salida.
- Si no hay una tarifa configurada para ese tipo, se informa que no se puede calcular el monto.

### Estados de los espacios

**Libre**, **Ocupado**, **Reservado** y **Fuera de servicio**.

---

## Tecnologías

- Python 3.12 o superior
- Django 6.1
- PostgreSQL
- python-decouple (variables de entorno)
- django-loaddata
- HTML y CSS con plantillas de Django (iconos Material Symbols de Google Fonts)

## Arquitectura

Monolito modular en capas, con una aplicación Django por dominio:

| Aplicación | Responsabilidad |
| --- | --- |
| `campuspark` | Configuración del proyecto, página de inicio, paginación común y formatos de fecha y número. |
| `usuarios` | Autenticación, perfiles, tipos de usuario y decoradores de permisos. |
| `vehiculos` | Vehículos de los usuarios. |
| `universidad` | Facultades. |
| `estacionamiento` | Zonas, espacios, reservas y movimientos (ingresos y salidas) y cuadrícula de espacios. |
| `reglas` | Tarifas, reglamento con su horario y reglas de acceso. |

## Estructura del repositorio

```
IS2_CampusPark/
├── CampusPark/                # Proyecto Django
│   ├── campuspark/            # Configuración (settings, urls, wsgi, asgi),
│   │   │                      # paginacion.py y formatos de fecha/número
│   │   └── formats/
│   ├── templates/             # Plantillas globales (base.html, inicio.html,
│   │                          # 404.html, _paginacion.html)
│   ├── usuarios/
│   ├── vehiculos/
│   ├── universidad/
│   ├── estacionamiento/       # Incluye cuadricula.py y fixtures/
│   ├── reglas/
│   ├── run.bat                # Atajo para iniciar el servidor en Windows
│   └── manage.py
├── Diagramas/                 # DER y diagramas de arquitectura
├── Informes/                  # Informes de cada sprint
└── README.md
```

---

## Instalación y ejecución

### Requisitos previos

- Python 3.12 o superior
- PostgreSQL instalado y en ejecución
- Git

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

Crear un archivo `.env` en la carpeta `CampusPark/` (junto a `manage.py`). Este archivo está en `.gitignore` y **no debe subirse** al repositorio.

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

Los datos iniciales incluyen:

| Fixture | Contenido |
| --- | --- |
| `tipo_usuario` | Docente, Estudiante, Funcionario, Externo, Administrador y Personal de estacionamiento. |
| `tipo_estado` | Estados de espacio: Libre, Ocupado, Reservado y Fuera de servicio. |
| `tipo_estado_reserva` | Estados de reserva: Pendiente, Confirmada, Cancelada y Finalizada. |
| `zona_espacio` | Una zona de ejemplo («Zona A») con 10 espacios libres. |

### 6. Crear el primer administrador

```bash
python manage.py createsuperuser
```

Esto crea el acceso al panel `/admin/`. Para usar la aplicación con rol de **Administrador**, hay dos opciones:

- Registrar un usuario desde `/usuarios/registro/` eligiendo el tipo «Administrador».
- Crear su perfil de usuario (modelo `Usuario`) desde el panel de administración, vinculado al usuario creado con `createsuperuser` y con el tipo «Administrador».

### 7. Iniciar el servidor

```bash
python manage.py runserver
```

En Windows también se puede usar `run.bat`, que abre Chrome en `127.0.0.1:8000` e inicia el servidor.

La aplicación queda disponible en:

- Inicio: http://127.0.0.1:8000/
- Login: http://127.0.0.1:8000/usuarios/login/



## Configuración inicial del sistema

Después de instalar, un Administrador debería cargar estos datos para que todo funcione de punta a punta:

1. **Facultades** (`/universidad/facultades/`): necesarias para registrar Docentes, Estudiantes y Funcionarios, y para crear zonas restringidas.
2. **Zonas y espacios** (`/estacionamiento/zonas/`): crear las zonas, indicando facultad y tipos permitidos si corresponde, y la cantidad de espacios.
3. **Tarifas** (`/reglas/`): cargar al menos una tarifa vigente por cada tipo de usuario. **Es importante cargar la del tipo «Externo»**, porque se usa también para las patentes no registradas.
4. **Reglamento y horarios** (`/reglas/reglamento/`): cargar el texto y el horario de apertura y cierre (por defecto se propone 07:00 a 22:00). Sin reglamento cargado, las reservas no tienen restricción horaria.
5. **Usuarios del personal**: registrar usuarios de tipo «Personal de estacionamiento» para quienes controlen los ingresos y salidas.

### Flujo de uso típico

1. El usuario se registra y carga sus vehículos.
2. Reserva un espacio eligiendo día, horario y lugar en la cuadrícula.
3. Al llegar, el personal registra su patente y el sistema le asigna el espacio reservado.
4. Al salir, el personal registra la salida y se muestra el recibo con el monto a cobrar.

---


## Rutas principales

### General y usuarios

| Ruta | Descripción | Acceso |
| --- | --- | --- |
| `/` | Página de inicio | Público |
| `/usuarios/registro/` | Registro de usuario | Público |
| `/usuarios/login/` | Inicio de sesión | Público |
| `/usuarios/logout/` | Cierre de sesión (método POST) | Autenticado |
| `/usuarios/perfil/` | Perfil del usuario | Autenticado |
| `/usuarios/perfil/editar/` | Editar perfil | Autenticado |
| `/usuarios/lista/` | Listado de usuarios | Personal |

### Vehículos

| Ruta | Descripción | Acceso |
| --- | --- | --- |
| `/vehiculos/` | Mis vehículos | Autenticado |
| `/vehiculos/agregar/` | Registrar vehículo | Autenticado |
| `/vehiculos/todos/` | Todos los vehículos | Personal |

### Estacionamiento

| Ruta | Descripción | Acceso |
| --- | --- | --- |
| `/estacionamiento/reservas/` | Mis reservas | Autenticado |
| `/estacionamiento/reservas/nueva/` | Nueva reserva | Autenticado |
| `/estacionamiento/reservas/<id>/cancelar/` | Cancelar reserva propia | Autenticado |
| `/estacionamiento/reservas/todas/` | Todas las reservas | Personal |
| `/estacionamiento/espacios/` | Mapa de espacios (lista o cuadrícula) | Autenticado |
| `/estacionamiento/espacios/<id>/editar/` | Editar espacio | Administrador |
| `/estacionamiento/movimientos/` | Ingresos y salidas | Personal |
| `/estacionamiento/movimientos/ingreso/` | Registrar ingreso | Personal |
| `/estacionamiento/movimientos/<id>/salida/` | Registrar salida y ver recibo | Personal |
| `/estacionamiento/zonas/` | Listado de zonas | Administrador |
| `/estacionamiento/zonas/nueva/` | Nueva zona | Administrador |
| `/estacionamiento/zonas/<id>/editar/` | Editar zona | Administrador |
| `/estacionamiento/zonas/espacios/nuevos/` | Crear espacios en masa | Administrador |

### Reglas y universidad

| Ruta | Descripción | Acceso |
| --- | --- | --- |
| `/reglas/` | Tarifas | Autenticado |
| `/reglas/nueva/` | Nueva tarifa | Personal |
| `/reglas/<id>/editar/` | Editar tarifa | Personal |
| `/reglas/reglamento/` | Ver reglamento y horarios | Autenticado |
| `/reglas/reglamento/editar/` | Editar texto del reglamento | Administrador |
| `/reglas/reglamento/horarios/` | Editar horario de apertura y cierre | Administrador |
| `/universidad/facultades/` | Listado de facultades | Administrador |
| `/universidad/facultades/nueva/` | Nueva facultad | Administrador |
| `/universidad/facultades/<id>/editar/` | Editar facultad | Administrador |
| `/admin/` | Panel de administración de Django | Superusuario |

### Parámetros comunes de los listados

La mayoría de los listados aceptan estos parámetros en la URL:

| Parámetro | Descripción |
| --- | --- |
| `q` | Texto de búsqueda. |
| `orden` y `dir` | Columna y sentido de ordenamiento (`asc` o `desc`). |
| `pagina` | Número de página (10 elementos por página). |
| `desde` y `hasta` | Rango de fechas (`AAAA-MM-DD`), en los listados de reservas. |
| `vista` | `lista` o `cuadros`, en el mapa de espacios. |

---

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