"""
interfaz_estilos.py
-------------------
Estilos visuales (CSS) y pequeños componentes HTML de la interfaz:
tarjetas de indicadores, etiquetas de estado, encabezados y formatos.
"""
from datetime import datetime, timedelta, timezone
from html import escape

import streamlit as st

COL = timezone(timedelta(hours=-5))

AZUL = "#1E3A8A"
COLOR_ESTADO = {"Abierto": "#2563EB", "En Proceso": "#D97706",
                "Resuelto": "#059669", "Cancelado": "#6B7280"}
COLOR_PRIORIDAD = {"Baja": "#10B981", "Media": "#3B82F6", "Alta": "#F59E0B", "Crítica": "#DC2626"}
ICONO_ESTADO = {"Abierto": "🔵", "En Proceso": "🟠", "Resuelto": "🟢", "Cancelado": "⚪"}
ICONO_PRIORIDAD = {"Baja": "▫️", "Media": "🔹", "Alta": "🔸", "Crítica": "🔺"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stMarkdown, button, input, textarea, select {
    font-family: 'Inter', sans-serif !important;
}
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1350px; }
#MainMenu, footer { visibility: hidden; }

/* ---------- Barra lateral ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0F1E4A 0%, #1E3A8A 100%);
}
[data-testid="stSidebar"] * { color: #E2E8F0 !important; }
[data-testid="stSidebar"] [role="radiogroup"] label {
    padding: .55rem .8rem; border-radius: 10px; margin-bottom: 2px;
    transition: background .15s;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(255,255,255,.08); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: rgba(255,255,255,.16);
}
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] p { font-size: .97rem; font-weight: 500; }

.marca { display:flex; align-items:center; gap:.7rem; padding:.3rem 0 1.2rem 0;
         border-bottom: 1px solid rgba(255,255,255,.12); margin-bottom: 1rem; }
.marca-logo { width:44px; height:44px; border-radius:12px; background:#fff;
              display:flex; align-items:center; justify-content:center;
              font-weight:800; color:#1E3A8A !important; font-size:1.1rem; }
.marca-logo span { color:#1E3A8A !important; }
.marca-nombre { font-size:1.35rem; font-weight:800; line-height:1.1; }
.marca-sub { font-size:.75rem; opacity:.75; }
.estado-api { font-size:.8rem; padding:.55rem .7rem; border-radius:10px;
              background: rgba(255,255,255,.08); margin-top: .5rem; }

/* ---------- Encabezado de página ---------- */
.encabezado { background: linear-gradient(120deg, #1E3A8A 0%, #2563EB 60%, #3B82F6 100%);
              border-radius: 18px; padding: 1.4rem 1.8rem; color: white; margin-bottom: 1.4rem;
              box-shadow: 0 10px 30px -12px rgba(30,58,138,.55); }
.encabezado h1 { color: white; font-size: 1.75rem; font-weight: 800; margin: 0; padding: 0; }
.encabezado p { color: #DBEAFE; margin: .25rem 0 0 0; font-size: .97rem; }

/* ---------- Tarjetas de indicadores ---------- */
.kpi { background: white; border-radius: 16px; padding: 1.05rem 1.2rem;
       border: 1px solid #E5EAF3; box-shadow: 0 2px 10px -4px rgba(15,23,42,.08);
       height: 100%; position: relative; overflow: hidden; }
.kpi::before { content:""; position:absolute; left:0; top:0; bottom:0; width:5px; background: var(--c); }
.kpi-top { display:flex; justify-content:space-between; align-items:center; }
.kpi-titulo { color:#64748B; font-size:.78rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em; }
.kpi-icono { font-size:1.3rem; }
.kpi-valor { font-size:1.75rem; font-weight:800; color:#0F172A; margin-top:.35rem; line-height:1.15; }
.kpi-sub { color:#94A3B8; font-size:.8rem; margin-top:.2rem; }

/* ---------- Tarjeta genérica ---------- */
.tarjeta { background:white; border:1px solid #E5EAF3; border-radius:16px; padding:1.1rem 1.3rem;
           box-shadow: 0 2px 10px -4px rgba(15,23,42,.08); margin-bottom: .8rem; }
.tarjeta h4 { margin:0 0 .5rem 0; font-size:1rem; color:#0F172A; }
.dato-etq { color:#64748B; font-size:.72rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em; margin-top:.5rem; }
.dato-val { color:#0F172A; font-size:.95rem; font-weight:500; }

/* ---------- Etiquetas (badges) ---------- */
.badge { display:inline-block; padding:.22rem .7rem; border-radius:999px; font-size:.78rem;
         font-weight:600; color:white; margin-right:.3rem; white-space:nowrap; }
.chip { display:inline-block; padding:.18rem .6rem; border-radius:8px; font-size:.75rem;
        font-weight:600; background:#EEF2FF; color:#3730A3; margin:.1rem .25rem .1rem 0; }

/* ---------- Ticket: cabecera de detalle ---------- */
.ticket-cab { background:white; border:1px solid #E5EAF3; border-left:6px solid var(--c);
              border-radius:16px; padding:1rem 1.3rem; margin:.6rem 0 1rem 0; }
.ticket-cod { font-size:1.35rem; font-weight:800; color:#0F172A; }
.ticket-sub { color:#64748B; font-size:.9rem; margin-top:.15rem; }

/* ---------- Línea de tiempo (bitácora) ---------- */
.timeline { border-left: 3px solid #E2E8F0; margin-left:.6rem; padding-left:1.2rem; }
.tl-item { position:relative; margin-bottom:1.05rem; }
.tl-item::before { content:""; position:absolute; left:-1.72rem; top:.25rem; width:13px; height:13px;
                   border-radius:50%; background: var(--c); border:3px solid white;
                   box-shadow: 0 0 0 2px var(--c); }
.tl-fecha { color:#94A3B8; font-size:.78rem; }
.tl-nota { color:#0F172A; font-size:.93rem; margin-top:.1rem; }
.tl-autor { color:#64748B; font-size:.8rem; font-weight:600; }

/* ---------- Técnico ---------- */
.tec-nombre { font-weight:700; font-size:1.05rem; color:#0F172A; }
.barra { background:#EEF2F7; height:9px; border-radius:99px; overflow:hidden; margin:.35rem 0 .2rem 0; }
.barra > div { height:100%; border-radius:99px; }

/* ---------- Pregunta de negocio (analítica) ---------- */
.pregunta { background:#EFF6FF; border-left:4px solid #2563EB; padding:.55rem .9rem;
            border-radius:8px; color:#1E3A8A; font-size:.88rem; margin-bottom:.6rem; }

/* ---------- Componentes nativos ---------- */
.stTabs [data-baseweb="tab-list"] { gap: .4rem; }
.stTabs [data-baseweb="tab"] { background:#F1F5F9; border-radius:10px 10px 0 0; padding:.5rem 1rem; }
.stTabs [aria-selected="true"] { background:white; }
div[data-testid="stForm"] { background:white; border:1px solid #E5EAF3; border-radius:16px; padding:1.2rem 1.4rem; }
.stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {
    border-radius:10px; font-weight:600; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
[data-testid="stExpander"] { background:white; border-radius:12px; }
</style>
"""


def aplicar_estilos():
    st.markdown(CSS, unsafe_allow_html=True)


def e(texto) -> str:
    """Escapa texto del usuario antes de meterlo en HTML."""
    return escape(str(texto)) if texto is not None else "—"


def encabezado(titulo: str, subtitulo: str):
    st.markdown(f'<div class="encabezado"><h1>{titulo}</h1><p>{subtitulo}</p></div>',
                unsafe_allow_html=True)


def kpi(titulo: str, valor, icono: str = "", sub: str = "", color: str = AZUL):
    st.markdown(f"""
    <div class="kpi" style="--c:{color}">
        <div class="kpi-top"><span class="kpi-titulo">{titulo}</span><span class="kpi-icono">{icono}</span></div>
        <div class="kpi-valor">{valor}</div>
        <div class="kpi-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)


def badge(texto: str, color: str) -> str:
    return f'<span class="badge" style="background:{color}">{e(texto)}</span>'


def badge_estado(estado: str) -> str:
    return badge(estado, COLOR_ESTADO.get(estado, "#64748B"))


def badge_prioridad(prioridad: str) -> str:
    return badge(prioridad, COLOR_PRIORIDAD.get(prioridad, "#64748B"))


def chips(lista) -> str:
    return "".join(f'<span class="chip">{e(x)}</span>' for x in (lista or []))


def icono_cliente(tipo: str) -> str:
    return "🏢" if tipo == "Empresa" else "👤"


def nombre_tipo(tipo: str) -> str:
    return "Empresa" if tipo == "Empresa" else "Persona natural"


def etiqueta_documento(tipo: str) -> str:
    return "NIT" if tipo == "Empresa" else "Cédula"


def estrellas(puntaje) -> str:
    n = int(puntaje or 0)
    return f'<span style="color:#F59E0B">{"★" * n}</span><span style="color:#CBD5E1">{"★" * (5 - n)}</span>'


def pregunta(texto: str):
    st.markdown(f'<div class="pregunta">❓ <b>Pregunta que responde:</b> {texto}</div>',
                unsafe_allow_html=True)


def dinero(valor) -> str:
    return "$ " + f"{float(valor or 0):,.0f}".replace(",", ".")


def a_fecha(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor)).astimezone(COL)
    except ValueError:
        return None


def fecha(valor, con_hora=True) -> str:
    f = a_fecha(valor)
    if not f:
        return "—"
    return f.strftime("%d/%m/%Y %I:%M %p" if con_hora else "%d/%m/%Y")
