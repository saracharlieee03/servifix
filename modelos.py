"""
modelos.py
----------
1) Constantes de negocio (categorías, estados, límites...).
2) Modelos Pydantic: definen qué datos acepta la API y los VALIDAN antes de
   tocar la base de datos. Si algo no cumple, FastAPI responde 422 con el error.
"""
import re
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# CONSTANTES DE NEGOCIO
# ---------------------------------------------------------------------------
CATEGORIAS = ["Hardware", "Software", "Redes", "Preventivo"]
PRIORIDADES = ["Baja", "Media", "Alta", "Crítica"]
ESTADOS = ["Abierto", "En Proceso", "Resuelto", "Cancelado"]
TIPOS_CLIENTE = ["Persona", "Empresa"]   # persona natural o empresa
CATEGORIAS_REPUESTO = ["Componentes", "Redes", "Consumibles", "Equipo médico", "Otros"]
TIPOS_EQUIPO = ["Computador", "Servidor", "Impresora", "Red", "Proyector",
                "Equipo médico", "Industrial", "Otro"]

# Un técnico no puede tener más de 3 tickets "En Proceso" al mismo tiempo
MAX_TICKETS_ACTIVOS = 3
ESTADOS_ACTIVOS = ["En Proceso"]
ESTADOS_FINALES = ["Resuelto", "Cancelado"]

# Cambios de estado permitidos (máquina de estados).
# "Abierto" -> "En Proceso" solo ocurre al ASIGNAR un técnico (endpoint /asignar).
TRANSICIONES = {
    "Abierto": ["Cancelado"],
    "En Proceso": ["Resuelto", "Cancelado"],
    "Resuelto": [],
    "Cancelado": [],
}

Categoria = Literal["Hardware", "Software", "Redes", "Preventivo"]
CategoriaRepuesto = Literal["Componentes", "Redes", "Consumibles", "Equipo médico", "Otros"]
Prioridad = Literal["Baja", "Media", "Alta", "Crítica"]
TipoEquipo = Literal["Computador", "Servidor", "Impresora", "Red", "Proyector",
                     "Equipo médico", "Industrial", "Otro"]

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
TELEFONO = r"^\+?[0-9 \-]{7,15}$"
DOCUMENTO = r"^[0-9]{6,10}(-[0-9])?$"   # forma general (cédula o NIT)
CEDULA = r"^[0-9]{6,10}$"               # persona: solo dígitos
NIT = r"^[0-9]{9}(-[0-9])?$"            # empresa: 9 dígitos + dígito de verificación opcional


class Base(BaseModel):
    # Quita espacios al inicio/fin de todos los textos
    model_config = ConfigDict(str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# CLIENTES  (pueden ser PERSONAS o EMPRESAS; contacto y equipos van EMBEBIDOS)
# ---------------------------------------------------------------------------
class Contacto(Base):
    # En una empresa es la persona que reporta; en una persona natural es ella misma
    nombre: Optional[str] = Field(default=None, min_length=3, max_length=80)
    email: str = Field(pattern=EMAIL)
    telefono: str = Field(pattern=TELEFONO)


class EquipoIn(Base):
    nombre: str = Field(min_length=3, max_length=80)
    tipo: TipoEquipo
    marca: str = Field(min_length=2, max_length=40)
    serial: str = Field(min_length=3, max_length=40)


class ClienteCreate(Base):
    tipo: Literal["Persona", "Empresa"]
    nombre: str = Field(min_length=3, max_length=100)        # nombre completo o razón social
    documento: str = Field(pattern=DOCUMENTO)                # cédula o NIT
    ciudad: str = Field(min_length=3, max_length=50)
    direccion: str = Field(min_length=5, max_length=120)
    contacto: Contacto

    @model_validator(mode="after")
    def reglas_por_tipo(self):
        if self.tipo == "Persona":
            # REGLA: la cédula son solo dígitos y el contacto es la misma persona
            if not re.fullmatch(CEDULA, self.documento):
                raise ValueError("La cédula debe tener entre 6 y 10 dígitos, sin puntos ni guiones.")
            self.contacto.nombre = self.nombre
        else:
            # REGLA: el NIT tiene 9 dígitos y la empresa debe indicar quién reporta
            if not re.fullmatch(NIT, self.documento):
                raise ValueError("El NIT debe tener 9 dígitos y, opcionalmente, el dígito de verificación (ej: 900123456-7).")
            if not self.contacto.nombre:
                raise ValueError("Para una empresa indique el nombre de la persona de contacto.")
        return self


class ClienteUpdate(Base):
    nombre: Optional[str] = Field(default=None, min_length=3, max_length=100)
    ciudad: Optional[str] = Field(default=None, min_length=3, max_length=50)
    direccion: Optional[str] = Field(default=None, min_length=5, max_length=120)
    contacto: Optional[Contacto] = None


# ---------------------------------------------------------------------------
# TÉCNICOS
# ---------------------------------------------------------------------------
class TecnicoCreate(Base):
    nombre: str = Field(min_length=3, max_length=80)
    email: str = Field(pattern=EMAIL)
    telefono: str = Field(pattern=TELEFONO)
    especialidades: List[Categoria] = Field(min_length=1)
    activo: bool = True


class TecnicoUpdate(Base):
    nombre: Optional[str] = Field(default=None, min_length=3, max_length=80)
    email: Optional[str] = Field(default=None, pattern=EMAIL)
    telefono: Optional[str] = Field(default=None, pattern=TELEFONO)
    especialidades: Optional[List[Categoria]] = Field(default=None, min_length=1)
    activo: Optional[bool] = None


# ---------------------------------------------------------------------------
# TICKETS
# ---------------------------------------------------------------------------
class TicketCreate(Base):
    cliente_id: str
    equipo_id: str
    categoria: Categoria
    prioridad: Prioridad = "Media"
    descripcion: str = Field(min_length=10, max_length=600)
    diagnostico_ia: Optional[str] = Field(default=None, max_length=1500)  # sugerencia de Gemini (opcional)


class TicketUpdate(Base):
    categoria: Optional[Categoria] = None
    prioridad: Optional[Prioridad] = None
    descripcion: Optional[str] = Field(default=None, min_length=10, max_length=600)


class TicketAsignar(Base):
    tecnico_id: str


class RepuestoUso(Base):
    repuesto_id: str
    cantidad: int = Field(ge=1, le=100)


class TicketEstado(Base):
    estado: Literal["Resuelto", "Cancelado"]
    nota: str = Field(min_length=5, max_length=400)
    costo: float = Field(default=0, ge=0, le=100_000_000)   # costo de MANO DE OBRA
    foto_url: Optional[str] = None
    repuestos: List[RepuestoUso] = Field(default_factory=list)  # repuestos usados (solo al resolver)


class TicketNota(Base):
    nota: str = Field(min_length=3, max_length=400)
    autor: str = Field(min_length=3, max_length=80)


# ---------------------------------------------------------------------------
# INVENTARIO DE REPUESTOS
# ---------------------------------------------------------------------------
SKU = r"^[A-Z0-9\-]{3,20}$"


class RepuestoCreate(Base):
    sku: str = Field(pattern=SKU)                    # código interno, ej: FTE-500W
    nombre: str = Field(min_length=3, max_length=80)
    categoria: CategoriaRepuesto
    precio_unitario: float = Field(gt=0, le=50_000_000)
    stock: int = Field(ge=0, le=100_000)
    stock_minimo: int = Field(ge=0, le=10_000)


class RepuestoUpdate(Base):
    # El stock NO se edita aquí: solo cambia con entradas o al usarse en un ticket (trazabilidad)
    nombre: Optional[str] = Field(default=None, min_length=3, max_length=80)
    categoria: Optional[CategoriaRepuesto] = None
    precio_unitario: Optional[float] = Field(default=None, gt=0, le=50_000_000)
    stock_minimo: Optional[int] = Field(default=None, ge=0, le=10_000)


class EntradaStock(Base):
    cantidad: int = Field(ge=1, le=10_000)
    nota: str = Field(default="Compra a proveedor", min_length=3, max_length=120)


# ---------------------------------------------------------------------------
# PORTAL DEL CLIENTE
# ---------------------------------------------------------------------------
class Calificacion(Base):
    codigo: str = Field(min_length=5, max_length=20)
    documento: str = Field(pattern=DOCUMENTO)
    puntaje: int = Field(ge=1, le=5)
    comentario: Optional[str] = Field(default=None, max_length=300)


# ---------------------------------------------------------------------------
# INTELIGENCIA ARTIFICIAL (Google Gemini)
# ---------------------------------------------------------------------------
class SolicitudIA(Base):
    descripcion: str = Field(min_length=10, max_length=600)
    equipo_tipo: Optional[str] = Field(default=None, max_length=40)
    equipo_nombre: Optional[str] = Field(default=None, max_length=80)
