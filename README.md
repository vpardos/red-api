# red-api

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-2.x-E92063?style=flat-square)
![httpx](https://img.shields.io/badge/httpx-0.27+-0097FF?style=flat-square)
![BeautifulSoup](https://img.shields.io/badge/BeautifulSoup-4.x-4B8BBE?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

API HTTP no oficial y de código abierto para el sistema de transporte público Red Movilidad de Santiago. Extrae información de red.cl y metro.cl de los paraderos de RED, el Metro de Santiago y el servicio Tren Nos - Estación Central en un formato JSON limpio.

##
Actualmente, la API se encuentra disponible de forma pública en https://redapi.vpardos.dev, sin embargo esto puede cambiar. Su estado puede comprobarse en https://redapi.vpardos.dev/health.

## Características

- **`/stops/{stop_id}`** — Retorna las próximas llegadas de buses para un código de paradero, con distancia y tiempo (min/max minutos) por bus. Cada servicio se anota con su ventana operativa (`is_24_7`, `is_night_only`) según la [Malla nocturna de Red Movilidad](https://www.red.cl/mapas-y-horarios/bus/malla-nocturna/), y se marca como `Fuera de horario de operación` cuando el horario local de Santiago está fuera de su ventana y el upstream no reporta buses.
- **`/metro/...`** — Estado en tiempo real del Metro, por línea y por estación, cada una etiquetada como `operativa` / `cerrada_temporalmente` / `no_habilitada`. Las líneas se marcan automáticamente como `con_problemas` si alguna de sus estaciones no está operativa.
- **`/metrotren/...`** — Estado en tiempo real del Metrotren Nos, incluyendo información de conexiones intermodales.
- **Cache de token y predicciones** — El token JWT se cachea por 55 min, las predicciones por 30 s, y los snapshots de metro y metrotren por 60 s.

## Estructura del proyecto

```
red-api/
├── app/
│   ├── main.py             # App + rutas
│   ├── client.py           # Cliente HTTP async a red.cl (buses)
│   ├── metro_client.py     # Cliente HTTP async a red.cl (estado del metro)
│   ├── metro_parser.py     # Parser HTML puro a MetroSnapshot
│   ├── metro_cl_parser.py  # Parser HTML puro a MetroSnapshot desde metro.cl
│   ├── metrotren_client.py # Cliente HTTP async a red.cl (estado del metrotren)
│   ├── metrotren_parser.py # Parser HTML puro a MetrotrenSnapshot
│   ├── cache.py            # Caches TTL en memoria
│   ├── config.py           # Settings (URLs, timeouts, UA)
│   ├── models.py           # Modelos de respuesta pydantic
│   └── transformer.py      # Payload raw de bus a respuesta estructurada
├── requirements.txt
└── README.md
```

## Requisitos

- Python 3.10+
- virtualenv, conda o similar

## Configuración (usando venv)

```bash
# Crear el virtualenv (solo la primera vez)
python -m venv .venv

# Activar el virtualenv
source .venv/bin/activate

# Instalar dependencias (solo necesario en la primera ejecución o tras cambios en requirements)
pip install -r requirements.txt
```

## Ejecución de la API

Desde la raíz del proyecto:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Luego abrir:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc:      <http://localhost:8000/redoc>
- Health:     <http://localhost:8000/health>

## Referencia de la API

### `GET /health`

Retorna

```json
{ "status": "ok" }
```
### `GET /stops/{stop_id}`

Retorna las llegadas para un paradero.

**Ejemplo:**

```bash
curl http://localhost:8000/stops/PA417
```

**Respuesta exitosa (`200`):**

```json
{
  "id": "PA417",
  "name": "PARADA 3 / (M) PLAZA DE ARMAS",
  "status_code": 0,
  "status_description": "Itinerario obtenido satisfactoriamente",
  "services": [
    {
      "id": "504",
      "valid": true,
      "status_description": "Información de tiempos de los próximos 2 buses",
      "buses": [
        {
          "id": "TBFW-83",
          "meters_distance": 413,
          "min_arrival_time": 0,
          "max_arrival_time": 2
        },
        {
          "id": "PFXC-51",
          "meters_distance": 501,
          "min_arrival_time": 0,
          "max_arrival_time": 2
        }
      ],
      "is_24_7": false,
      "is_night_only": false
    },
    {
      "id": "505",
      "valid": true,
      "status_description": "Información de tiempos de los próximos 2 buses",
      "buses": [
        {
          "id": "LZPH-22",
          "meters_distance": 479,
          "min_arrival_time": 0,
          "max_arrival_time": 2
        },
        {
          "id": "SRTK-30",
          "meters_distance": 1098,
          "min_arrival_time": 0,
          "max_arrival_time": 4
        }
      ],
      "is_24_7": false,
      "is_night_only": false
    },
    {
      "id": "508",
      "valid": true,
      "status_description": "Información de tiempos de los próximos 2 buses",
      "buses": [
        {
          "id": "TBFX-24",
          "meters_distance": 503,
          "min_arrival_time": 0,
          "max_arrival_time": 2
        },
        {
          "id": "FLXV-88",
          "meters_distance": 3667,
          "min_arrival_time": 13,
          "max_arrival_time": 17
        }
      ],
      "is_24_7": true,
      "is_night_only": false
    },
    {
      "id": "402",
      "valid": true,
      "status_description": "Información de tiempos de los próximos 2 buses",
      "buses": [
        {
          "id": "LXWP-80",
          "meters_distance": 0,
          "min_arrival_time": 0,
          "max_arrival_time": 0
        },
        {
          "id": "SHXG-38",
          "meters_distance": 1273,
          "min_arrival_time": 3,
          "max_arrival_time": 7
        }
      ],
      "is_24_7": false,
      "is_night_only": false
    },
    {
      "id": "514",
      "valid": true,
      "status_description": "Información de tiempos de los próximos 2 buses",
      "buses": [
        {
          "id": "PFXB-25",
          "meters_distance": 464,
          "min_arrival_time": 0,
          "max_arrival_time": 2
        },
        {
          "id": "FLXX-49",
          "meters_distance": 5711,
          "min_arrival_time": 21,
          "max_arrival_time": 25
        }
      ],
      "is_24_7": false,
      "is_night_only": false
    }
  ]
}
```

**No encontrado (`200`, status_code = 1):**

```json
{
  "id": "PA999",
  "name": null,
  "status_code": 1,
  "status_description": "Paradero inválido",
  "services": []
}
```

**Upstream caído (`502`):** se retorna cuando red.cl no responde o devuelve un error.

#### Valores de `status_code`

| Código | Significado                                  |
| ------ | -------------------------------------------- |
| `0`    | OK                                           |
| `1`    | Paradero no encontrado / no existe           |
| `20`   | Sistema fuera de línea temporalmente         |

#### `min_arrival_time` / `max_arrival_time`

| Texto del upstream    | `min` | `max` |
| --------------------- | ----- | ----- |
| `"llegando"`          | `0`   | `0`   |
| `"menos de 5 min"`    | `0`   | `5`   |
| `"más de 10 min"`     | `10`  | `-1`  |
| `"3 y 5 min"`         | `3`   | `5`   |
| `"7 min"`             | `7`   | `7`   |
| no interpretable / vacío | `0`   | `0`   |

`max_arrival_time = -1` significa "más de `min` minutos" (abierto).

#### Horario de operación e indicador 24/7

Cada servicio lleva dos banderas que describen su horario, derivadas de la [Malla nocturna de Red Movilidad](https://www.red.cl/mapas-y-horarios/bus/malla-nocturna/):

| Campo            | Significado                                                                 |
| ---------------- | --------------------------------------------------------------------------- |
| `is_24_7`        | El servicio opera las 24 horas del día (25 servicios en la malla nocturna). |
| `is_night_only`  | El servicio es exclusivo de la noche (sufijo `N` en el código, 18 servicios).|

Además, la API aplica la ventana operativa del servicio contra la hora local de Santiago (UTC-4). Si la hora actual está **fuera** de la ventana del servicio y red.cl no reporta buses para él, la respuesta se sobreescribe a un estado explícito:

```json
{
  "id": "504",
  "valid": false,
  "status_description": "Fuera de horario de operación",
  "buses": [],
  "is_24_7": false,
  "is_night_only": false
}
```

Las ventanas aplicadas son:

| Categoría                | Servicios                                                                 | Ventana (hora local Santiago) |
| ------------------------ | ------------------------------------------------------------------------- | ----------------------------- |
| 24/7                     | `104, 107, 119, 201, 207, 210, 210v, 230, 301, 303, 401, 403, 405, 407, 418, 426, 506, 508, 513, 516, 518, C02, F20, G08, J08` | siempre                     |
| Diurno extendido         | `103, D09`                                                                | 05:30 – 01:30 (atraviesa medianoche) |
| Nocturno (sufijo `N`)    | `109N, 203N, 204N, 262N, 264N, 302N, 346N, 432N, 541N, 712N, B02N, B30N, B31N, F30N, I08N, I10N, I11N, I14N` | 00:00 – 05:00                |
| Diurno (resto)           | cualquier otro servicio                                                   | 05:30 – 23:59                |

La sobreescritura a `Fuera de horario de operación` **no** se aplica cuando red.cl reporta al menos un bus (aunque sea fuera de horario, p. ej. un desvío nocturno): en ese caso la API respeta la respuesta del upstream para no enmascarar incidentes.

### `GET /metro/status`

Snapshot completo de las 7 líneas de metro y las 143 estaciones. Respaldado por un cache en memoria de 60 s, por lo que la primera solicitud consulta red.cl y las siguientes (de cualquier worker) retornan el valor cacheado.

### `GET /metro/lines/{line_id}`

Retorna una sola línea. `line_id` debe ser uno de `l1`, `l2`, `l3`, `l4`, `l4a`, `l5`, `l6` (insensible a mayúsculas). `400` en id inválido, `404` si la línea no está en el snapshot.

**Ejemplo:**

```bash
curl http://localhost:8000/metro/lines/l4a
```

### `GET /metro/stations/{station_slug}`

Retorna una sola estación por su slug (el último segmento del `detail_url` del upstream, ej. `san-pablo-l1`, `puente-cal-y-canto-l2`). `400` en slug inválido, `404` si no está en el snapshot.

**Ejemplo:**

```bash
curl http://localhost:8000/metro/stations/san-pablo-l1
```

#### Valores de `status` (por estación)

| Valor de la API        | Clase en red.cl             | Significado                          |
| ---------------------- | --------------------------- | ------------------------------------ |
| `operativa`            | `operativa`                 | Estación operativa                   |
| `cerrada_temporalmente`| `cerrada-temporalmente`     | Estación cerrada temporalmente       |
| `no_habilitada`        | `no-habilitada`             | Estación no habilitada               |
| `desconocido`          | cualquier otra              | Desconocido — ver `raw_status_class` |

#### Valores de `status` (por línea)

| Valor de la API  | Significado                                                    |
| ---------------- | -------------------------------------------------------------- |
| `operativa`      | Todas las estaciones están `operativa`                         |
| `con_problemas`  | Al menos una estación no está `operativa`                      |

### `GET /metrotren/status`

Snapshot completo de la línea Metrotren Nos y sus 10 estaciones. Respaldado por un cache en memoria de 60 s, igual que el snapshot del metro.

**Ejemplo:**

```bash
curl http://localhost:8000/metrotren/status
```


### `GET /metrotren/stations/{station_slug}`

Retorna una sola estación por su slug (ej. `alameda`, `lo-valledor`, `p-a-c`, `san-bernardo`). `400` en slug inválido, `404` si no está en el snapshot.

**Ejemplo:**

```bash
curl http://localhost:8000/metrotren/stations/alameda
```

La semántica de `status` / `raw_status_class` es la misma que para los endpoints de Metro. Para estaciones que son hubs intermodales, `connections` está poblado, de lo contrario `has_connections: false` y `connections: null`.



## Licencia

MIT
