# 🛠️ ServiFix — Gestión de soporte técnico

Aplicación para que una empresa de soporte técnico gestione las solicitudes de sus clientes: registro de fallas en equipos, asignación de técnicos, seguimiento (bitácora), cierre con costo y evidencia fotográfica, órdenes de servicio en PDF y reportes analíticos.

**Proyecto final — Bases de Datos II**

## Arquitectura

```
Interfaz (Streamlit · app.py)
        │  HTTP / JSON
        ▼
Backend / API (FastAPI · main.py)  ──►  Cloudinary (fotos de evidencia)
        │                          ──►  Google Gemini · Google Cloud (inteligencia artificial)
        │  PyMongo
        ▼
Base de datos en la nube (MongoDB Atlas)
```

| Archivo | Qué hace |
|---|---|
| `app.py` | Interfaz gráfica (6 pantallas) |
| `interfaz_api.py` | Funciones con las que la interfaz llama a la API |
| `interfaz_estilos.py` | Estilos visuales (CSS) y componentes |
| `main.py` | API: endpoints, validaciones y reglas de negocio |
| `modelos.py` | Modelos Pydantic (validación) y constantes de negocio |
| `consultas.py` | Consultas de agregación (Aggregation Pipeline) |
| `pdf_report.py` | Orden de servicio y reporte de tickets en PDF |
| `ia.py` | Integración con Google Gemini (sugerencias y informe ejecutivo) |
| `database.py` | Conexión a MongoDB Atlas e índices |
| `seed.py` | Datos de ejemplo |

## Modelo de datos (MongoDB)

- **clientes**: pueden ser **personas naturales** (con cédula) o **empresas** (con NIT y persona de contacto). `contacto` y `equipos[]` van **embebidos** (siempre se consultan junto con el cliente).
- **tecnicos**: nombre, email, teléfono, `especialidades[]` y estado activo/inactivo.
- **tickets**: referencia al cliente (`cliente_id`) y al técnico (`tecnico_id`) por **referencing**; copia del `equipo` y `bitacora[]` **embebidos**.
- **contadores**: consecutivo atómico para los códigos `TCK-AAAA-NNNN`.
- **repuestos**: inventario con `stock`, `stock_minimo` y `movimientos[]` **embebidos** (solo los últimos 50, con `$push` + `$slice`).
- En **tickets** también van embebidos `repuestos_usados[]` (con el precio del momento) y `calificacion` (encuesta del portal).

## Reglas de negocio

1. Un técnico puede tener como máximo **3 tickets en proceso**.
2. Solo se asignan técnicos **activos** y con la **especialidad** de la categoría del ticket.
3. Estados válidos: Abierto → En Proceso (al asignar) → Resuelto / Cancelado. Abierto → Cancelado. Resuelto y Cancelado son finales.
4. Para marcar como **Resuelto** se debe registrar un costo mayor a 0.
5. Un equipo no puede tener **dos tickets activos** a la vez, y debe pertenecer al cliente.
6. Solo se eliminan tickets **Abiertos o Cancelados**.
7. No se elimina un cliente ni un técnico con historial de tickets (el técnico se desactiva).
8. No se desactiva un técnico con tickets en proceso.
9. Cédula/NIT de cliente, email de técnico y código de ticket son **únicos** (índices únicos). Una persona se registra con cédula (solo dígitos); una empresa con NIT de 9 dígitos y una persona de contacto.
10. No se elimina un equipo con un ticket activo.
11. Al resolver, los repuestos se descuentan del inventario en una **transacción**: si falta stock de uno, no se guarda nada.
12. El stock no se edita a mano: solo cambia con entradas o al usarse en tickets. Un repuesto usado no se elimina.
13. El cliente solo ve su ticket si el código y su cédula/NIT coinciden; califica una sola vez y solo si está Resuelto.

## Ampliación para equipo de 3 integrantes

| Función | Qué demuestra |
|---|---|
| 🤖 IA con **Google Gemini** (Google Cloud) | Sugerencia de categoría, prioridad y diagnóstico al crear tickets; informe ejecutivo de la analítica |
| 📦 Inventario de repuestos | Nueva colección, **transacciones multi-documento**, `$expr`, `$unwind`, `$push` con `$slice` |
| 🙋 Portal del cliente + encuesta | Consulta segura por código + documento, calificación 1–5, métricas de satisfacción |
| 📄 Reportes PDF | Orden de servicio completa y reporte del listado filtrado de tickets |

## Ejecutar en el computador

```bash
python -m venv venv311
venv311\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env            # y poner los datos reales
python seed.py                    # carga datos de ejemplo (borra los anteriores)
uvicorn main:app --reload         # API en http://localhost:8000  (docs: /docs)
streamlit run app.py              # interfaz en http://localhost:8501
```

En Windows también se puede usar `Iniciar_Servifix.bat`.

## Despliegue

**Backend en Render** (Web Service, plan gratuito)
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment: `MONGO_URI`, `DB_NAME`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `GEMINI_API_KEY`, `PYTHON_VERSION=3.11.9`

**Interfaz en Streamlit Community Cloud**
- Main file: `app.py` · Python 3.11
- Secrets: `API_URL = "https://<su-servicio>.onrender.com"`

**MongoDB Atlas**: en *Network Access* permitir `0.0.0.0/0` para que Render pueda conectarse.

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/tickets?buscar=&estado=&categoria=&prioridad=&tecnico_id=&cliente_id=&desde=&hasta=` | Búsqueda y filtros |
| POST / PUT / DELETE | `/tickets`, `/tickets/{id}` | Crear, editar, eliminar |
| PUT | `/tickets/{id}/asignar`, `/tickets/{id}/estado` | Flujo de trabajo |
| POST | `/tickets/{id}/notas` | Nota en la bitácora |
| GET | `/tickets/{id}/pdf` | Orden de servicio |
| GET | `/reportes/tickets.pdf?...` | Reporte PDF con los mismos filtros de la búsqueda |
| CRUD | `/repuestos`, `POST /repuestos/{id}/entrada` | Inventario |
| GET / POST | `/portal/ticket`, `/portal/ticket/pdf`, `/portal/calificar` | Portal del cliente |
| POST / GET | `/ia/sugerir`, `/ia/resumen-analitica` | Google Gemini |
| CRUD | `/tecnicos`, `/clientes`, `/clientes/{id}/equipos` | Técnicos, clientes y equipos |
| GET | `/analytics/...` | resumen, rendimiento-tecnicos, por-categoria, top-clientes, por-ciudad, por-tipo-cliente, satisfaccion, comentarios, repuestos-mas-usados, stock-bajo, por-mes, equipos-fallas, pendientes |
