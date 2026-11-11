# Qué cambió y por qué (versión 1 → versión 2)

## 1. Seguridad y repositorio
| Antes | Ahora | Por qué |
|---|---|---|
| No había `.gitignore`; el `.env` con contraseñas se iba a subir a GitHub | `.gitignore` excluye `.env`, `venv*`, `__pycache__`, `__MACOSX` | El enunciado exige que las credenciales no queden en el repositorio |
| — | `.env.example` (plantilla sin contraseñas) | Quien clone el repo sabe qué variables necesita |
| `API_URL = "http://localhost:8000"` fijo en `app.py` | Se lee de `st.secrets` o de la variable `API_URL` | Permite desplegar la interfaz sin tocar el código |

## 2. Modelo de datos
| Antes | Ahora |
|---|---|
| 2 colecciones: `users`, `tickets` | 4 colecciones: `clientes`, `tecnicos`, `tickets`, `contadores` |
| El cliente era un texto suelto en el ticket | Colección `clientes` con `contacto` y `equipos[]` **embebidos** |
| El equipo era un texto suelto | El ticket guarda `cliente_id` (**referencing**) y una copia del `equipo` (**embedding**, conserva el historial aunque el equipo se borre) |
| Técnicos sin especialidad | `especialidades[]` y `activo` |
| Fechas de bitácora como texto | Fechas reales (`datetime`), con `estado` en cada entrada |
| Sin índices | Índices únicos (código, NIT, email) e índices para los filtros |

## 3. Errores corregidos
1. **Códigos duplicados** (`count()+1`) → contador atómico con `$inc` en la colección `contadores`.
2. **Cualquier estado era válido** → máquina de estados (`TRANSICIONES` en `modelos.py`).
3. **Costos negativos y campos vacíos** → validación con Pydantic (`Field(ge=0)`, `min_length`, `pattern`).
4. **Asignar a un ticket inexistente o cerrado respondía "OK"** → se verifica que exista y su estado.
5. **Eliminar un ticket inexistente respondía "ID inválido"** → ahora 400 si el ID es inválido y 404 si no existe.
6. **La página pedía un PDF por cada ticket en cada recarga** → el PDF se genera solo cuando se pide; además las consultas tienen caché de 60 s.
7. **Errores silenciosos al cerrar ticket/subir foto** → todos los errores se muestran en pantalla, en español.

## 4. Funcionalidades nuevas
- CRUD completo de **técnicos**, **clientes** y **equipos** (antes solo tickets).
- **Editar** ticket (prioridad, categoría, descripción) y **agregar notas** a la bitácora.
- **Reasignar** técnico.
- **Búsqueda por texto** (código, cliente, equipo, serial, descripción) + filtros por estado, categoría, prioridad, técnico, cliente y rango de fechas.
- El listado muestra **nombres** de cliente y técnico (con `$lookup`), no IDs.
- Exportar resultados a CSV.

## 5. Reglas de negocio (antes 1, ahora 10)
Ver README. Todas están en `main.py`, marcadas con el comentario `# REGLA:`.

## 6. Consultas analíticas (antes 1, ahora 9)
Todas en `consultas.py`, cada una con la pregunta de negocio que responde:
resumen general ($facet), ranking de técnicos, por categoría, top clientes ($limit), por ciudad, evolución mensual, tipos de equipo con más fallas, solicitudes atrasadas y carga de cada técnico.

## 7. Interfaz
- Menú lateral con 6 secciones: Panel de control, Tickets, Nuevo ticket, Técnicos, Clientes, Analítica.
- Tarjetas de indicadores, etiquetas de colores por estado y prioridad, línea de tiempo para la bitácora y gráficos interactivos (Altair).
- Confirmación antes de eliminar.
- Indicador de conexión con la API, MongoDB Atlas y Cloudinary.

## 8. PDF
Antes: 6 líneas de texto. Ahora: encabezado con logo y código, estado y prioridad con colores, datos completos del cliente, equipo y técnico, tiempo de atención, descripción, bitácora en tabla (continúa en otra página si es larga), foto de evidencia, total y espacio para firmas.

## 9. Clientes: personas o empresas (versión 2.1)
- Al registrar un cliente se elige si viene **a nombre propio** (persona natural, con cédula) o **de parte de una empresa** (con NIT y nombre de quien reporta).
- En **Nuevo ticket** se puede registrar el cliente y su equipo en el mismo momento, sin ir a otra pantalla. Antes de guardar se valida todo con los mismos modelos del backend, para no dejar registros a medias.
- Nueva consulta analítica: **personas vs. empresas** (tickets, clientes, ingresos y ticket promedio de cada grupo).
- Corrección: versiones de `numpy` y `pyarrow` fijadas en `requirements.txt` (error "pyarrow requires NumPy 2.0").

## 10. Ampliación para equipo de 3 (versión 3)
- **IA con Google Gemini (Google Cloud)** — `ia.py`. Botón "🤖 Sugerir con IA" en Nuevo ticket (categoría, prioridad, diagnóstico y pasos; el diagnóstico queda guardado en el ticket y en el PDF). En Analítica, "Informe ejecutivo con IA". Si un modelo no está disponible se prueba el siguiente; la IA solo sugiere y el backend corrige valores fuera de las listas.
- **Inventario de repuestos** — nueva colección `repuestos`, sección 📦 Inventario (CRUD, entradas de stock, historial de movimientos embebido). Al resolver un ticket se eligen los repuestos usados y se descuentan con una **transacción de MongoDB** (`start_session` + `start_transaction`): si falta stock de uno, se deshace todo. El costo del ticket ahora es mano de obra + repuestos.
- **Portal del cliente** — sección 🙋: el cliente consulta su ticket con código + cédula/NIT, ve el progreso, descarga su PDF y califica de 1 a 5 (una sola vez). Nuevas métricas de satisfacción.
- **CSV → PDF**: el listado de tickets se exporta como reporte PDF generado por el backend con los filtros aplicados.
