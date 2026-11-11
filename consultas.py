"""
consultas.py
------------
Todas las consultas de agregación (Aggregation Pipeline) del proyecto.

Cada función devuelve un "pipeline": una lista de etapas que MongoDB ejecuta
en orden, como una cadena de montaje. Operadores usados:
$match, $lookup, $unwind, $group, $project, $sort, $limit, $facet, $addFields.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

ZONA_COLOMBIA = "-05:00"

# Expresión que calcula las horas entre la creación y la resolución de un ticket
HORAS_RESOLUCION = {
    "$divide": [{"$subtract": ["$resolved_at", "$created_at"]}, 1000 * 60 * 60]
}


# ---------------------------------------------------------------------------
# 1. LISTADO DE TICKETS CON RELACIONES (se usa en la pantalla "Tickets")
# ---------------------------------------------------------------------------
def pipeline_tickets(filtro: dict, texto: Optional[str] = None) -> list:
    """
    Trae los tickets con el NOMBRE del cliente y del técnico (no solo su ID).
    - filtro: condiciones directas sobre el ticket (estado, categoría, fechas...)
    - texto: búsqueda libre en código, cliente, equipo, serial o descripción
    """
    pipeline = [
        {"$match": filtro},
        # REFERENCING: el ticket guarda cliente_id -> traemos el documento del cliente
        {"$lookup": {"from": "clientes", "localField": "cliente_id",
                     "foreignField": "_id", "as": "cliente"}},
        {"$unwind": {"path": "$cliente", "preserveNullAndEmptyArrays": True}},
        # REFERENCING: el ticket guarda tecnico_id -> traemos el documento del técnico
        {"$lookup": {"from": "tecnicos", "localField": "tecnico_id",
                     "foreignField": "_id", "as": "tecnico"}},
        {"$unwind": {"path": "$tecnico", "preserveNullAndEmptyArrays": True}},
    ]

    if texto:
        patron = {"$regex": re.escape(texto), "$options": "i"}  # sin distinguir mayúsculas
        pipeline.append({"$match": {"$or": [
            {"codigo": patron},
            {"cliente.nombre": patron},
            {"equipo.nombre": patron},
            {"equipo.serial": patron},
            {"descripcion": patron},
        ]}})

    pipeline += [
        {"$sort": {"created_at": -1}},
        {"$project": {
            "codigo": 1, "categoria": 1, "prioridad": 1, "descripcion": 1,
            "estado": 1, "costo": 1, "foto_url": 1, "equipo": 1, "bitacora": 1,
            "costo_mano_obra": 1, "costo_repuestos": 1, "repuestos_usados": 1,
            "calificacion": 1, "diagnostico_ia": 1,
            "created_at": 1, "updated_at": 1, "resolved_at": 1,
            "cliente_id": 1, "tecnico_id": 1,
            "cliente": {"nombre": "$cliente.nombre", "tipo": "$cliente.tipo",
                        "documento": "$cliente.documento",
                        "ciudad": "$cliente.ciudad", "direccion": "$cliente.direccion",
                        "contacto": "$cliente.contacto"},
            "tecnico": {"nombre": "$tecnico.nombre", "email": "$tecnico.email",
                        "telefono": "$tecnico.telefono",
                        "especialidades": "$tecnico.especialidades"},
        }},
    ]
    return pipeline


# ---------------------------------------------------------------------------
# 2. TÉCNICOS CON SU CARGA DE TRABAJO
# ---------------------------------------------------------------------------
def pipeline_tecnicos_con_carga(filtro: dict) -> list:
    """Lista de técnicos + cuántos tickets tienen activos y cuántos han resuelto."""
    return [
        {"$match": filtro},
        {"$lookup": {
            "from": "tickets",
            "localField": "_id",
            "foreignField": "tecnico_id",
            "as": "sus_tickets",
        }},
        {"$addFields": {
            "carga_actual": {"$size": {"$filter": {
                "input": "$sus_tickets", "cond": {"$eq": ["$$this.estado", "En Proceso"]}}}},
            "total_resueltos": {"$size": {"$filter": {
                "input": "$sus_tickets", "cond": {"$eq": ["$$this.estado", "Resuelto"]}}}},
        }},
        {"$project": {"sus_tickets": 0}},
        {"$sort": {"nombre": 1}},
    ]


# ---------------------------------------------------------------------------
# 3. INDICADORES GENERALES (tarjetas del inicio)
# ---------------------------------------------------------------------------
def pipeline_resumen() -> list:
    """$facet ejecuta varias agregaciones en paralelo sobre los mismos datos."""
    return [
        {"$facet": {
            "por_estado": [
                {"$group": {"_id": "$estado", "total": {"$sum": 1}}},
            ],
            "por_prioridad_activos": [
                {"$match": {"estado": {"$in": ["Abierto", "En Proceso"]}}},
                {"$group": {"_id": "$prioridad", "total": {"$sum": 1}}},
            ],
            "satisfaccion": [
                {"$match": {"calificacion.puntaje": {"$exists": True}}},
                {"$group": {"_id": None, "promedio": {"$avg": "$calificacion.puntaje"},
                            "encuestas": {"$sum": 1}}},
            ],
            "resueltos": [
                {"$match": {"estado": "Resuelto"}},
                {"$group": {
                    "_id": None,
                    "ingresos": {"$sum": "$costo"},
                    "costo_promedio": {"$avg": "$costo"},
                    "horas_promedio": {"$avg": HORAS_RESOLUCION},
                }},
            ],
        }},
    ]


# ---------------------------------------------------------------------------
# 4. RENDIMIENTO POR TÉCNICO (ranking)
# Pregunta: ¿qué técnico resuelve más, genera más ingresos y es más rápido?
# ---------------------------------------------------------------------------
def pipeline_rendimiento_tecnicos() -> list:
    return [
        {"$match": {"estado": "Resuelto"}},
        {"$lookup": {"from": "tecnicos", "localField": "tecnico_id",
                     "foreignField": "_id", "as": "tecnico_info"}},
        {"$unwind": "$tecnico_info"},
        {"$group": {
            "_id": "$tecnico_info.nombre",
            "total_resueltos": {"$sum": 1},
            "ingresos_totales": {"$sum": "$costo"},
            "costo_promedio": {"$avg": "$costo"},
            "horas_promedio": {"$avg": HORAS_RESOLUCION},
        }},
        {"$sort": {"total_resueltos": -1, "ingresos_totales": -1}},
        {"$project": {
            "_id": 0,
            "tecnico": "$_id",
            "total_resueltos": 1,
            "ingresos_totales": 1,
            "costo_promedio": {"$round": ["$costo_promedio", 0]},
            "horas_promedio": {"$round": ["$horas_promedio", 1]},
        }},
    ]


# ---------------------------------------------------------------------------
# 5. ANÁLISIS POR CATEGORÍA
# Pregunta: ¿qué tipo de servicio se pide más y cuál deja más ingresos?
# ---------------------------------------------------------------------------
def pipeline_por_categoria() -> list:
    return [
        {"$group": {
            "_id": "$categoria",
            "total": {"$sum": 1},
            "resueltos": {"$sum": {"$cond": [{"$eq": ["$estado", "Resuelto"]}, 1, 0]}},
            "ingresos": {"$sum": {"$cond": [{"$eq": ["$estado", "Resuelto"]}, "$costo", 0]}},
        }},
        {"$project": {
            "_id": 0,
            "categoria": "$_id",
            "total": 1,
            "resueltos": 1,
            "ingresos": 1,
            "tasa_resolucion": {"$round": [
                {"$multiply": [{"$divide": ["$resueltos", "$total"]}, 100]}, 1]},
        }},
        {"$sort": {"total": -1}},
    ]


# ---------------------------------------------------------------------------
# 6. TOP CLIENTES POR GASTO
# Pregunta: ¿cuáles son los clientes más valiosos para la empresa?
# ---------------------------------------------------------------------------
def pipeline_top_clientes(limite: int = 5) -> list:
    return [
        {"$match": {"estado": "Resuelto"}},
        {"$group": {
            "_id": "$cliente_id",
            "servicios": {"$sum": 1},
            "gasto_total": {"$sum": "$costo"},
        }},
        {"$sort": {"gasto_total": -1}},
        {"$limit": limite},
        {"$lookup": {"from": "clientes", "localField": "_id",
                     "foreignField": "_id", "as": "cliente"}},
        {"$unwind": "$cliente"},
        {"$project": {
            "_id": 0,
            "cliente": "$cliente.nombre",
            "tipo": "$cliente.tipo",
            "ciudad": "$cliente.ciudad",
            "servicios": 1,
            "gasto_total": 1,
        }},
    ]


# ---------------------------------------------------------------------------
# 7. TICKETS E INGRESOS POR CIUDAD
# Pregunta: ¿en qué ciudades hay más demanda de soporte?
# ---------------------------------------------------------------------------
def pipeline_por_ciudad() -> list:
    return [
        {"$lookup": {"from": "clientes", "localField": "cliente_id",
                     "foreignField": "_id", "as": "cliente"}},
        {"$unwind": "$cliente"},
        {"$group": {
            "_id": "$cliente.ciudad",
            "tickets": {"$sum": 1},
            "ingresos": {"$sum": {"$cond": [{"$eq": ["$estado", "Resuelto"]}, "$costo", 0]}},
        }},
        {"$sort": {"tickets": -1}},
        {"$project": {"_id": 0, "ciudad": "$_id", "tickets": 1, "ingresos": 1}},
    ]


# ---------------------------------------------------------------------------
# 7b. PERSONAS VS. EMPRESAS
# Pregunta: ¿quién genera más trabajo e ingresos, las personas o las empresas?
# ---------------------------------------------------------------------------
def pipeline_por_tipo_cliente() -> list:
    return [
        {"$lookup": {"from": "clientes", "localField": "cliente_id",
                     "foreignField": "_id", "as": "cliente"}},
        {"$unwind": "$cliente"},
        {"$group": {
            "_id": "$cliente.tipo",
            "tickets": {"$sum": 1},
            "clientes": {"$addToSet": "$cliente_id"},
            "resueltos": {"$sum": {"$cond": [{"$eq": ["$estado", "Resuelto"]}, 1, 0]}},
            "ingresos": {"$sum": {"$cond": [{"$eq": ["$estado", "Resuelto"]}, "$costo", 0]}},
        }},
        {"$project": {
            "_id": 0,
            "tipo": "$_id",
            "tickets": 1,
            "clientes": {"$size": "$clientes"},
            "ingresos": 1,
            "ticket_promedio": {"$cond": [{"$gt": ["$resueltos", 0]},
                                          {"$round": [{"$divide": ["$ingresos", "$resueltos"]}, 0]}, 0]},
        }},
        {"$sort": {"ingresos": -1}},
    ]


# ---------------------------------------------------------------------------
# 8. EVOLUCIÓN MENSUAL
# Pregunta: ¿cómo cambia la demanda y los ingresos mes a mes?
# ---------------------------------------------------------------------------
def pipeline_por_mes() -> list:
    return [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at",
                                      "timezone": ZONA_COLOMBIA}},
            "creados": {"$sum": 1},
            "resueltos": {"$sum": {"$cond": [{"$eq": ["$estado", "Resuelto"]}, 1, 0]}},
            "ingresos": {"$sum": {"$cond": [{"$eq": ["$estado", "Resuelto"]}, "$costo", 0]}},
        }},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "mes": "$_id", "creados": 1, "resueltos": 1, "ingresos": 1}},
    ]


# ---------------------------------------------------------------------------
# 9. TIPOS DE EQUIPO CON MÁS FALLAS
# Pregunta: ¿qué equipos fallan más? (útil para planear mantenimiento preventivo)
# ---------------------------------------------------------------------------
def pipeline_equipos_con_mas_fallas(limite: int = 8) -> list:
    return [
        {"$match": {"categoria": {"$ne": "Preventivo"}}},
        {"$group": {"_id": "$equipo.tipo", "fallas": {"$sum": 1}}},
        {"$sort": {"fallas": -1}},
        {"$limit": limite},
        {"$project": {"_id": 0, "tipo_equipo": "$_id", "fallas": 1}},
    ]


# ---------------------------------------------------------------------------
# 10. ALERTA: TICKETS ABIERTOS SIN ASIGNAR HACE MÁS DE N HORAS
# Pregunta: ¿qué solicitudes están esperando demasiado?
# ---------------------------------------------------------------------------
def pipeline_pendientes_antiguos(horas: int = 48) -> list:
    limite = datetime.now(timezone.utc) - timedelta(hours=horas)
    ahora = datetime.now(timezone.utc)
    return [
        {"$match": {"estado": "Abierto", "created_at": {"$lte": limite}}},
        {"$lookup": {"from": "clientes", "localField": "cliente_id",
                     "foreignField": "_id", "as": "cliente"}},
        {"$unwind": "$cliente"},
        {"$project": {
            "_id": 0,
            "codigo": 1,
            "cliente": "$cliente.nombre",
            "equipo": "$equipo.nombre",
            "prioridad": 1,
            "horas_esperando": {"$round": [
                {"$divide": [{"$subtract": [ahora, "$created_at"]}, 1000 * 60 * 60]}, 0]},
        }},
        {"$sort": {"horas_esperando": -1}},
    ]


# ---------------------------------------------------------------------------
# 11. SATISFACCIÓN DEL CLIENTE POR TÉCNICO (encuestas del portal)
# Pregunta: ¿qué técnicos dejan más satisfechos a los clientes?
# ---------------------------------------------------------------------------
def pipeline_satisfaccion() -> list:
    return [
        {"$match": {"calificacion.puntaje": {"$exists": True}}},
        {"$lookup": {"from": "tecnicos", "localField": "tecnico_id",
                     "foreignField": "_id", "as": "tecnico"}},
        {"$unwind": "$tecnico"},
        {"$group": {
            "_id": "$tecnico.nombre",
            "promedio": {"$avg": "$calificacion.puntaje"},
            "encuestas": {"$sum": 1},
            "cinco_estrellas": {"$sum": {"$cond": [{"$eq": ["$calificacion.puntaje", 5]}, 1, 0]}},
        }},
        {"$sort": {"promedio": -1, "encuestas": -1}},
        {"$project": {"_id": 0, "tecnico": "$_id", "promedio": {"$round": ["$promedio", 2]},
                      "encuestas": 1, "cinco_estrellas": 1}},
    ]


def pipeline_ultimos_comentarios(limite: int = 6) -> list:
    return [
        {"$match": {"calificacion.comentario": {"$nin": [None, ""]}}},
        {"$sort": {"calificacion.fecha": -1}},
        {"$limit": limite},
        {"$lookup": {"from": "clientes", "localField": "cliente_id",
                     "foreignField": "_id", "as": "cliente"}},
        {"$unwind": "$cliente"},
        {"$project": {"_id": 0, "codigo": 1, "cliente": "$cliente.nombre",
                      "puntaje": "$calificacion.puntaje", "comentario": "$calificacion.comentario",
                      "fecha": "$calificacion.fecha"}},
    ]


# ---------------------------------------------------------------------------
# 12. REPUESTOS MÁS USADOS
# Pregunta: ¿qué repuestos se consumen más y cuánto dinero representan?
# $unwind "abre" el arreglo embebido repuestos_usados: un documento por repuesto
# ---------------------------------------------------------------------------
def pipeline_repuestos_mas_usados(limite: int = 10) -> list:
    return [
        {"$match": {"estado": "Resuelto"}},
        {"$unwind": "$repuestos_usados"},
        {"$group": {
            "_id": "$repuestos_usados.nombre",
            "unidades": {"$sum": "$repuestos_usados.cantidad"},
            "valor": {"$sum": "$repuestos_usados.subtotal"},
            "tickets": {"$sum": 1},
        }},
        {"$sort": {"unidades": -1, "valor": -1}},
        {"$limit": limite},
        {"$project": {"_id": 0, "repuesto": "$_id", "unidades": 1, "valor": 1, "tickets": 1}},
    ]


# ---------------------------------------------------------------------------
# 13. ALERTA DE STOCK BAJO
# Pregunta: ¿qué repuestos hay que volver a comprar?
# $expr permite comparar dos campos del mismo documento (stock vs stock_minimo)
# ---------------------------------------------------------------------------
def pipeline_stock_bajo() -> list:
    return [
        {"$match": {"$expr": {"$lte": ["$stock", "$stock_minimo"]}}},
        {"$project": {"_id": 0, "sku": 1, "nombre": 1, "categoria": 1, "stock": 1, "stock_minimo": 1,
                      "faltante": {"$subtract": ["$stock_minimo", "$stock"]}}},
        {"$sort": {"stock": 1}},
    ]
