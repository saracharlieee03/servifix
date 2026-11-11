"""
interfaz_api.py
---------------
Funciones que usa la interfaz (Streamlit) para hablar con el backend (FastAPI).
La interfaz NUNCA se conecta directo a MongoDB: todo pasa por la API.

La dirección de la API se toma de (en este orden):
  1. st.secrets["API_URL"]   (Streamlit Cloud -> Settings -> Secrets)
  2. variable de entorno API_URL
  3. http://localhost:8000    (para trabajar en el computador)
"""
import os

import requests
import streamlit as st

TIMEOUT = 60  # segundos (Render gratis puede tardar ~50 s en "despertar")


def _hay_secrets() -> bool:
    """True si existe un secrets.toml (sin mostrar errores en pantalla si no existe)."""
    try:
        return bool(st.secrets.load_if_toml_exists())
    except AttributeError:
        rutas = [os.path.join(os.path.expanduser("~"), ".streamlit", "secrets.toml"),
                 os.path.join(os.getcwd(), ".streamlit", "secrets.toml")]
        return any(os.path.exists(r) for r in rutas)
    except Exception:
        return False


def _api_url() -> str:
    url = os.getenv("API_URL")
    if not url and _hay_secrets():
        url = st.secrets.get("API_URL")
    return (url or "http://localhost:8000").rstrip("/")


API_URL = _api_url()

# Traducción de los errores de validación de Pydantic (422) a español
_CAMPOS = {
    "nombre": "Nombre", "documento": "Cédula / NIT", "ciudad": "Ciudad", "direccion": "Dirección",
    "email": "Email", "telefono": "Teléfono", "especialidades": "Especialidades",
    "descripcion": "Descripción", "nota": "Nota", "costo": "Costo", "serial": "Serial",
    "marca": "Marca", "tipo": "Tipo", "categoria": "Categoría", "prioridad": "Prioridad",
    "autor": "Autor", "contacto": "Contacto", "sku": "Código (SKU)",
    "precio_unitario": "Precio unitario", "stock": "Stock", "stock_minimo": "Stock mínimo",
    "cantidad": "Cantidad", "puntaje": "Calificación", "comentario": "Comentario", "codigo": "Código",
}


def mensaje_validacion(err: dict) -> str:
    loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
    campo = " › ".join(_CAMPOS.get(x, x) for x in loc) or "Dato"
    tipo, ctx = err.get("type", ""), err.get("ctx") or {}
    if tipo == "string_too_short":
        return f"{campo}: debe tener al menos {ctx.get('min_length')} caracteres."
    if tipo == "string_too_long":
        return f"{campo}: máximo {ctx.get('max_length')} caracteres."
    if tipo == "string_pattern_mismatch":
        return f"{campo}: el formato no es válido."
    if tipo == "missing":
        return f"{campo}: es obligatorio."
    if tipo in ("greater_than_equal", "greater_than"):
        return f"{campo}: debe ser mayor o igual a {ctx.get('ge', ctx.get('gt'))}."
    if tipo == "too_short":
        return f"{campo}: seleccione al menos una opción."
    if tipo == "value_error":  # reglas escritas en los modelos (ej: cédula vs NIT)
        return err.get("msg", "").replace("Value error, ", "")
    if tipo == "literal_error":
        return f"{campo}: valor no permitido."
    return f"{campo}: {err.get('msg', 'valor no válido')}."


def _error(resp: requests.Response) -> str:
    try:
        detalle = resp.json().get("detail")
    except ValueError:
        return f"Error {resp.status_code} del servidor."
    if isinstance(detalle, list):
        return " ".join(mensaje_validacion(e) for e in detalle)
    return str(detalle)


def _llamar(metodo: str, ruta: str, **kwargs):
    """Hace la petición y devuelve (ok, datos_o_mensaje)."""
    try:
        resp = requests.request(metodo, f"{API_URL}{ruta}", timeout=TIMEOUT, **kwargs)
    except requests.exceptions.ConnectionError:
        return False, f"No se pudo conectar con la API ({API_URL}). ¿Está encendido el backend?"
    except requests.exceptions.Timeout:
        return False, "La API tardó demasiado en responder. Intente de nuevo."
    if resp.ok:
        if resp.headers.get("content-type", "").startswith("application/json"):
            return True, resp.json()
        return True, resp.content
    return False, _error(resp)


class _ErrorApi(Exception):
    pass


@st.cache_data(ttl=60, show_spinner=False)
def _get_cache(ruta: str, params: tuple):
    ok, datos = _llamar("GET", ruta, params=dict(params))
    if not ok:
        raise _ErrorApi(datos)  # los errores NO se guardan en caché
    return datos


def get(ruta: str, **params):
    """GET con caché de 60 s. Se limpia automáticamente después de cualquier cambio."""
    limpios = tuple(sorted((k, str(v)) for k, v in params.items() if v not in (None, "", [])))
    try:
        return True, _get_cache(ruta, limpios)
    except _ErrorApi as e:
        return False, str(e)


def get_directo(ruta: str, **params):
    """GET sin caché (para PDFs y consultas del portal)."""
    limpios = {k: v for k, v in params.items() if v not in (None, "", [])}
    return _llamar("GET", ruta, params=limpios)


def consultar(ruta: str, json=None):
    """POST que solo consulta (no cambia datos), por eso no limpia la caché. Ej: IA."""
    return _llamar("POST", ruta, json=json)


def post(ruta: str, json=None, files=None):
    r = _llamar("POST", ruta, json=json, files=files)
    st.cache_data.clear()
    return r


def put(ruta: str, json=None):
    r = _llamar("PUT", ruta, json=json)
    st.cache_data.clear()
    return r


def delete(ruta: str):
    r = _llamar("DELETE", ruta)
    st.cache_data.clear()
    return r
