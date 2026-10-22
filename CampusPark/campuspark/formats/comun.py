"""
Formatos de fecha y hora de CampusPark, compartidos por todos los idiomas
(ver formats/en y formats/es). Usan la sintaxis de los filtros `date`/`time`
de Django: d=día, m=mes, Y=año de 4 dígitos, H=hora (00-23), i=minutos.

Se activan con FORMAT_MODULE_PATH = "campuspark.formats" en settings.py.
Con eso, TODA fecha mostrada con {{ valor }} (templates, admin) sale así:

  fechas con hora (DateTimeField)  ->  13/10/2026, 15:30
  fechas sin hora (DateField)      ->  13/10/2026
  horas (TimeField)                ->  15:30

No se tocan los *_INPUT_FORMATS: los campos de fecha/hora de los
formularios son <input type="date"/"time">, que siempre trabajan en ISO.
"""

# FECHA Y HORA
DATE_FORMAT = "d/m/Y"
DATETIME_FORMAT = "d-m-Y, H:i"
TIME_FORMAT = "H:i"
SHORT_DATE_FORMAT = "d/m/Y"
SHORT_DATETIME_FORMAT = "d/m/Y, H:i"

# FORMATO DE NÚMEROS (Punto como separador de miles, sin decimales)
NUMBER_GROUPING = 3
THOUSAND_SEPARATOR = "."
DECIMAL_SEPARATOR = ","
DECIMAL_PLACES = 0