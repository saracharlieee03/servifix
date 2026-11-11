"""
database.py
-----------
Conexión entre el backend (FastAPI) y la base de datos en la nube (MongoDB Atlas).

- La cadena de conexión NO está escrita en el código: se lee de la variable de
  entorno MONGO_URI (archivo .env en local, o "Environment" en Render).
- Aquí también se crean los índices de las colecciones.
"""
import os

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "servifix_db")

if not MONGO_URI:
    raise ValueError("No se encontró la variable MONGO_URI. Revisa tu archivo .env")

# tz_aware=True -> las fechas vuelven de Mongo con zona horaria (UTC)
# serverSelectionTimeoutMS -> si Atlas no responde, falla en 8 s en vez de quedarse colgado
client = MongoClient(MONGO_URI, tz_aware=True, serverSelectionTimeoutMS=8000)
db = client[DB_NAME]

# Colecciones del sistema
clientes = db["clientes"]
tecnicos = db["tecnicos"]
tickets = db["tickets"]
contadores = db["contadores"]  # guarda el consecutivo de los códigos de ticket
repuestos = db["repuestos"]    # inventario de repuestos


def crear_indices() -> None:
    """Índices: aceleran las búsquedas y garantizan datos únicos."""
    # Índice de la versión anterior (los clientes tenían "nit"); ya no se usa
    if "nit_1" in clientes.index_information():
        clientes.drop_index("nit_1")
    # Únicos: no puede haber dos tickets con el mismo código,
    # dos clientes con el mismo documento (cédula/NIT) ni dos técnicos con el mismo email.
    tickets.create_index([("codigo", ASCENDING)], unique=True)
    clientes.create_index([("documento", ASCENDING)], unique=True)
    clientes.create_index([("tipo", ASCENDING), ("ciudad", ASCENDING)])
    tecnicos.create_index([("email", ASCENDING)], unique=True)

    # Para filtros y consultas frecuentes
    tickets.create_index([("estado", ASCENDING), ("categoria", ASCENDING)])
    tickets.create_index([("tecnico_id", ASCENDING), ("estado", ASCENDING)])
    tickets.create_index([("cliente_id", ASCENDING)])
    tickets.create_index([("created_at", DESCENDING)])
    repuestos.create_index([("sku", ASCENDING)], unique=True)


def ping() -> bool:
    """Comprueba que Atlas responde."""
    client.admin.command("ping")
    return True
