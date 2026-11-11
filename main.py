"""
main.py  —  BACKEND / API de ServiFix (FastAPI)
================================================
Recorrido de una operación:
    Interfaz (app.py)  --HTTP/JSON-->  este archivo  --PyMongo-->  MongoDB Atlas

Aquí se:
  1. reciben las peticiones de la interfaz,
  2. validan los datos (modelos.py) y las REGLAS DE NEGOCIO,
  3. ejecutan las operaciones sobre la base de datos (database.py),
  4. ejecutan las consultas analíticas (consultas.py).

Para correr en local:   uvicorn main:app --reload
Documentación automática de la API:  http://localhost:8000/docs
"""
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import cloudinary
import cloudinary.uploader
from bson import ObjectId
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError, ServerSelectionTimeoutError

import consultas as q
import ia
from database import (client, clientes, contadores, crear_indices, db, ping, repuestos,
                      tecnicos, tickets)
from modelos import (CATEGORIAS, CATEGORIAS_REPUESTO, ESTADOS, ESTADOS_ACTIVOS,
                     ESTADOS_FINALES, MAX_TICKETS_ACTIVOS, PRIORIDADES, TIPOS_CLIENTE,
                     TIPOS_EQUIPO, TRANSICIONES, Calificacion, EntradaStock,
                     RepuestoCreate, RepuestoUpdate, SolicitudIA,
                     ClienteCreate, ClienteUpdate, EquipoIn, TecnicoCreate,
                     TecnicoUpdate, TicketAsignar, TicketCreate, TicketEstado,
                     TicketNota, TicketUpdate)
from pdf_report import generar_pdf_listado, generar_pdf_ticket

app = FastAPI(
    title="ServiFix API",
    description="Backend del sistema de gestión de soporte técnico ServiFix",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cloudinary (almacenamiento de fotos en la nube). Credenciales desde variables de entorno.
CLOUDINARY_OK = all(os.getenv(v) for v in
                    ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"))
if CLOUDINARY_OK:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )

COL = timezone(timedelta(hours=-5))  # Hora de Colombia


@app.on_event("startup")
def al_iniciar():
    try:
        crear_indices()
    except PyMongoError as e:  # la API arranca igual; /health mostrará el problema
        print(f"[ADVERTENCIA] No se pudieron crear los índices: {e}")


# ---------------------------------------------------------------------------
# MANEJO DE ERRORES DE BASE DE DATOS
# ---------------------------------------------------------------------------
@app.exception_handler(DuplicateKeyError)
def error_duplicado(_: Request, exc: DuplicateKeyError):
    return JSONResponse(status_code=409, content={"detail": "Ya existe un registro con ese dato único."})


@app.exception_handler(ServerSelectionTimeoutError)
def error_conexion(_: Request, exc: ServerSelectionTimeoutError):
    return JSONResponse(status_code=503, content={"detail": "No hay conexión con MongoDB Atlas."})


# ---------------------------------------------------------------------------
# FUNCIONES DE APOYO
# ---------------------------------------------------------------------------
def ahora() -> datetime:
    return datetime.now(timezone.utc)


def oid(valor: str, que: str = "registro") -> ObjectId:
    """Convierte un texto en ObjectId. Si no es válido responde 400."""
    if not ObjectId.is_valid(valor):
        raise HTTPException(400, f"El ID de {que} no tiene un formato válido.")
    return ObjectId(valor)


def serializar(dato):
    """Convierte ObjectId y fechas a texto para poder enviarlos como JSON."""
    if isinstance(dato, list):
        return [serializar(x) for x in dato]
    if isinstance(dato, dict):
        salida = {}
        for k, v in dato.items():
            salida["id" if k == "_id" else k] = serializar(v)
        return salida
    if isinstance(dato, ObjectId):
        return str(dato)
    if isinstance(dato, datetime):
        if dato.tzinfo is None:
            dato = dato.replace(tzinfo=timezone.utc)
        return dato.isoformat()
    return dato


def entrada_bitacora(nota: str, autor: str, estado: str) -> dict:
    """Un registro del historial del ticket (va EMBEBIDO en el ticket)."""
    return {"fecha": ahora(), "nota": nota, "autor": autor, "estado": estado}


def siguiente_codigo() -> str:
    """
    Genera el código TCK-AAAA-NNNN con un contador atómico ($inc).
    Así nunca se repite, aunque se borren tickets (antes se usaba count()+1).
    """
    anio = ahora().astimezone(COL).year
    doc = contadores.find_one_and_update(
        {"_id": f"tickets-{anio}"},
        {"$inc": {"secuencia": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"TCK-{anio}-{doc['secuencia']:04d}"


def obtener_ticket(ticket_id: str) -> dict:
    t = tickets.find_one({"_id": oid(ticket_id, "ticket")})
    if not t:
        raise HTTPException(404, "Ticket no encontrado.")
    return t


def detalle_ticket(_id: ObjectId) -> dict:
    """Ticket con los datos del cliente y del técnico ($lookup)."""
    res = list(tickets.aggregate(q.pipeline_tickets({"_id": _id})))
    if not res:
        raise HTTPException(404, "Ticket no encontrado.")
    return res[0]


# ---------------------------------------------------------------------------
# GENERALES
# ---------------------------------------------------------------------------
@app.get("/", tags=["General"])
def inicio():
    return {"app": "ServiFix API", "version": "3.0.0", "docs": "/docs"}


@app.get("/health", tags=["General"])
def salud():
    """Verifica que la API y la conexión con MongoDB Atlas funcionan."""
    try:
        ping()
        return {"api": "ok", "mongodb_atlas": "ok", "base_de_datos": db.name,
                "cloudinary": "ok" if CLOUDINARY_OK else "no configurado",
                "gemini": "ok" if ia.configurada() else "no configurado"}
    except PyMongoError as e:
        raise HTTPException(503, f"Sin conexión con MongoDB Atlas: {e}")


@app.get("/catalogos", tags=["General"])
def catalogos():
    """Listas fijas que usa la interfaz para los menús desplegables."""
    return {"categorias": CATEGORIAS, "prioridades": PRIORIDADES, "estados": ESTADOS,
            "tipos_equipo": TIPOS_EQUIPO, "tipos_cliente": TIPOS_CLIENTE,
            "categorias_repuesto": CATEGORIAS_REPUESTO,
            "max_tickets_activos": MAX_TICKETS_ACTIVOS}


# ===========================================================================
# CLIENTES   (personas o empresas · CRUD + equipos embebidos)
# ===========================================================================
@app.get("/clientes", tags=["Clientes"])
def listar_clientes(buscar: Optional[str] = None, ciudad: Optional[str] = None,
                    tipo: Optional[str] = None):
    filtro = {}
    if ciudad:
        filtro["ciudad"] = ciudad
    if tipo:
        if tipo not in TIPOS_CLIENTE:
            raise HTTPException(400, f"Tipo de cliente no válido: {tipo}")
        filtro["tipo"] = tipo
    if buscar:
        patron = {"$regex": re.escape(buscar), "$options": "i"}
        filtro["$or"] = [{"nombre": patron}, {"documento": patron}, {"contacto.nombre": patron}]
    return serializar(list(clientes.find(filtro).sort("nombre", 1)))


@app.get("/clientes/{cliente_id}", tags=["Clientes"])
def ver_cliente(cliente_id: str):
    c = clientes.find_one({"_id": oid(cliente_id, "cliente")})
    if not c:
        raise HTTPException(404, "Cliente no encontrado.")
    return serializar(c)


@app.post("/clientes", status_code=201, tags=["Clientes"])
def crear_cliente(data: ClienteCreate):
    # REGLA: la cédula / NIT no se puede repetir
    if clientes.find_one({"documento": data.documento}):
        doc = "la cédula" if data.tipo == "Persona" else "el NIT"
        raise HTTPException(409, f"Ya existe un cliente con {doc} {data.documento}.")
    doc = data.model_dump()
    doc.update({"equipos": [], "created_at": ahora()})
    res = clientes.insert_one(doc)
    return {"mensaje": "Cliente creado", "id": str(res.inserted_id)}


@app.put("/clientes/{cliente_id}", tags=["Clientes"])
def actualizar_cliente(cliente_id: str, data: ClienteUpdate):
    _id = oid(cliente_id, "cliente")
    cliente = clientes.find_one({"_id": _id})
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado.")
    cambios = data.model_dump(exclude_none=True)
    if not cambios:
        raise HTTPException(400, "No se enviaron cambios.")
    # El tipo (persona/empresa) y el documento no se modifican.
    if cliente.get("tipo") == "Persona":
        # REGLA: en una persona natural el contacto es ella misma
        nombre = cambios.get("nombre", cliente["nombre"])
        contacto = cambios.get("contacto") or cliente.get("contacto", {})
        cambios["contacto"] = {**contacto, "nombre": nombre}
    elif "contacto" in cambios and not cambios["contacto"].get("nombre"):
        raise HTTPException(400, "Para una empresa indique el nombre de la persona de contacto.")
    clientes.update_one({"_id": _id}, {"$set": cambios})
    return {"mensaje": "Cliente actualizado"}


@app.delete("/clientes/{cliente_id}", tags=["Clientes"])
def eliminar_cliente(cliente_id: str):
    _id = oid(cliente_id, "cliente")
    if not clientes.find_one({"_id": _id}):
        raise HTTPException(404, "Cliente no encontrado.")
    # REGLA: no se borra un cliente con historial de tickets (se perdería la trazabilidad)
    n = tickets.count_documents({"cliente_id": _id})
    if n > 0:
        raise HTTPException(409, f"No se puede eliminar: el cliente tiene {n} ticket(s) registrados.")
    clientes.delete_one({"_id": _id})
    return {"mensaje": "Cliente eliminado"}


@app.post("/clientes/{cliente_id}/equipos", status_code=201, tags=["Clientes"])
def agregar_equipo(cliente_id: str, data: EquipoIn):
    _id = oid(cliente_id, "cliente")
    cliente = clientes.find_one({"_id": _id})
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado.")
    # REGLA: un cliente no puede tener dos equipos con el mismo serial
    if any(e["serial"].lower() == data.serial.lower() for e in cliente.get("equipos", [])):
        raise HTTPException(409, f"El cliente ya tiene un equipo con serial {data.serial}.")
    equipo = {"equipo_id": ObjectId(), **data.model_dump()}
    clientes.update_one({"_id": _id}, {"$push": {"equipos": equipo}})
    return {"mensaje": "Equipo agregado", "equipo_id": str(equipo["equipo_id"])}


@app.delete("/clientes/{cliente_id}/equipos/{equipo_id}", tags=["Clientes"])
def eliminar_equipo(cliente_id: str, equipo_id: str):
    _id, eq_id = oid(cliente_id, "cliente"), oid(equipo_id, "equipo")
    # REGLA: no se elimina un equipo que tiene un ticket abierto o en proceso
    if tickets.count_documents({"cliente_id": _id, "equipo.equipo_id": eq_id,
                                "estado": {"$in": ["Abierto", "En Proceso"]}}):
        raise HTTPException(409, "El equipo tiene un ticket activo. Ciérrelo antes de eliminarlo.")
    res = clientes.update_one({"_id": _id}, {"$pull": {"equipos": {"equipo_id": eq_id}}})
    if res.matched_count == 0:
        raise HTTPException(404, "Cliente no encontrado.")
    if res.modified_count == 0:
        raise HTTPException(404, "Equipo no encontrado.")
    return {"mensaje": "Equipo eliminado"}


# ===========================================================================
# TÉCNICOS   (CRUD)
# ===========================================================================
@app.get("/tecnicos", tags=["Técnicos"])
def listar_tecnicos(buscar: Optional[str] = None, activo: Optional[bool] = None,
                    especialidad: Optional[str] = None):
    filtro = {}
    if activo is not None:
        filtro["activo"] = activo
    if especialidad:
        filtro["especialidades"] = especialidad
    if buscar:
        patron = {"$regex": re.escape(buscar), "$options": "i"}
        filtro["$or"] = [{"nombre": patron}, {"email": patron}]
    return serializar(list(tecnicos.aggregate(q.pipeline_tecnicos_con_carga(filtro))))


@app.get("/tecnicos/{tecnico_id}", tags=["Técnicos"])
def ver_tecnico(tecnico_id: str):
    res = list(tecnicos.aggregate(q.pipeline_tecnicos_con_carga({"_id": oid(tecnico_id, "técnico")})))
    if not res:
        raise HTTPException(404, "Técnico no encontrado.")
    return serializar(res[0])


@app.post("/tecnicos", status_code=201, tags=["Técnicos"])
def crear_tecnico(data: TecnicoCreate):
    email = data.email.lower()
    if tecnicos.find_one({"email": email}):
        raise HTTPException(409, f"Ya existe un técnico con el email {email}.")
    doc = data.model_dump()
    doc.update({"email": email, "created_at": ahora()})
    res = tecnicos.insert_one(doc)
    return {"mensaje": "Técnico creado", "id": str(res.inserted_id)}


@app.put("/tecnicos/{tecnico_id}", tags=["Técnicos"])
def actualizar_tecnico(tecnico_id: str, data: TecnicoUpdate):
    _id = oid(tecnico_id, "técnico")
    if not tecnicos.find_one({"_id": _id}):
        raise HTTPException(404, "Técnico no encontrado.")
    cambios = data.model_dump(exclude_none=True)
    if not cambios:
        raise HTTPException(400, "No se enviaron cambios.")

    if "email" in cambios:
        cambios["email"] = cambios["email"].lower()
        if tecnicos.find_one({"email": cambios["email"], "_id": {"$ne": _id}}):
            raise HTTPException(409, "Ese email ya lo usa otro técnico.")

    activos = tickets.count_documents({"tecnico_id": _id, "estado": {"$in": ESTADOS_ACTIVOS}})
    # REGLA: no se puede desactivar un técnico que tiene tickets en proceso
    if cambios.get("activo") is False and activos > 0:
        raise HTTPException(409, f"El técnico tiene {activos} ticket(s) en proceso. "
                                 "Reasígnelos o ciérrelos antes de desactivarlo.")
    # REGLA: si se le quita una especialidad, no puede tener tickets en proceso de esa categoría
    if "especialidades" in cambios:
        conflicto = tickets.find_one({"tecnico_id": _id, "estado": {"$in": ESTADOS_ACTIVOS},
                                      "categoria": {"$nin": cambios["especialidades"]}})
        if conflicto:
            raise HTTPException(409, f"El técnico atiende el ticket {conflicto['codigo']} "
                                     f"de categoría {conflicto['categoria']}; no puede quitarle esa especialidad.")

    tecnicos.update_one({"_id": _id}, {"$set": cambios})
    return {"mensaje": "Técnico actualizado"}


@app.delete("/tecnicos/{tecnico_id}", tags=["Técnicos"])
def eliminar_tecnico(tecnico_id: str):
    _id = oid(tecnico_id, "técnico")
    if not tecnicos.find_one({"_id": _id}):
        raise HTTPException(404, "Técnico no encontrado.")
    # REGLA: un técnico con historial no se borra (se perdería quién hizo cada trabajo).
    n = tickets.count_documents({"tecnico_id": _id})
    if n > 0:
        raise HTTPException(409, f"El técnico tiene {n} ticket(s) en su historial. "
                                 "En lugar de eliminarlo, márquelo como inactivo.")
    tecnicos.delete_one({"_id": _id})
    return {"mensaje": "Técnico eliminado"}


# ===========================================================================
# TICKETS   (CRUD + flujo de trabajo)
# ===========================================================================
def filtro_tickets(estado, categoria, prioridad, tecnico_id, cliente_id, desde, hasta) -> dict:
    """Arma el filtro de MongoDB a partir de los parámetros de búsqueda."""
    filtro = {}
    for valor, lista, campo in ((estado, ESTADOS, "estado"), (categoria, CATEGORIAS, "categoria"),
                                (prioridad, PRIORIDADES, "prioridad")):
        if valor:
            if valor not in lista:
                raise HTTPException(400, f"Valor de {campo} no válido: {valor}")
            filtro[campo] = valor
    if tecnico_id:
        filtro["tecnico_id"] = oid(tecnico_id, "técnico")
    if cliente_id:
        filtro["cliente_id"] = oid(cliente_id, "cliente")
    if desde or hasta:
        filtro["created_at"] = {}
        if desde:
            filtro["created_at"]["$gte"] = datetime(desde.year, desde.month, desde.day, tzinfo=COL)
        if hasta:
            fin = datetime(hasta.year, hasta.month, hasta.day, tzinfo=COL) + timedelta(days=1)
            filtro["created_at"]["$lt"] = fin
    return filtro


@app.get("/tickets", tags=["Tickets"])
def listar_tickets(
    buscar: Optional[str] = None,
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    prioridad: Optional[str] = None,
    tecnico_id: Optional[str] = None,
    cliente_id: Optional[str] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
):
    """Búsqueda y filtrado de tickets. Devuelve nombres de cliente y técnico."""
    filtro = filtro_tickets(estado, categoria, prioridad, tecnico_id, cliente_id, desde, hasta)
    return serializar(list(tickets.aggregate(q.pipeline_tickets(filtro, buscar))))


@app.get("/reportes/tickets.pdf", tags=["Reportes"])
def reporte_tickets_pdf(
    buscar: Optional[str] = None,
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    prioridad: Optional[str] = None,
    tecnico_id: Optional[str] = None,
    cliente_id: Optional[str] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
):
    """Reporte PDF del listado de tickets con los mismos filtros de la búsqueda."""
    filtro = filtro_tickets(estado, categoria, prioridad, tecnico_id, cliente_id, desde, hasta)
    lista = list(tickets.aggregate(q.pipeline_tickets(filtro, buscar)))
    partes = [f"Búsqueda: '{buscar}'" if buscar else None,
              f"Estado: {estado}" if estado else None,
              f"Categoría: {categoria}" if categoria else None,
              f"Prioridad: {prioridad}" if prioridad else None,
              f"Técnico: {lista[0]['tecnico'].get('nombre')}" if tecnico_id and lista else None,
              f"Cliente: {lista[0]['cliente'].get('nombre')}" if cliente_id and lista else None,
              f"Desde {desde.strftime('%d/%m/%Y')}" if desde else None,
              f"hasta {hasta.strftime('%d/%m/%Y')}" if hasta else None]
    descripcion = " · ".join(p for p in partes if p) or "Todos los tickets"
    return Response(content=generar_pdf_listado(lista, descripcion), media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=reporte_tickets.pdf"})


@app.get("/tickets/{ticket_id}", tags=["Tickets"])
def ver_ticket(ticket_id: str):
    return serializar(detalle_ticket(oid(ticket_id, "ticket")))


@app.post("/tickets", status_code=201, tags=["Tickets"])
def crear_ticket(data: TicketCreate):
    cliente_id = oid(data.cliente_id, "cliente")
    equipo_id = oid(data.equipo_id, "equipo")

    cliente = clientes.find_one({"_id": cliente_id})
    if not cliente:
        raise HTTPException(404, "El cliente no existe.")
    # REGLA: el equipo debe pertenecer a ese cliente
    equipo = next((e for e in cliente.get("equipos", []) if e["equipo_id"] == equipo_id), None)
    if not equipo:
        raise HTTPException(400, "El equipo seleccionado no pertenece a este cliente.")
    # REGLA: no puede haber dos tickets activos para el mismo equipo
    duplicado = tickets.find_one({"equipo.equipo_id": equipo_id,
                                  "estado": {"$in": ["Abierto", "En Proceso"]}})
    if duplicado:
        raise HTTPException(409, f"Ese equipo ya tiene el ticket activo {duplicado['codigo']}.")

    codigo = siguiente_codigo()
    momento = ahora()
    nuevo = {
        "codigo": codigo,
        "cliente_id": cliente_id,                   # REFERENCING al cliente
        "equipo": {                                 # EMBEDDING: copia del equipo al momento del reporte
            "equipo_id": equipo["equipo_id"],
            "nombre": equipo["nombre"],
            "tipo": equipo["tipo"],
            "marca": equipo["marca"],
            "serial": equipo["serial"],
        },
        "categoria": data.categoria,
        "prioridad": data.prioridad,
        "descripcion": data.descripcion,
        "estado": "Abierto",
        "tecnico_id": None,                         # REFERENCING al técnico (se llena al asignar)
        "costo": 0.0,                               # total = mano de obra + repuestos
        "costo_mano_obra": 0.0,
        "costo_repuestos": 0.0,
        "repuestos_usados": [],                     # EMBEDDING: se llena al resolver
        "calificacion": None,                       # EMBEDDING: encuesta del portal del cliente
        "diagnostico_ia": data.diagnostico_ia,      # sugerencia de Google Gemini (opcional)
        "foto_url": None,
        "created_at": momento,
        "updated_at": momento,
        "resolved_at": None,
        "bitacora": [{"fecha": momento, "nota": "Solicitud registrada.",
                      "autor": cliente["contacto"]["nombre"], "estado": "Abierto"}],
    }
    res = tickets.insert_one(nuevo)
    return {"mensaje": "Ticket creado", "id": str(res.inserted_id), "codigo": codigo}


@app.put("/tickets/{ticket_id}", tags=["Tickets"])
def editar_ticket(ticket_id: str, data: TicketUpdate):
    t = obtener_ticket(ticket_id)
    # REGLA: un ticket cerrado no se modifica
    if t["estado"] in ESTADOS_FINALES:
        raise HTTPException(409, f"El ticket está {t['estado']} y ya no se puede editar.")
    cambios = data.model_dump(exclude_none=True)
    cambios = {k: v for k, v in cambios.items() if t.get(k) != v}
    if not cambios:
        raise HTTPException(400, "No hay cambios para guardar.")
    # REGLA: la categoría solo cambia mientras no haya técnico (depende de su especialidad)
    if "categoria" in cambios and t["estado"] != "Abierto":
        raise HTTPException(409, "La categoría solo se puede cambiar antes de asignar un técnico.")

    descripcion_cambios = ", ".join(f"{k}: {t.get(k)} → {v}" if k != "descripcion"
                                    else "descripción actualizada" for k, v in cambios.items())
    cambios["updated_at"] = ahora()
    tickets.update_one({"_id": t["_id"]}, {
        "$set": cambios,
        "$push": {"bitacora": entrada_bitacora(f"Ticket editado ({descripcion_cambios}).",
                                               "Coordinador", t["estado"])},
    })
    return {"mensaje": "Ticket actualizado"}


@app.put("/tickets/{ticket_id}/asignar", tags=["Tickets"])
def asignar_tecnico(ticket_id: str, data: TicketAsignar):
    t = obtener_ticket(ticket_id)
    tec_id = oid(data.tecnico_id, "técnico")

    # REGLA: solo se asignan/reasignan tickets abiertos o en proceso
    if t["estado"] not in ("Abierto", "En Proceso"):
        raise HTTPException(409, f"No se puede asignar un ticket en estado {t['estado']}.")
    if t.get("tecnico_id") == tec_id:
        raise HTTPException(400, "Ese técnico ya está asignado a este ticket.")

    tecnico = tecnicos.find_one({"_id": tec_id})
    if not tecnico:
        raise HTTPException(404, "El técnico no existe.")
    # REGLA: el técnico debe estar activo
    if not tecnico.get("activo", True):
        raise HTTPException(409, f"{tecnico['nombre']} está inactivo.")
    # REGLA: el técnico debe tener la especialidad de la categoría del ticket
    if t["categoria"] not in tecnico.get("especialidades", []):
        raise HTTPException(409, f"{tecnico['nombre']} no tiene la especialidad {t['categoria']} "
                                 f"(sus especialidades: {', '.join(tecnico.get('especialidades', []))}).")
    # REGLA: máximo 3 tickets en proceso por técnico
    activos = tickets.count_documents({"tecnico_id": tec_id, "estado": {"$in": ESTADOS_ACTIVOS}})
    if activos >= MAX_TICKETS_ACTIVOS:
        raise HTTPException(409, f"{tecnico['nombre']} ya tiene {activos} tickets en proceso "
                                 f"(máximo {MAX_TICKETS_ACTIVOS}).")

    if t.get("tecnico_id"):
        anterior = tecnicos.find_one({"_id": t["tecnico_id"]}) or {}
        nota = f"Reasignado de {anterior.get('nombre', 'otro técnico')} a {tecnico['nombre']}."
    else:
        nota = f"Asignado al técnico {tecnico['nombre']}."

    # El filtro incluye el estado actual: si otro usuario lo cambió al mismo tiempo, no se pisa.
    res = tickets.update_one(
        {"_id": t["_id"], "estado": t["estado"]},
        {"$set": {"tecnico_id": tec_id, "estado": "En Proceso", "updated_at": ahora()},
         "$push": {"bitacora": entrada_bitacora(nota, "Coordinador", "En Proceso")}},
    )
    if res.modified_count == 0:
        raise HTTPException(409, "El ticket cambió mientras se asignaba. Recargue e intente de nuevo.")
    return {"mensaje": nota}


@app.put("/tickets/{ticket_id}/estado", tags=["Tickets"])
def cambiar_estado(ticket_id: str, data: TicketEstado):
    """
    Cierra un ticket (Resuelto o Cancelado).
    Si se usaron repuestos, se descuentan del inventario y se actualiza el ticket dentro de
    una TRANSACCIÓN de MongoDB: o se guarda todo, o no se guarda nada.
    """
    t = obtener_ticket(ticket_id)

    # REGLA: solo se permiten ciertos cambios de estado (ver TRANSICIONES en modelos.py)
    permitidos = TRANSICIONES.get(t["estado"], [])
    if data.estado not in permitidos:
        detalle = ", ".join(permitidos) if permitidos else "ninguno (estado final)"
        raise HTTPException(409, f"No se puede pasar de '{t['estado']}' a '{data.estado}'. "
                                 f"Permitidos: {detalle}.")

    # Cantidad pedida de cada repuesto (si se repite un repuesto, se suman)
    pedidos = {}
    for r in data.repuestos:
        rid = oid(r.repuesto_id, "repuesto")
        pedidos[rid] = pedidos.get(rid, 0) + r.cantidad

    momento = ahora()
    cambios = {"estado": data.estado, "updated_at": momento}
    if data.estado == "Resuelto":
        # REGLA: para resolver se debe registrar el costo de mano de obra
        if data.costo <= 0:
            raise HTTPException(400, "Para marcar como Resuelto debe indicar un costo de mano de obra mayor a 0.")
        cambios.update({"costo_mano_obra": data.costo, "resolved_at": momento})
        if data.foto_url:
            cambios["foto_url"] = data.foto_url
    else:  # Cancelado
        # REGLA: un ticket cancelado no consume repuestos ni genera cobro
        if pedidos:
            raise HTTPException(400, "Un ticket cancelado no puede registrar repuestos usados.")
        cambios.update({"costo": 0.0, "costo_mano_obra": 0.0, "costo_repuestos": 0.0})

    autor = "Coordinador"
    if t.get("tecnico_id"):
        tec = tecnicos.find_one({"_id": t["tecnico_id"]})
        if tec:
            autor = tec["nombre"]

    nota = f"{data.estado}: {data.nota}"
    with client.start_session() as sesion:
        with sesion.start_transaction():
            usados = []
            for rid, cantidad in pedidos.items():
                movimiento = {"fecha": momento, "tipo": "Salida", "cantidad": cantidad,
                              "referencia": f"Ticket {t['codigo']}"}
                # REGLA: no se puede usar más de lo que hay en stock (filtro stock >= cantidad)
                rep = repuestos.find_one_and_update(
                    {"_id": rid, "stock": {"$gte": cantidad}},
                    {"$inc": {"stock": -cantidad},
                     "$push": {"movimientos": {"$each": [movimiento], "$slice": -50}}},
                    session=sesion, return_document=ReturnDocument.AFTER,
                )
                if rep is None:  # se lanza el error -> la transacción se DESHACE completa
                    existe = repuestos.find_one({"_id": rid}, session=sesion)
                    if not existe:
                        raise HTTPException(404, "Uno de los repuestos seleccionados no existe.")
                    raise HTTPException(409, f"Stock insuficiente de '{existe['nombre']}': "
                                             f"hay {existe['stock']} y se pidieron {cantidad}. "
                                             "No se guardó ningún cambio.")
                usados.append({  # copia EMBEBIDA: conserva el precio del momento
                    "repuesto_id": rid, "sku": rep["sku"], "nombre": rep["nombre"],
                    "cantidad": cantidad, "precio_unitario": rep["precio_unitario"],
                    "subtotal": round(rep["precio_unitario"] * cantidad, 2),
                })

            if data.estado == "Resuelto":
                total_rep = round(sum(u["subtotal"] for u in usados), 2)
                cambios.update({"repuestos_usados": usados, "costo_repuestos": total_rep,
                                "costo": round(data.costo + total_rep, 2)})
                if usados:
                    nota += " | Repuestos: " + ", ".join(f"{u['cantidad']}x {u['nombre']}" for u in usados)

            res = tickets.update_one(
                {"_id": t["_id"], "estado": t["estado"]},
                {"$set": cambios,
                 "$push": {"bitacora": entrada_bitacora(nota, autor, data.estado)}},
                session=sesion,
            )
            if res.modified_count == 0:
                raise HTTPException(409, "El ticket cambió mientras se actualizaba. Recargue e intente de nuevo.")
    return {"mensaje": f"Ticket marcado como {data.estado}"}


@app.post("/tickets/{ticket_id}/notas", status_code=201, tags=["Tickets"])
def agregar_nota(ticket_id: str, data: TicketNota):
    """Agrega un avance a la bitácora sin cambiar el estado."""
    t = obtener_ticket(ticket_id)
    if t["estado"] in ESTADOS_FINALES:
        raise HTTPException(409, "No se pueden agregar notas a un ticket cerrado.")
    tickets.update_one({"_id": t["_id"]}, {
        "$set": {"updated_at": ahora()},
        "$push": {"bitacora": entrada_bitacora(data.nota, data.autor, t["estado"])},
    })
    return {"mensaje": "Nota agregada"}


@app.delete("/tickets/{ticket_id}", tags=["Tickets"])
def eliminar_ticket(ticket_id: str):
    t = obtener_ticket(ticket_id)
    # REGLA: solo se eliminan tickets Abiertos o Cancelados.
    # Los Resueltos son historial facturado y los En Proceso tienen trabajo en curso.
    if t["estado"] not in ("Abierto", "Cancelado"):
        raise HTTPException(409, f"No se puede eliminar un ticket {t['estado']}. "
                                 "Solo se eliminan tickets Abiertos o Cancelados.")
    tickets.delete_one({"_id": t["_id"]})
    return {"mensaje": f"Ticket {t['codigo']} eliminado"}


@app.get("/tickets/{ticket_id}/pdf", tags=["Tickets"])
def pdf_ticket(ticket_id: str):
    ticket = detalle_ticket(oid(ticket_id, "ticket"))
    contenido = generar_pdf_ticket(ticket)
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=orden_{ticket['codigo']}.pdf"},
    )


# ===========================================================================
# INVENTARIO DE REPUESTOS
# ===========================================================================
@app.get("/repuestos", tags=["Inventario"])
def listar_repuestos(buscar: Optional[str] = None, categoria: Optional[str] = None,
                     solo_stock_bajo: bool = False):
    filtro = {}
    if categoria:
        filtro["categoria"] = categoria
    if buscar:
        patron = {"$regex": re.escape(buscar), "$options": "i"}
        filtro["$or"] = [{"sku": patron}, {"nombre": patron}]
    if solo_stock_bajo:
        filtro["$expr"] = {"$lte": ["$stock", "$stock_minimo"]}
    return serializar(list(repuestos.find(filtro).sort("nombre", 1)))


@app.get("/repuestos/{repuesto_id}", tags=["Inventario"])
def ver_repuesto(repuesto_id: str):
    r = repuestos.find_one({"_id": oid(repuesto_id, "repuesto")})
    if not r:
        raise HTTPException(404, "Repuesto no encontrado.")
    return serializar(r)


@app.post("/repuestos", status_code=201, tags=["Inventario"])
def crear_repuesto(data: RepuestoCreate):
    # REGLA: el SKU (código) no se repite
    if repuestos.find_one({"sku": data.sku}):
        raise HTTPException(409, f"Ya existe un repuesto con el código {data.sku}.")
    momento = ahora()
    doc = data.model_dump()
    doc.update({"created_at": momento, "movimientos": [
        {"fecha": momento, "tipo": "Entrada", "cantidad": data.stock, "referencia": "Inventario inicial"}]})
    res = repuestos.insert_one(doc)
    return {"mensaje": "Repuesto creado", "id": str(res.inserted_id)}


@app.put("/repuestos/{repuesto_id}", tags=["Inventario"])
def actualizar_repuesto(repuesto_id: str, data: RepuestoUpdate):
    cambios = data.model_dump(exclude_none=True)
    if not cambios:
        raise HTTPException(400, "No se enviaron cambios.")
    res = repuestos.update_one({"_id": oid(repuesto_id, "repuesto")}, {"$set": cambios})
    if res.matched_count == 0:
        raise HTTPException(404, "Repuesto no encontrado.")
    return {"mensaje": "Repuesto actualizado"}


@app.post("/repuestos/{repuesto_id}/entrada", tags=["Inventario"])
def entrada_stock(repuesto_id: str, data: EntradaStock):
    """Registra la llegada de unidades (compra a proveedor). Guarda el movimiento embebido."""
    movimiento = {"fecha": ahora(), "tipo": "Entrada", "cantidad": data.cantidad, "referencia": data.nota}
    r = repuestos.find_one_and_update(
        {"_id": oid(repuesto_id, "repuesto")},
        {"$inc": {"stock": data.cantidad},
         "$push": {"movimientos": {"$each": [movimiento], "$slice": -50}}},  # solo los últimos 50
        return_document=ReturnDocument.AFTER,
    )
    if not r:
        raise HTTPException(404, "Repuesto no encontrado.")
    return {"mensaje": f"Entrada registrada. Nuevo stock de {r['nombre']}: {r['stock']}"}


@app.delete("/repuestos/{repuesto_id}", tags=["Inventario"])
def eliminar_repuesto(repuesto_id: str):
    _id = oid(repuesto_id, "repuesto")
    r = repuestos.find_one({"_id": _id})
    if not r:
        raise HTTPException(404, "Repuesto no encontrado.")
    # REGLA: un repuesto que ya se usó en tickets no se elimina (es parte del historial y del cobro)
    n = tickets.count_documents({"repuestos_usados.repuesto_id": _id})
    if n > 0:
        raise HTTPException(409, f"El repuesto se usó en {n} ticket(s); no se puede eliminar.")
    repuestos.delete_one({"_id": _id})
    return {"mensaje": f"Repuesto {r['sku']} eliminado"}


# ===========================================================================
# PORTAL DEL CLIENTE  (el cliente consulta su ticket y califica el servicio)
# ===========================================================================
NO_ENCONTRADO = "No encontramos un ticket con ese código y ese documento. Verifique los datos."


def ticket_de_cliente(codigo: str, documento: str) -> dict:
    """
    REGLA DE SEGURIDAD: el cliente solo ve su ticket si el código Y su cédula/NIT coinciden.
    Si algo no coincide se responde el mismo mensaje (no se revela si el código existe).
    """
    cliente = clientes.find_one({"documento": documento.strip()})
    if not cliente:
        raise HTTPException(404, NO_ENCONTRADO)
    t = tickets.find_one({"codigo": codigo.strip().upper(), "cliente_id": cliente["_id"]})
    if not t:
        raise HTTPException(404, NO_ENCONTRADO)
    return detalle_ticket(t["_id"])


@app.get("/portal/ticket", tags=["Portal del cliente"])
def portal_ver_ticket(codigo: str, documento: str):
    t = ticket_de_cliente(codigo, documento)
    tecnico = t.get("tecnico") or {}
    # Solo se devuelven los datos que el cliente necesita ver
    return serializar({
        "codigo": t["codigo"], "estado": t["estado"], "prioridad": t["prioridad"],
        "categoria": t["categoria"], "descripcion": t["descripcion"],
        "equipo": {k: t["equipo"].get(k) for k in ("nombre", "tipo", "marca", "serial")},
        "cliente": (t.get("cliente") or {}).get("nombre"),
        "tecnico": tecnico.get("nombre"),
        "created_at": t["created_at"], "resolved_at": t.get("resolved_at"),
        "costo": t.get("costo", 0), "costo_mano_obra": t.get("costo_mano_obra", 0),
        "costo_repuestos": t.get("costo_repuestos", 0),
        "repuestos_usados": [{k: r[k] for k in ("nombre", "cantidad", "subtotal")}
                             for r in t.get("repuestos_usados") or []],
        "foto_url": t.get("foto_url"),
        "bitacora": [{"fecha": b["fecha"], "estado": b.get("estado"), "nota": b["nota"]}
                     for b in t.get("bitacora", [])],
        "calificacion": t.get("calificacion"),
    })


@app.get("/portal/ticket/pdf", tags=["Portal del cliente"])
def portal_pdf(codigo: str, documento: str):
    t = ticket_de_cliente(codigo, documento)
    return Response(content=generar_pdf_ticket(t), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=orden_{t['codigo']}.pdf"})


@app.post("/portal/calificar", tags=["Portal del cliente"])
def portal_calificar(data: Calificacion):
    t = ticket_de_cliente(data.codigo, data.documento)
    # REGLA: solo se califica un servicio resuelto
    if t["estado"] != "Resuelto":
        raise HTTPException(409, "Solo se puede calificar un servicio que ya fue resuelto.")
    calificacion = {"puntaje": data.puntaje, "comentario": data.comentario or None, "fecha": ahora()}
    # REGLA: cada servicio se califica UNA sola vez (el filtro exige que aún no tenga calificación)
    res = tickets.update_one(
        {"_id": t["_id"], "calificacion": None},
        {"$set": {"calificacion": calificacion},
         "$push": {"bitacora": entrada_bitacora(
             f"El cliente calificó el servicio con {data.puntaje}/5.", (t.get("cliente") or {}).get("nombre",
                                                                                              "Cliente"),
             "Resuelto")}},
    )
    if res.modified_count == 0:
        raise HTTPException(409, "Este servicio ya fue calificado. ¡Gracias por su opinión!")
    return {"mensaje": "¡Gracias! Su calificación fue registrada."}


# ===========================================================================
# INTELIGENCIA ARTIFICIAL — Google Gemini (Google Cloud)
# ===========================================================================
@app.post("/ia/sugerir", tags=["Inteligencia artificial"])
def ia_sugerir(data: SolicitudIA):
    """Sugiere categoría, prioridad, diagnóstico y pasos a partir de la descripción."""
    try:
        return ia.sugerir_ticket(data.descripcion, data.equipo_tipo, data.equipo_nombre)
    except ia.ErrorIA as e:
        raise HTTPException(503, str(e))


@app.get("/ia/resumen-analitica", tags=["Inteligencia artificial"])
def ia_resumen():
    """Resume los indicadores del sistema en un informe ejecutivo escrito por la IA."""
    indicadores = {
        "resumen_general": resumen(),
        "rendimiento_tecnicos": rendimiento_tecnicos(),
        "por_categoria": por_categoria(),
        "top_clientes": top_clientes(5),
        "por_tipo_cliente": por_tipo_cliente(),
        "satisfaccion_por_tecnico": satisfaccion(),
        "repuestos_mas_usados": repuestos_mas_usados(),
        "stock_bajo": stock_bajo(),
    }
    try:
        return {"informe": ia.resumen_ejecutivo(indicadores), "modelo": "Google Gemini"}
    except ia.ErrorIA as e:
        raise HTTPException(503, str(e))


# ===========================================================================
# CLOUDINARY: subida de fotos de evidencia
# ===========================================================================
TIPOS_IMAGEN = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB


@app.post("/upload", tags=["Evidencias"])
def subir_evidencia(file: UploadFile = File(...)):
    if not CLOUDINARY_OK:
        raise HTTPException(503, "Cloudinary no está configurado en el servidor.")
    if file.content_type not in TIPOS_IMAGEN:
        raise HTTPException(400, "Solo se permiten imágenes JPG, PNG o WEBP.")
    contenido = file.file.read()
    if len(contenido) > MAX_BYTES:
        raise HTTPException(400, "La imagen supera el tamaño máximo de 5 MB.")
    try:
        resultado = cloudinary.uploader.upload(contenido, folder="servifix/evidencias")
    except Exception as e:
        raise HTTPException(502, f"Error al subir a Cloudinary: {e}")
    return {"url": resultado.get("secure_url")}


# ===========================================================================
# ANALÍTICA  (Aggregation Pipeline — ver consultas.py)
# ===========================================================================
@app.get("/analytics/resumen", tags=["Analítica"])
def resumen():
    r = list(tickets.aggregate(q.pipeline_resumen()))[0]
    por_estado = {e: 0 for e in ESTADOS}
    por_estado.update({x["_id"]: x["total"] for x in r["por_estado"]})
    por_prioridad = {p: 0 for p in PRIORIDADES}
    por_prioridad.update({x["_id"]: x["total"] for x in r["por_prioridad_activos"]})
    res = r["resueltos"][0] if r["resueltos"] else {}
    sat = r["satisfaccion"][0] if r["satisfaccion"] else {}
    return {
        "satisfaccion_promedio": round(sat.get("promedio") or 0, 2),
        "encuestas": sat.get("encuestas", 0),
        "repuestos_stock_bajo": len(list(repuestos.aggregate(q.pipeline_stock_bajo()))),
        "total_tickets": sum(por_estado.values()),
        "por_estado": por_estado,
        "activos_por_prioridad": por_prioridad,
        "ingresos": res.get("ingresos", 0),
        "costo_promedio": round(res.get("costo_promedio") or 0),
        "horas_promedio_resolucion": round(res.get("horas_promedio") or 0, 1),
        "total_clientes": clientes.count_documents({}),
        "tecnicos_activos": tecnicos.count_documents({"activo": True}),
    }


@app.get("/analytics/rendimiento-tecnicos", tags=["Analítica"])
def rendimiento_tecnicos():
    return list(tickets.aggregate(q.pipeline_rendimiento_tecnicos()))


@app.get("/analytics/por-categoria", tags=["Analítica"])
def por_categoria():
    return list(tickets.aggregate(q.pipeline_por_categoria()))


@app.get("/analytics/top-clientes", tags=["Analítica"])
def top_clientes(limite: int = 5):
    return list(tickets.aggregate(q.pipeline_top_clientes(max(1, min(limite, 20)))))


@app.get("/analytics/por-ciudad", tags=["Analítica"])
def por_ciudad():
    return list(tickets.aggregate(q.pipeline_por_ciudad()))


@app.get("/analytics/por-mes", tags=["Analítica"])
def por_mes():
    return list(tickets.aggregate(q.pipeline_por_mes()))


@app.get("/analytics/por-tipo-cliente", tags=["Analítica"])
def por_tipo_cliente():
    return list(tickets.aggregate(q.pipeline_por_tipo_cliente()))


@app.get("/analytics/equipos-fallas", tags=["Analítica"])
def equipos_fallas():
    return list(tickets.aggregate(q.pipeline_equipos_con_mas_fallas()))


@app.get("/analytics/pendientes", tags=["Analítica"])
def pendientes(horas: int = 48):
    return list(tickets.aggregate(q.pipeline_pendientes_antiguos(max(1, horas))))


@app.get("/analytics/satisfaccion", tags=["Analítica"])
def satisfaccion():
    return list(tickets.aggregate(q.pipeline_satisfaccion()))


@app.get("/analytics/comentarios", tags=["Analítica"])
def comentarios():
    return serializar(list(tickets.aggregate(q.pipeline_ultimos_comentarios())))


@app.get("/analytics/repuestos-mas-usados", tags=["Analítica"])
def repuestos_mas_usados():
    return list(tickets.aggregate(q.pipeline_repuestos_mas_usados()))


@app.get("/analytics/stock-bajo", tags=["Analítica"])
def stock_bajo():
    return list(repuestos.aggregate(q.pipeline_stock_bajo()))
