"""
ia.py
-----
Integración con GOOGLE CLOUD: Inteligencia artificial con Google Gemini.

- sugerir_ticket(): a partir de la descripción de la falla sugiere categoría,
  prioridad, un posible diagnóstico y los pasos recomendados.
- resumen_ejecutivo(): convierte los indicadores de la analítica en un
  informe corto en lenguaje natural para la gerencia.

La clave se lee de la variable de entorno GEMINI_API_KEY (nunca va en el código).
Se crea gratis en https://aistudio.google.com/apikey
"""
import json
import os
import time

import requests
from dotenv import load_dotenv

from modelos import CATEGORIAS, PRIORIDADES

load_dotenv()  # lee GEMINI_API_KEY y GEMINI_MODEL del archivo .env

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

# Si un modelo no existe en la cuenta, se intenta con el siguiente
MODELOS = list(dict.fromkeys(m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.5-flash-lite",
                                         "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"] if m))
OCUPADO = (429, 500, 503, 504)  # límite alcanzado o modelo saturado: se reintenta / se prueba otro


class ErrorIA(Exception):
    pass


def configurada() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def _llamar_gemini(prompt: str, json_salida: bool) -> str:
    clave = os.getenv("GEMINI_API_KEY")
    if not clave:
        raise ErrorIA("La IA no está configurada: falta GEMINI_API_KEY en el archivo .env del backend.")
    cuerpo = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    if json_salida:
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"

    ultimo_error = "sin respuesta"
    hubo_saturacion = False
    for modelo in MODELOS:
        for intento in range(2):  # si el modelo está saturado, se espera un momento y se reintenta
            try:
                r = requests.post(URL.format(modelo=modelo), json=cuerpo, timeout=30,
                                  headers={"x-goog-api-key": clave, "Content-Type": "application/json"})
            except requests.RequestException as e:
                raise ErrorIA(f"No se pudo conectar con Google Gemini: {e}")
            if r.status_code in OCUPADO and intento == 0:
                time.sleep(2)
                continue
            break
        if r.status_code == 404:          # modelo no disponible -> probar el siguiente
            ultimo_error = f"modelo {modelo} no disponible"
            continue
        if r.status_code in OCUPADO:      # saturado o sin cupo -> probar el siguiente modelo
            hubo_saturacion = True
            ultimo_error = f"modelo {modelo} ocupado ({r.status_code})"
            continue
        if r.status_code in (400, 401, 403):
            raise ErrorIA("Google Gemini rechazó la solicitud. Revise que GEMINI_API_KEY sea correcta.")
        if not r.ok:
            raise ErrorIA(f"Error de Google Gemini ({r.status_code}).")
        try:
            partes = r.json()["candidates"][0]["content"]["parts"]
            texto = "".join(p.get("text", "") for p in partes)
        except (KeyError, IndexError, ValueError):
            raise ErrorIA("Gemini respondió en un formato inesperado.")
        if texto.strip():
            return texto
        ultimo_error = "respuesta vacía"
    if hubo_saturacion:
        raise ErrorIA("Google Gemini está saturado en este momento (muchas solicitudes en el plan gratuito). "
                      "Espere unos segundos e intente de nuevo.")
    raise ErrorIA(f"Ningún modelo de Gemini respondió ({ultimo_error}).")


def sugerir_ticket(descripcion: str, equipo_tipo: str = None, equipo_nombre: str = None) -> dict:
    prompt = f"""Eres el coordinador de una empresa colombiana de soporte técnico llamada ServiFix.
Analiza esta solicitud de un cliente y responde SOLO con un JSON con estas claves:
- "categoria": una de {CATEGORIAS}
- "prioridad": una de {PRIORIDADES} (Crítica solo si afecta salud, dinero o a toda una organización)
- "diagnostico": posible causa de la falla, máximo 2 frases, en español
- "pasos": lista de 3 a 4 pasos cortos que debería seguir el técnico, en español
- "justificacion": una frase que explique la prioridad elegida

Equipo: {equipo_nombre or 'no especificado'} (tipo: {equipo_tipo or 'no especificado'})
Descripción de la falla: {descripcion}"""
    texto = _llamar_gemini(prompt, json_salida=True)
    try:
        datos = json.loads(texto.strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError:
        raise ErrorIA("No se pudo interpretar la respuesta de la IA. Intente de nuevo.")

    # Validación: la IA solo SUGIERE; si devuelve algo fuera de las listas se corrige
    categoria = datos.get("categoria") if datos.get("categoria") in CATEGORIAS else "Hardware"
    prioridad = datos.get("prioridad") if datos.get("prioridad") in PRIORIDADES else "Media"
    pasos = datos.get("pasos") if isinstance(datos.get("pasos"), list) else []
    return {
        "categoria": categoria,
        "prioridad": prioridad,
        "diagnostico": str(datos.get("diagnostico", ""))[:600],
        "pasos": [str(p)[:200] for p in pasos[:5]],
        "justificacion": str(datos.get("justificacion", ""))[:300],
        "modelo": "Google Gemini",
    }


def resumen_ejecutivo(indicadores: dict) -> str:
    prompt = f"""Eres analista de operaciones de ServiFix, empresa colombiana de soporte técnico.
Con estos indicadores (montos en pesos colombianos) escribe un informe ejecutivo en español, en
formato Markdown, con: un párrafo de situación general, 3 hallazgos clave en viñetas y 3
recomendaciones concretas en viñetas. Máximo 220 palabras. No inventes datos que no estén aquí.

Indicadores:
{json.dumps(indicadores, ensure_ascii=False, default=str, indent=1)}"""
    return _llamar_gemini(prompt, json_salida=False).strip()
