"""
app.py  —  INTERFAZ GRÁFICA de ServiFix (Streamlit)
===================================================
La interfaz solo muestra pantallas y envía peticiones HTTP al backend (main.py).
Nunca toca la base de datos directamente.

Para correr en local:   streamlit run app.py
"""
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st
from pydantic import ValidationError

# set_page_config debe ser el PRIMER comando de Streamlit del script
st.set_page_config(page_title="ServiFix · Soporte Técnico", page_icon="🛠️",
                   layout="wide", initial_sidebar_state="expanded")

import interfaz_api as api  # noqa: E402
from interfaz_estilos import (AZUL, COLOR_ESTADO, COLOR_PRIORIDAD, ICONO_ESTADO,  # noqa: E402
                              ICONO_PRIORIDAD, a_fecha, aplicar_estilos, badge,
                              badge_estado, badge_prioridad, chips, dinero, e,
                              encabezado, estrellas, etiqueta_documento, fecha,
                              icono_cliente, kpi, nombre_tipo, pregunta)
from modelos import ClienteCreate, EquipoIn, TicketCreate  # noqa: E402  (mismas validaciones del backend)

aplicar_estilos()

# ---------------------------------------------------------------------------
# CATÁLOGOS (vienen del backend; si falla se usan estos valores)
# ---------------------------------------------------------------------------
_ok, _cat = api.get("/catalogos")
if not _ok:
    _cat = {}
CATEGORIAS = _cat.get("categorias", ["Hardware", "Software", "Redes", "Preventivo"])
PRIORIDADES = _cat.get("prioridades", ["Baja", "Media", "Alta", "Crítica"])
ESTADOS = _cat.get("estados", ["Abierto", "En Proceso", "Resuelto", "Cancelado"])
TIPOS_EQUIPO = _cat.get("tipos_equipo", ["Computador", "Servidor", "Impresora", "Red",
                                         "Proyector", "Equipo médico", "Industrial", "Otro"])
MAX_ACTIVOS = _cat.get("max_tickets_activos", 3)
CATEGORIAS_REPUESTO = _cat.get("categorias_repuesto", ["Componentes", "Redes", "Consumibles",
                                                       "Equipo médico", "Otros"])


# ---------------------------------------------------------------------------
# UTILIDADES DE LA INTERFAZ
# ---------------------------------------------------------------------------
def avisar(mensaje: str, tipo: str = "success"):
    """Guarda un mensaje para mostrarlo después de recargar la página."""
    st.session_state["_aviso"] = (tipo, mensaje)


def mostrar_aviso():
    if "_aviso" in st.session_state:
        tipo, msg = st.session_state.pop("_aviso")
        (st.success if tipo == "success" else st.error)(msg, icon="✅" if tipo == "success" else "⛔")


def contador_form(nombre: str) -> int:
    """Número que cambia para 'limpiar' un formulario después de guardar."""
    return st.session_state.get(f"_n_{nombre}", 0)


def resultado(ok, datos, exito: str = None, limpiar: str = None, ir_a: str = None, abrir_ticket=None):
    """Procesa la respuesta de la API: mensaje de éxito + recarga, o error en pantalla."""
    if ok:
        avisar(exito or (datos.get("mensaje") if isinstance(datos, dict) else "Operación exitosa"))
        if limpiar:
            st.session_state[f"_n_{limpiar}"] = contador_form(limpiar) + 1
        if ir_a:
            st.session_state["_ir_a"] = ir_a
        if abrir_ticket:
            st.session_state["_abrir_ticket"] = abrir_ticket
        st.rerun()
    else:
        st.error(datos, icon="⛔")


def sin_datos(texto: str):
    st.info(texto, icon="ℹ️")


def tabla_vacia(df: pd.DataFrame) -> bool:
    return df is None or df.empty


def color_scale(dominio: dict):
    return alt.Scale(domain=list(dominio.keys()), range=list(dominio.values()))


def grafico_barras(df, x, y, titulo_x="", titulo_y="", color=AZUL, horizontal=False,
                   formato=None, alto=300):
    """Gráfico de barras (vertical u horizontal) con el estilo de la app."""
    tooltip = [alt.Tooltip(f"{x}:N", title=titulo_x or x),
               alt.Tooltip(f"{y}:Q", title=titulo_y or y, format=formato or ",.0f")]
    if horizontal:
        barras = alt.Chart(df).mark_bar(color=color, cornerRadiusTopRight=6, cornerRadiusBottomRight=6).encode(
            y=alt.Y(f"{x}:N", sort="-x", title=titulo_x),
            x=alt.X(f"{y}:Q", title=titulo_y),
            tooltip=tooltip)
    else:
        barras = alt.Chart(df).mark_bar(color=color, cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
            x=alt.X(f"{x}:N", sort="-y", title=titulo_x, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{y}:Q", title=titulo_y),
            tooltip=tooltip)
    return barras.properties(height=alto)


# ---------------------------------------------------------------------------
# BARRA LATERAL (navegación)
# ---------------------------------------------------------------------------
PAGINAS = ["🏠  Panel de control", "🎫  Tickets", "➕  Nuevo ticket",
           "👷  Técnicos", "👥  Clientes", "📦  Inventario", "📊  Analítica", "🙋  Portal del cliente"]

if "_ir_a" in st.session_state:
    st.session_state["nav"] = st.session_state.pop("_ir_a")

with st.sidebar:
    st.markdown("""
    <div class="marca">
        <div class="marca-logo"><span>SF</span></div>
        <div><div class="marca-nombre">ServiFix</div>
        <div class="marca-sub">Gestión de soporte técnico</div></div>
    </div>""", unsafe_allow_html=True)
    pagina = st.radio("Navegación", PAGINAS, key="nav", label_visibility="collapsed")

    st.markdown("<br>", unsafe_allow_html=True)
    ok_salud, salud = api.get("/health")
    if ok_salud:
        st.markdown(f"""<div class="estado-api">🟢 <b>API conectada</b><br>
            🍃 MongoDB Atlas: {e(salud.get('mongodb_atlas'))}<br>
            ☁️ Cloudinary: {e(salud.get('cloudinary'))}<br>
            🤖 Google Gemini: {e(salud.get('gemini', '—'))}</div>""", unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="estado-api">🔴 <b>Sin conexión con la API</b><br>{e(salud)}</div>',
                    unsafe_allow_html=True)
    st.markdown("""<div class="estado-api" style="margin-top:.7rem">
        <b>Arquitectura</b><br>Streamlit → FastAPI → MongoDB Atlas<br>
        + Cloudinary · Google Gemini</div>""", unsafe_allow_html=True)


# ===========================================================================
# 1. PANEL DE CONTROL
# ===========================================================================
def pagina_panel():
    encabezado("🛠️ Panel de control", "Resumen en tiempo real de la operación de soporte técnico")
    ok, r = api.get("/analytics/resumen")
    if not ok:
        st.error(r, icon="⛔")
        return

    est = r["por_estado"]
    c = st.columns(4)
    with c[0]:
        kpi("Total de tickets", r["total_tickets"], "🎫", "registrados en el sistema", AZUL)
    with c[1]:
        kpi("Sin asignar", est.get("Abierto", 0), "🔵", "esperando técnico", COLOR_ESTADO["Abierto"])
    with c[2]:
        kpi("En proceso", est.get("En Proceso", 0), "🟠", "en manos de un técnico", COLOR_ESTADO["En Proceso"])
    with c[3]:
        kpi("Resueltos", est.get("Resuelto", 0), "🟢",
            f"{est.get('Cancelado', 0)} cancelados", COLOR_ESTADO["Resuelto"])

    st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)
    c = st.columns(4)
    with c[0]:
        kpi("Ingresos", dinero(r["ingresos"]), "💰", "por servicios resueltos", "#059669")
    with c[1]:
        kpi("Costo promedio", dinero(r["costo_promedio"]), "🧾", "por servicio", "#7C3AED")
    with c[2]:
        kpi("Tiempo de resolución", f"{r['horas_promedio_resolucion']} h", "⏱️",
            "promedio desde la solicitud", "#0891B2")
    with c[3]:
        kpi("Satisfacción", f"{r.get('satisfaccion_promedio', 0)} / 5", "⭐",
            f"{r.get('encuestas', 0)} encuestas del portal", "#F59E0B")
    if r.get("repuestos_stock_bajo"):
        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
        st.warning(f"📦 Hay **{r['repuestos_stock_bajo']} repuesto(s) con stock bajo**. Revise la sección Inventario.")

    st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("##### 🍩 Tickets por estado")
            df = pd.DataFrame({"estado": list(est.keys()), "total": list(est.values())})
            if df["total"].sum() == 0:
                sin_datos("Aún no hay tickets.")
            else:
                dona = alt.Chart(df[df.total > 0]).mark_arc(innerRadius=70, cornerRadius=5).encode(
                    theta="total:Q",
                    color=alt.Color("estado:N", scale=color_scale(COLOR_ESTADO),
                                    legend=alt.Legend(orient="bottom", title=None)),
                    tooltip=[alt.Tooltip("estado:N", title="Estado"), alt.Tooltip("total:Q", title="Tickets")],
                ).properties(height=290)
                st.altair_chart(dona, use_container_width=True)
    with col2:
        with st.container(border=True):
            st.markdown("##### 🚦 Tickets activos por prioridad")
            pr = r["activos_por_prioridad"]
            df = pd.DataFrame({"prioridad": list(pr.keys()), "total": list(pr.values())})
            if df["total"].sum() == 0:
                sin_datos("No hay tickets activos.")
            else:
                barras = alt.Chart(df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
                    x=alt.X("prioridad:N", sort=PRIORIDADES, title=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("total:Q", title="Tickets", axis=alt.Axis(tickMinStep=1)),
                    color=alt.Color("prioridad:N", scale=color_scale(COLOR_PRIORIDAD), legend=None),
                    tooltip=[alt.Tooltip("prioridad:N", title="Prioridad"),
                             alt.Tooltip("total:Q", title="Tickets")],
                ).properties(height=290)
                st.altair_chart(barras, use_container_width=True)

    col1, col2 = st.columns([1, 1.4])
    with col1:
        with st.container(border=True):
            st.markdown("##### ⏰ Solicitudes esperando más de 48 h")
            ok, pend = api.get("/analytics/pendientes", horas=48)
            if ok and pend:
                for p in pend:
                    st.markdown(f"""<div class="tarjeta" style="padding:.7rem 1rem;margin-bottom:.5rem">
                        <b>{e(p['codigo'])}</b> {badge_prioridad(p['prioridad'])}<br>
                        <span style="color:#64748B;font-size:.88rem">{e(p['cliente'])} · {e(p['equipo'])}</span><br>
                        <span style="color:#DC2626;font-weight:600;font-size:.85rem">
                        {int(p['horas_esperando'])} horas sin asignar</span></div>""", unsafe_allow_html=True)
            elif ok:
                st.success("Todo al día: no hay solicitudes atrasadas.", icon="👌")
            else:
                st.error(pend)
    with col2:
        with st.container(border=True):
            st.markdown("##### 🆕 Últimos tickets")
            ok, ts = api.get("/tickets")
            if ok and ts:
                filas = [{
                    "Código": t["codigo"],
                    "Estado": f"{ICONO_ESTADO.get(t['estado'], '')} {t['estado']}",
                    "Cliente": (t.get("cliente") or {}).get("nombre", "—"),
                    "Equipo": t["equipo"]["nombre"],
                    "Técnico": (t.get("tecnico") or {}).get("nombre") or "Sin asignar",
                    "Creado": fecha(t["created_at"]),
                } for t in ts[:7]]
                st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
            elif ok:
                sin_datos("Aún no hay tickets.")


# ===========================================================================
# 2. TICKETS: búsqueda, filtros, detalle y gestión
# ===========================================================================
def pagina_tickets():
    encabezado("🎫 Tickets de soporte", "Busque, filtre y gestione las órdenes de servicio")

    ok_t, tecnicos = api.get("/tecnicos")
    ok_c, clientes = api.get("/clientes")
    tecnicos = tecnicos if ok_t else []
    clientes = clientes if ok_c else []

    # ---------------- Filtros ----------------
    with st.container(border=True):
        c = st.columns([2.2, 1, 1, 1])
        buscar = c[0].text_input("🔎 Buscar", placeholder="Código, cliente, equipo, serial o descripción…")
        f_estado = c[1].selectbox("Estado", ["Todos"] + ESTADOS)
        f_cat = c[2].selectbox("Categoría", ["Todas"] + CATEGORIAS)
        f_pri = c[3].selectbox("Prioridad", ["Todas"] + PRIORIDADES)
        c = st.columns([1.5, 1.5, 1.2])
        mapa_tec = {"Todos": None, **{t["nombre"]: t["id"] for t in tecnicos}}
        mapa_cli = {"Todos": None, **{x["nombre"]: x["id"] for x in clientes}}
        f_tec = c[0].selectbox("Técnico", list(mapa_tec))
        f_cli = c[1].selectbox("Cliente", list(mapa_cli))
        hoy = date.today()
        rango = c[2].date_input("Fecha de creación", value=(hoy - timedelta(days=180), hoy),
                                format="DD/MM/YYYY")

    params = {
        "buscar": buscar.strip() or None,
        "estado": None if f_estado == "Todos" else f_estado,
        "categoria": None if f_cat == "Todas" else f_cat,
        "prioridad": None if f_pri == "Todas" else f_pri,
        "tecnico_id": mapa_tec[f_tec],
        "cliente_id": mapa_cli[f_cli],
    }
    if isinstance(rango, (list, tuple)) and len(rango) == 2:
        params["desde"], params["hasta"] = rango[0].isoformat(), rango[1].isoformat()

    ok, tickets = api.get("/tickets", **params)
    if not ok:
        st.error(tickets, icon="⛔")
        return

    # ---------------- Resultados ----------------
    cab1, cab2 = st.columns([3, 1])
    cab1.markdown(f"**{len(tickets)}** ticket(s) encontrados")
    filas = [{
        "Código": t["codigo"],
        "Estado": f"{ICONO_ESTADO.get(t['estado'], '')} {t['estado']}",
        "Prioridad": f"{ICONO_PRIORIDAD.get(t['prioridad'], '')} {t['prioridad']}",
        "Cliente": f"{icono_cliente((t.get('cliente') or {}).get('tipo'))} {(t.get('cliente') or {}).get('nombre', '—')}",
        "Ciudad": (t.get("cliente") or {}).get("ciudad", "—"),
        "Equipo": t["equipo"]["nombre"],
        "Categoría": t["categoria"],
        "Técnico": (t.get("tecnico") or {}).get("nombre") or "Sin asignar",
        "Costo": t.get("costo", 0),
        "Creado": a_fecha(t["created_at"]).strftime("%d/%m/%Y") if a_fecha(t["created_at"]) else "",
    } for t in tickets]
    df = pd.DataFrame(filas)
    if tabla_vacia(df):
        sin_datos("No hay tickets con esos filtros.")
        return
    with cab2:  # Reporte PDF generado por el backend con los mismos filtros
        clave_pdf = str(sorted((k, v) for k, v in params.items() if v))
        if st.button("📄 Generar reporte PDF", use_container_width=True):
            with st.spinner("Generando reporte…"):
                ok_pdf, pdf = api.get_directo("/reportes/tickets.pdf", **params)
            if ok_pdf:
                st.session_state["_reporte_pdf"] = (clave_pdf, pdf)
            else:
                st.error(pdf)
        guardado = st.session_state.get("_reporte_pdf")
        if guardado and guardado[0] == clave_pdf:
            st.download_button("⬇️ Descargar PDF", guardado[1], "reporte_tickets.pdf", "application/pdf",
                               type="primary", use_container_width=True)
    st.dataframe(df, hide_index=True, use_container_width=True, height=min(420, 38 + 35 * len(df)),
                 column_config={"Costo": st.column_config.NumberColumn("Costo (COP)", format="$ %d")})

    # ---------------- Selección del ticket ----------------
    ids = [t["id"] for t in tickets]
    por_id = {t["id"]: t for t in tickets}
    if "_abrir_ticket" in st.session_state:
        pendiente = st.session_state.pop("_abrir_ticket")
        if pendiente in ids:
            st.session_state["ticket_sel"] = pendiente
    if st.session_state.get("ticket_sel") not in ids:
        st.session_state.pop("ticket_sel", None)

    st.markdown("#### 🔍 Detalle y gestión")
    sel = st.selectbox(
        "Seleccione un ticket", ids, index=None, key="ticket_sel",
        placeholder="Elija un ticket de la lista…",
        format_func=lambda i: f"{por_id[i]['codigo']} · {(por_id[i].get('cliente') or {}).get('nombre', '')} "
                              f"· {por_id[i]['equipo']['nombre']} ({por_id[i]['estado']})",
    )
    if sel:
        detalle_ticket(por_id[sel], tecnicos)


def detalle_ticket(t: dict, tecnicos: list):
    cliente = t.get("cliente") or {}
    tecnico = t.get("tecnico") or {}
    equipo = t["equipo"]
    estado = t["estado"]
    cerrado = estado in ("Resuelto", "Cancelado")

    st.markdown(f"""
    <div class="ticket-cab" style="--c:{COLOR_ESTADO.get(estado, AZUL)}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:.5rem">
        <div>
          <div class="ticket-cod">{e(t['codigo'])} &nbsp;{badge_estado(estado)}{badge_prioridad(t['prioridad'])}
               {badge(t['categoria'], '#475569')}</div>
          <div class="ticket-sub">{icono_cliente(cliente.get('tipo'))} {e(cliente.get('nombre'))} &nbsp;·&nbsp; 🖥️ {e(equipo['nombre'])}
               &nbsp;·&nbsp; 📅 {fecha(t['created_at'])}</div>
        </div>
        <div style="text-align:right">
          <div class="dato-etq">Costo del servicio</div>
          <div style="font-size:1.5rem;font-weight:800;color:#0F172A">{dinero(t.get('costo'))}</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    tabs = st.tabs(["📋 Detalle", "🕓 Bitácora", "⚙️ Gestionar", "✏️ Editar", "📄 PDF y eliminar"])

    # ---- Detalle ----
    with tabs[0]:
        c = st.columns(3)
        with c[0]:
            st.markdown(tarjeta_cliente(cliente, con_equipos=False), unsafe_allow_html=True)
        with c[1]:
            st.markdown(f"""<div class="tarjeta"><h4>🖥️ Equipo</h4>
                <div class="dato-etq">Nombre</div><div class="dato-val">{e(equipo['nombre'])}</div>
                <div class="dato-etq">Tipo · Marca</div><div class="dato-val">{e(equipo['tipo'])} · {e(equipo['marca'])}</div>
                <div class="dato-etq">Serial</div><div class="dato-val">{e(equipo['serial'])}</div>
                </div>""", unsafe_allow_html=True)
        with c[2]:
            if tecnico.get("nombre"):
                cuerpo = f"""<div class="dato-etq">Nombre</div><div class="dato-val">{e(tecnico['nombre'])}</div>
                    <div class="dato-etq">Contacto</div><div class="dato-val">{e(tecnico.get('email'))}<br>{e(tecnico.get('telefono'))}</div>
                    <div class="dato-etq">Especialidades</div><div>{chips(tecnico.get('especialidades'))}</div>"""
            else:
                cuerpo = '<div class="dato-val" style="color:#94A3B8">Aún no se ha asignado un técnico.</div>'
            st.markdown(f'<div class="tarjeta"><h4>👷 Técnico</h4>{cuerpo}</div>', unsafe_allow_html=True)

        st.markdown(f"""<div class="tarjeta"><h4>📝 Descripción de la falla</h4>
            <div class="dato-val">{e(t['descripcion'])}</div>
            <div class="dato-etq">Resuelto el</div><div class="dato-val">{fecha(t.get('resolved_at'))}</div>
            </div>""", unsafe_allow_html=True)
        if t.get("diagnostico_ia"):
            st.markdown(f"""<div class="tarjeta" style="background:#F5F3FF;border-left:5px solid #7C3AED">
                <h4>🤖 Diagnóstico preliminar sugerido por IA (Google Gemini)</h4>
                <div class="dato-val" style="white-space:pre-line">{e(t['diagnostico_ia'])}</div></div>""",
                        unsafe_allow_html=True)
        if estado == "Resuelto":
            c = st.columns([1.6, 1])
            with c[0]:
                with st.container(border=True):
                    st.markdown("##### 📦 Repuestos utilizados")
                    usados = t.get("repuestos_usados") or []
                    if usados:
                        st.dataframe(pd.DataFrame([{
                            "Código": u["sku"], "Repuesto": u["nombre"], "Cantidad": u["cantidad"],
                            "Precio unit.": u["precio_unitario"], "Subtotal": u["subtotal"]} for u in usados]),
                            hide_index=True, use_container_width=True,
                            column_config={"Precio unit.": st.column_config.NumberColumn(format="$ %d"),
                                           "Subtotal": st.column_config.NumberColumn(format="$ %d")})
                    else:
                        st.caption("No se usaron repuestos en este servicio.")
            with c[1]:
                st.markdown(f"""<div class="tarjeta"><h4>💰 Costo del servicio</h4>
                    <div class="dato-etq">Mano de obra</div><div class="dato-val">{dinero(t.get('costo_mano_obra', t.get('costo')))}</div>
                    <div class="dato-etq">Repuestos</div><div class="dato-val">{dinero(t.get('costo_repuestos'))}</div>
                    <div class="dato-etq">Total</div><div style="font-size:1.4rem;font-weight:800">{dinero(t.get('costo'))}</div>
                    </div>""", unsafe_allow_html=True)
            cal = t.get("calificacion") or {}
            if cal.get("puntaje"):
                st.markdown(f"""<div class="tarjeta"><h4>⭐ Calificación del cliente (portal)</h4>
                    <div style="font-size:1.5rem">{estrellas(cal['puntaje'])} <b>{cal['puntaje']}/5</b></div>
                    <div class="dato-val" style="color:#475569"><i>{e(cal.get('comentario') or 'Sin comentario')}</i></div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.caption("⭐ El cliente aún no ha calificado este servicio en el portal.")
        if t.get("foto_url"):
            st.image(t["foto_url"], caption="Evidencia del trabajo (almacenada en Cloudinary)", width=420)

    # ---- Bitácora ----
    with tabs[1]:
        items = "".join(f"""<div class="tl-item" style="--c:{COLOR_ESTADO.get(b.get('estado'), AZUL)}">
                <div class="tl-fecha">{fecha(b['fecha'])} · {e(b.get('estado', ''))}</div>
                <div class="tl-nota">{e(b['nota'])}</div>
                <div class="tl-autor">👤 {e(b['autor'])}</div></div>""" for b in t.get("bitacora", []))
        st.markdown(f'<div class="tarjeta"><h4>Historial del ticket (embebido en el documento)</h4>'
                    f'<div class="timeline">{items}</div></div>', unsafe_allow_html=True)

    # ---- Gestionar ----
    with tabs[2]:
        if cerrado:
            st.info(f"Este ticket está **{estado}**. Es un estado final y ya no admite cambios.", icon="🔒")
        else:
            gestionar_ticket(t, tecnicos)

    # ---- Editar ----
    with tabs[3]:
        if cerrado:
            st.info("Los tickets cerrados no se pueden editar.", icon="🔒")
        else:
            with st.form(f"editar_{t['id']}"):
                c = st.columns(2)
                pri = c[0].selectbox("Prioridad", PRIORIDADES, index=PRIORIDADES.index(t["prioridad"]))
                cat = c[1].selectbox("Categoría", CATEGORIAS, index=CATEGORIAS.index(t["categoria"]),
                                     disabled=estado != "Abierto",
                                     help="Solo se puede cambiar antes de asignar un técnico.")
                desc = st.text_area("Descripción", t["descripcion"], height=110)
                if st.form_submit_button("💾 Guardar cambios", type="primary"):
                    cambios = {"prioridad": pri, "descripcion": desc}
                    if estado == "Abierto":
                        cambios["categoria"] = cat
                    resultado(*api.put(f"/tickets/{t['id']}", json=cambios), abrir_ticket=t["id"])

    # ---- PDF y eliminar ----
    with tabs[4]:
        c = st.columns(2)
        with c[0]:
            with st.container(border=True):
                st.markdown("##### 📄 Orden de servicio en PDF")
                st.caption("Incluye datos del cliente, equipo, técnico, bitácora completa, evidencia y costo.")
                clave = f"pdf_{t['id']}"
                if st.button("Generar PDF", key=f"gen_{t['id']}", use_container_width=True):
                    with st.spinner("Generando PDF…"):
                        ok, datos = api.get_directo(f"/tickets/{t['id']}/pdf")
                    if ok:
                        st.session_state[clave] = datos
                    else:
                        st.error(datos)
                if clave in st.session_state:
                    st.download_button("⬇️ Descargar PDF", st.session_state[clave],
                                       f"orden_{t['codigo']}.pdf", "application/pdf",
                                       type="primary", use_container_width=True, key=f"dl_{t['id']}")
        with c[1]:
            with st.container(border=True):
                st.markdown("##### 🗑️ Eliminar ticket")
                st.caption("Regla: solo se eliminan tickets **Abiertos** o **Cancelados**. "
                           "Los resueltos se conservan como historial.")
                conf = st.checkbox(f"Confirmo que deseo eliminar {t['codigo']}", key=f"conf_{t['id']}")
                if st.button("Eliminar definitivamente", key=f"del_{t['id']}", disabled=not conf,
                             use_container_width=True):
                    resultado(*api.delete(f"/tickets/{t['id']}"))


def gestionar_ticket(t: dict, tecnicos: list):
    estado = t["estado"]
    actual = (t.get("tecnico") or {}).get("nombre")

    c = st.columns(2)
    # ---- Asignar / reasignar técnico ----
    with c[0]:
        with st.container(border=True):
            st.markdown("##### 👷 " + ("Reasignar técnico" if actual else "Asignar técnico"))
            st.caption(f"Reglas: técnico activo, con especialidad **{t['categoria']}** "
                       f"y máximo **{MAX_ACTIVOS}** tickets en proceso.")
            activos = [x for x in tecnicos if x.get("activo")]
            if not activos:
                sin_datos("No hay técnicos activos.")
            else:
                def etiqueta(x):
                    if t["categoria"] not in x["especialidades"]:
                        marca = "⚠️ sin especialidad"
                    elif x["carga_actual"] >= MAX_ACTIVOS:
                        marca = "⛔ sin cupo"
                    else:
                        marca = "✅ disponible"
                    return f"{x['nombre']} — {x['carga_actual']}/{MAX_ACTIVOS} en proceso · {marca}"
                opciones = {x["id"]: x for x in activos}
                tec_id = st.selectbox("Técnico", list(opciones), format_func=lambda i: etiqueta(opciones[i]),
                                      key=f"asig_sel_{t['id']}")
                if st.button("Asignar", key=f"asig_{t['id']}", type="primary", use_container_width=True):
                    resultado(*api.put(f"/tickets/{t['id']}/asignar", json={"tecnico_id": tec_id}),
                              abrir_ticket=t["id"])

    # ---- Nota de avance ----
    with c[1]:
        with st.container(border=True):
            st.markdown("##### 🗒️ Agregar nota a la bitácora")
            with st.form(f"nota_{t['id']}_{contador_form('nota')}"):
                autor = st.text_input("Autor", value=actual or "Coordinador")
                nota = st.text_area("Nota de avance", height=80,
                                    placeholder="Ej: Se solicitó repuesto al proveedor…")
                if st.form_submit_button("Agregar nota", use_container_width=True):
                    resultado(*api.post(f"/tickets/{t['id']}/notas", json={"nota": nota, "autor": autor}),
                              limpiar="nota", abrir_ticket=t["id"])

    # ---- Cerrar ticket ----
    with st.container(border=True):
        st.markdown("##### ✅ Cerrar ticket")
        if estado == "Abierto":
            st.caption("Un ticket **Abierto** solo puede cancelarse. Para resolverlo, primero asigne un técnico.")
            opciones_estado = ["Cancelado"]
        else:
            st.caption("Reglas: para **Resuelto** se registra el costo de mano de obra (> 0). Los repuestos se "
                       "descuentan del inventario con una **transacción**: si falta stock de uno, no se guarda nada.")
            opciones_estado = ["Resuelto", "Cancelado"]
        nuevo = st.radio("Nuevo estado", opciones_estado, horizontal=True, key=f"nuevo_estado_{t['id']}")

        elegidos = []
        if nuevo == "Resuelto":
            ok_r, reps = api.get("/repuestos")
            disponibles = {r["id"]: r for r in (reps if ok_r else []) if r["stock"] > 0}
            elegidos = st.multiselect(
                "📦 Repuestos utilizados (opcional)", list(disponibles), key=f"reps_{t['id']}",
                format_func=lambda i: f"{disponibles[i]['nombre']} · {dinero(disponibles[i]['precio_unitario'])} "
                                      f"· stock {disponibles[i]['stock']}",
                placeholder="Elija los repuestos que se cambiaron…")

        with st.form(f"cerrar_{t['id']}"):
            cantidades = {}
            if elegidos:
                st.markdown("**Cantidad de cada repuesto**")
                cols = st.columns(min(3, len(elegidos)))
                for i, rid in enumerate(elegidos):
                    r = disponibles[rid]
                    cantidades[rid] = cols[i % len(cols)].number_input(
                        r["nombre"], min_value=1, max_value=max(1, r["stock"]), value=1, step=1,
                        key=f"cant_{t['id']}_{rid}")
            costo = 0.0
            if nuevo == "Resuelto":
                costo = st.number_input("Costo de mano de obra (COP)", min_value=0.0, step=10000.0, format="%.0f")
            nota = st.text_area("Nota de cierre / motivo", height=80,
                                placeholder="Describa el trabajo realizado o el motivo de cancelación…")
            foto = None
            if nuevo == "Resuelto":
                foto = st.file_uploader("📷 Foto de evidencia (opcional · se guarda en Cloudinary)",
                                        type=["jpg", "jpeg", "png", "webp"])
            if st.form_submit_button("Guardar cierre", type="primary"):
                url = None
                if foto:
                    with st.spinner("Subiendo foto a Cloudinary…"):
                        ok, datos = api.post("/upload", files={"file": (foto.name, foto.getvalue(), foto.type)})
                    if not ok:
                        st.error(f"No se pudo subir la foto: {datos}", icon="⛔")
                        st.stop()
                    url = datos["url"]
                resultado(*api.put(f"/tickets/{t['id']}/estado", json={
                    "estado": nuevo, "nota": nota, "costo": costo, "foto_url": url,
                    "repuestos": [{"repuesto_id": rid, "cantidad": int(n)} for rid, n in cantidades.items()]}),
                    abrir_ticket=t["id"])


# ===========================================================================
# FORMULARIOS REUTILIZABLES: cliente (persona o empresa) y equipo
# ===========================================================================
def campos_cliente(tipo: str, v: dict = None, nuevo: bool = True) -> dict:
    """Campos del cliente según sea persona natural o empresa (se usa dentro de un st.form)."""
    v = v or {}
    con = v.get("contacto") or {}
    es_emp = tipo == "Empresa"
    c = st.columns(2)
    nombre = c[0].text_input("Nombre de la empresa" if es_emp else "Nombre completo", v.get("nombre", ""),
                             placeholder="Ej: Ferretería El Tornillo S.A.S." if es_emp else "Ej: María Fernanda López")
    if nuevo:
        documento = c[1].text_input("NIT" if es_emp else "Cédula",
                                    placeholder="900123456-7" if es_emp else "1036598741")
    else:
        c[1].text_input(f"{etiqueta_documento(tipo)} (no se puede cambiar)", v.get("documento", ""), disabled=True)
        documento = None
    c = st.columns(2)
    ciudad = c[0].text_input("Ciudad", v.get("ciudad", ""))
    direccion = c[1].text_input("Dirección", v.get("direccion", ""))
    if es_emp:
        st.markdown("**Persona que reporta / contacto en la empresa**")
        c = st.columns(3)
        cn = c[0].text_input("Nombre del contacto", con.get("nombre", ""))
        ce = c[1].text_input("Email", con.get("email", ""))
        ct = c[2].text_input("Teléfono", con.get("telefono", ""))
    else:
        c = st.columns(2)
        cn = None  # en una persona natural el contacto es ella misma
        ce = c[0].text_input("Email", con.get("email", ""))
        ct = c[1].text_input("Teléfono / celular", con.get("telefono", ""))
    datos = {"nombre": nombre, "ciudad": ciudad, "direccion": direccion,
             "contacto": {"nombre": (cn or None), "email": ce, "telefono": ct}}
    if nuevo:
        datos.update({"tipo": tipo, "documento": documento})
    return datos


def campos_equipo() -> dict:
    c = st.columns(2)
    nombre = c[0].text_input("Nombre del equipo", placeholder="Ej: Portátil personal, Servidor de facturación…")
    tipo = c[1].selectbox("Tipo de equipo", TIPOS_EQUIPO)
    c = st.columns(2)
    marca = c[0].text_input("Marca", placeholder="Ej: Lenovo")
    serial = c[1].text_input("Serial", help="Número de serie que aparece en la etiqueta del equipo")
    return {"nombre": nombre, "tipo": tipo, "marca": marca, "serial": serial}


def validar(modelo, datos: dict):
    """Valida con los MISMOS modelos del backend antes de enviar (devuelve el error o None)."""
    try:
        modelo(**datos)
        return None
    except ValidationError as ex:
        return " ".join(api.mensaje_validacion(err) for err in ex.errors())


def tarjeta_cliente(cliente: dict, con_equipos: bool = True) -> str:
    contacto = cliente.get("contacto") or {}
    tipo = cliente.get("tipo")
    filas = f"""
        <div class="dato-etq">Tipo de cliente</div><div class="dato-val">{icono_cliente(tipo)} {nombre_tipo(tipo)}</div>
        <div class="dato-etq">{etiqueta_documento(tipo)}</div><div class="dato-val">{e(cliente.get('documento'))}</div>
        <div class="dato-etq">Ubicación</div><div class="dato-val">{e(cliente.get('ciudad'))} · {e(cliente.get('direccion'))}</div>"""
    if tipo == "Empresa":
        filas += f"""<div class="dato-etq">Persona de contacto</div><div class="dato-val">{e(contacto.get('nombre'))}</div>"""
    filas += f"""<div class="dato-etq">Email · Teléfono</div>
        <div class="dato-val">{e(contacto.get('email'))}<br>{e(contacto.get('telefono'))}</div>"""
    if con_equipos:
        equipos = cliente.get("equipos", [])
        lista = "".join(f"<li>{e(x['nombre'])} <span style='color:#94A3B8'>({e(x['tipo'])})</span></li>"
                        for x in equipos) or "<li style='color:#94A3B8'>Ninguno</li>"
        filas += f"""<div class="dato-etq">Equipos registrados ({len(equipos)})</div>
            <ul style="margin:.2rem 0 0 1rem">{lista}</ul>"""
    return f'<div class="tarjeta"><h4>{icono_cliente(tipo)} {e(cliente.get("nombre"))}</h4>{filas}</div>'


# ===========================================================================
# 3. NUEVO TICKET
# ===========================================================================
NUEVO_EQUIPO = "__nuevo__"


def pagina_nuevo_ticket():
    encabezado("➕ Nueva solicitud de soporte",
               "Registre la falla de un equipo. El cliente puede ser una persona o venir de parte de una empresa.")
    ok, clientes = api.get("/clientes")
    if not ok:
        st.error(clientes, icon="⛔")
        return

    col_form, col_info = st.columns([1.6, 1])
    with col_form:
        # ---- Paso 1: ¿quién solicita? (fuera del formulario para que la pantalla cambie al elegir) ----
        with st.container(border=True):
            st.markdown("##### 1️⃣ ¿Quién solicita el servicio?")
            opciones = ["Cliente ya registrado", "Cliente nuevo"] if clientes else ["Cliente nuevo"]
            quien = st.radio("¿El cliente ya está registrado?", opciones, horizontal=True)
            cliente, cli_id, eq_id, tipo = None, None, None, None
            if quien == "Cliente nuevo":
                resp = st.radio("¿Viene de parte de una empresa?",
                                ["No, a nombre propio", "Sí, viene de una empresa"], horizontal=True)
                tipo = "Empresa" if resp.startswith("Sí") else "Persona"
            else:
                mapa = {c["id"]: c for c in clientes}
                cli_id = st.selectbox("Buscar cliente", list(mapa),
                                      format_func=lambda i: f"{icono_cliente(mapa[i].get('tipo'))} {mapa[i]['nombre']}"
                                                            f" · {etiqueta_documento(mapa[i].get('tipo'))} "
                                                            f"{mapa[i].get('documento')} · {mapa[i]['ciudad']}")
                cliente = mapa[cli_id]
                eq = {x["equipo_id"]: x for x in cliente.get("equipos", [])}
                eq_id = st.selectbox(
                    "🖥️ Equipo con falla", list(eq) + [NUEVO_EQUIPO],
                    format_func=lambda i: "➕ Otro equipo (registrarlo ahora)" if i == NUEVO_EQUIPO
                    else f"{eq[i]['nombre']} · {eq[i]['tipo']} · S/N {eq[i]['serial']}")

        # ---- Pasos 2 y 3: datos (formulario) ----
        with st.form(f"nuevo_ticket_{contador_form('ticket')}"):
            paso = 2
            datos_cliente = datos_equipo = None
            if quien == "Cliente nuevo":
                st.markdown(f"##### {paso}️⃣ Datos del cliente · "
                            f"{'🏢 empresa' if tipo == 'Empresa' else '👤 persona natural'}")
                datos_cliente = campos_cliente(tipo)
                paso += 1
            if quien == "Cliente nuevo" or eq_id == NUEVO_EQUIPO:
                st.markdown(f"##### {paso}️⃣ Equipo con falla")
                datos_equipo = campos_equipo()
                paso += 1
            st.markdown(f"##### {paso}️⃣ Detalle de la falla")
            sug = st.session_state.get("_sug_ia")  # sugerencia de la IA (si se pidió)
            descripcion = st.text_area("Descripción de la falla", height=120,
                                       placeholder="Describa el problema con el mayor detalle posible (mínimo 10 caracteres)…")
            c = st.columns(2)
            categoria = c[0].selectbox("Categoría del servicio", CATEGORIAS,
                                       index=CATEGORIAS.index(sug["categoria"]) if sug else 0)
            prioridad = c[1].select_slider("Prioridad", PRIORIDADES, value=sug["prioridad"] if sug else "Media")
            c = st.columns([1, 1.4])
            pedir_ia = c[0].form_submit_button("🤖 Sugerir con IA", use_container_width=True,
                                               help="Google Gemini lee la descripción y sugiere categoría, "
                                                    "prioridad y un posible diagnóstico.")
            enviar = c[1].form_submit_button("🚀 Crear ticket", type="primary", use_container_width=True)

        if pedir_ia:
            if len(descripcion.strip()) < 10:
                st.warning("Escriba primero la descripción de la falla (mínimo 10 caracteres).", icon="✍️")
            else:
                if datos_equipo:
                    eq_info = {"equipo_tipo": datos_equipo["tipo"], "equipo_nombre": datos_equipo["nombre"] or None}
                elif cliente and eq_id in {x["equipo_id"] for x in cliente.get("equipos", [])}:
                    eq_sel = next(x for x in cliente["equipos"] if x["equipo_id"] == eq_id)
                    eq_info = {"equipo_tipo": eq_sel["tipo"], "equipo_nombre": eq_sel["nombre"]}
                else:
                    eq_info = {}
                with st.spinner("🤖 Google Gemini está analizando la falla…"):
                    ok, r = api.consultar("/ia/sugerir", {"descripcion": descripcion, **eq_info})
                if ok:
                    st.session_state["_sug_ia"] = r
                    st.rerun()
                else:
                    st.error(r, icon="🤖")

        if enviar:
            ticket = {"cliente_id": "x", "equipo_id": "x", "categoria": categoria,
                      "prioridad": prioridad, "descripcion": descripcion}
            if sug:  # se guarda el diagnóstico de la IA dentro del ticket
                ticket["diagnostico_ia"] = (sug.get("diagnostico", "") + "\n" + "\n".join(
                    f"{i}. {p}" for i, p in enumerate(sug.get("pasos", []), start=1))).strip()
            # 1) Se valida TODO antes de guardar algo, para no dejar registros a medias
            errores = [m for m in (
                validar(ClienteCreate, datos_cliente) if datos_cliente else None,
                validar(EquipoIn, datos_equipo) if datos_equipo else None,
                validar(TicketCreate, ticket),
            ) if m]
            if errores:
                st.error(" ".join(errores), icon="⛔")
                st.stop()
            # 2) Se guarda en orden: cliente -> equipo -> ticket (cada paso por la API)
            if datos_cliente:
                ok, r = api.post("/clientes", json=datos_cliente)
                if not ok:
                    st.error(r, icon="⛔")
                    st.stop()
                cli_id = r["id"]
            if datos_equipo:
                ok, r = api.post(f"/clientes/{cli_id}/equipos", json=datos_equipo)
                if not ok:
                    st.error(r, icon="⛔")
                    if datos_cliente:
                        st.warning("El cliente sí quedó registrado. Elija **Cliente ya registrado** para continuar.")
                    st.stop()
                eq_id = r["equipo_id"]
            ticket.update({"cliente_id": cli_id, "equipo_id": eq_id})
            ok, r = api.post("/tickets", json=ticket)
            if ok:
                st.session_state.pop("_sug_ia", None)
                resultado(ok, r, f"Ticket {r['codigo']} creado correctamente.",
                          limpiar="ticket", ir_a=PAGINAS[1], abrir_ticket=r["id"])
            else:
                st.error(r, icon="⛔")

    with col_info:
        sug = st.session_state.get("_sug_ia")
        if sug:
            pasos = "".join(f"<li>{e(p)}</li>" for p in sug.get("pasos", []))
            st.markdown(f"""<div class="tarjeta" style="background:#F5F3FF;border-left:5px solid #7C3AED">
                <h4>🤖 Sugerencia de Google Gemini</h4>
                <div>{badge(sug['categoria'], '#475569')}{badge_prioridad(sug['prioridad'])}</div>
                <div class="dato-etq">Posible diagnóstico</div><div class="dato-val">{e(sug.get('diagnostico'))}</div>
                <div class="dato-etq">Pasos recomendados</div><ol style="margin:.2rem 0 0 1rem">{pasos}</ol>
                <div class="dato-etq">¿Por qué esa prioridad?</div><div class="dato-val">{e(sug.get('justificacion'))}</div>
                <div style="color:#7C3AED;font-size:.8rem;margin-top:.5rem">La sugerencia ya se aplicó en el formulario;
                puede cambiarla antes de crear el ticket. El diagnóstico quedará guardado en el ticket.</div>
                </div>""", unsafe_allow_html=True)
            if st.button("Descartar sugerencia", key="descartar_ia"):
                st.session_state.pop("_sug_ia", None)
                st.rerun()
        if cliente:
            st.markdown(tarjeta_cliente(cliente), unsafe_allow_html=True)
        st.markdown("""<div class="tarjeta" style="background:#F8FAFC"><h4>📌 Reglas al crear</h4>
            <ul style="margin:0 0 0 1rem;color:#475569;font-size:.9rem">
            <li>El cliente puede ser una <b>persona natural</b> (con cédula) o una <b>empresa</b> (con NIT y persona de contacto).</li>
            <li>La cédula o el NIT no se pueden repetir.</li>
            <li>El equipo debe pertenecer al cliente y no puede tener dos tickets activos al mismo tiempo.</li>
            <li>La descripción debe tener al menos 10 caracteres.</li>
            <li>El código TCK-AAAA-NNNN se genera automáticamente y nunca se repite.</li></ul></div>""",
                    unsafe_allow_html=True)


# ===========================================================================
# 4. TÉCNICOS
# ===========================================================================
def pagina_tecnicos():
    encabezado("👷 Técnicos", "Equipo técnico, especialidades y carga de trabajo")
    tabs = st.tabs(["👥 Equipo técnico", "➕ Nuevo técnico", "✏️ Editar · Eliminar"])

    with tabs[0]:
        c = st.columns([2, 1, 1])
        buscar = c[0].text_input("🔎 Buscar técnico", placeholder="Nombre o email…")
        esp = c[1].selectbox("Especialidad", ["Todas"] + CATEGORIAS)
        act = c[2].selectbox("Estado", ["Todos", "Activos", "Inactivos"])
        ok, lista = api.get("/tecnicos", buscar=buscar.strip() or None,
                            especialidad=None if esp == "Todas" else esp,
                            activo={"Todos": None, "Activos": "true", "Inactivos": "false"}[act])
        if not ok:
            st.error(lista, icon="⛔")
        elif not lista:
            sin_datos("No hay técnicos con esos filtros.")
        else:
            cols = st.columns(3)
            for i, x in enumerate(lista):
                carga = x.get("carga_actual", 0)
                pct = min(100, int(carga / MAX_ACTIVOS * 100))
                color = "#059669" if carga < MAX_ACTIVOS - 1 else ("#D97706" if carga < MAX_ACTIVOS else "#DC2626")
                estado_b = badge("Activo", "#059669") if x.get("activo") else badge("Inactivo", "#94A3B8")
                with cols[i % 3]:
                    st.markdown(f"""<div class="tarjeta">
                        <div style="display:flex;justify-content:space-between;align-items:center">
                          <span class="tec-nombre">👷 {e(x['nombre'])}</span>{estado_b}</div>
                        <div style="color:#64748B;font-size:.85rem;margin-top:.2rem">✉️ {e(x['email'])}<br>📞 {e(x['telefono'])}</div>
                        <div style="margin-top:.5rem">{chips(x.get('especialidades'))}</div>
                        <div class="dato-etq">Carga actual</div>
                        <div class="barra"><div style="width:{pct}%;background:{color}"></div></div>
                        <div style="display:flex;justify-content:space-between;font-size:.82rem;color:#475569">
                          <span><b>{carga}/{MAX_ACTIVOS}</b> en proceso</span>
                          <span>✅ <b>{x.get('total_resueltos', 0)}</b> resueltos</span></div>
                        </div>""", unsafe_allow_html=True)

    with tabs[1]:
        with st.form(f"nuevo_tec_{contador_form('tecnico')}"):
            c = st.columns(3)
            nombre = c[0].text_input("Nombre completo")
            email = c[1].text_input("Email")
            tel = c[2].text_input("Teléfono", placeholder="3001234567")
            esps = st.multiselect("Especialidades", CATEGORIAS)
            activo = st.toggle("Activo", value=True)
            if st.form_submit_button("💾 Registrar técnico", type="primary"):
                resultado(*api.post("/tecnicos", json={"nombre": nombre, "email": email, "telefono": tel,
                                                       "especialidades": esps, "activo": activo}),
                          limpiar="tecnico")

    with tabs[2]:
        ok, lista = api.get("/tecnicos")
        if not ok or not lista:
            sin_datos("No hay técnicos registrados.")
            return
        mapa = {x["id"]: x for x in lista}
        tid = st.selectbox("Técnico", list(mapa), format_func=lambda i: mapa[i]["nombre"], key="tec_editar")
        x = mapa[tid]
        c = st.columns([1.6, 1])
        with c[0]:
            with st.form(f"edit_tec_{tid}"):
                cc = st.columns(3)
                nombre = cc[0].text_input("Nombre", x["nombre"])
                email = cc[1].text_input("Email", x["email"])
                tel = cc[2].text_input("Teléfono", x["telefono"])
                esps = st.multiselect("Especialidades", CATEGORIAS, default=x.get("especialidades", []))
                activo = st.toggle("Activo", value=x.get("activo", True),
                                   help="No se puede desactivar si tiene tickets en proceso.")
                if st.form_submit_button("💾 Guardar cambios", type="primary"):
                    resultado(*api.put(f"/tecnicos/{tid}", json={"nombre": nombre, "email": email, "telefono": tel,
                                                                  "especialidades": esps, "activo": activo}))
        with c[1]:
            with st.container(border=True):
                st.markdown("##### 🗑️ Eliminar técnico")
                st.caption("Regla: un técnico con tickets en su historial no se elimina; se marca como inactivo.")
                conf = st.checkbox(f"Confirmo eliminar a {x['nombre']}", key=f"conf_tec_{tid}")
                if st.button("Eliminar", disabled=not conf, key=f"del_tec_{tid}", use_container_width=True):
                    resultado(*api.delete(f"/tecnicos/{tid}"))


# ===========================================================================
# 5. CLIENTES (personas o empresas, con equipos embebidos)
# ===========================================================================
def pagina_clientes():
    encabezado("👥 Clientes", "Personas y empresas atendidas, sus datos de contacto y sus equipos")
    tabs = st.tabs(["📇 Clientes", "➕ Nuevo cliente", "✏️ Editar · Equipos · Eliminar"])

    with tabs[0]:
        ok_all, todos = api.get("/clientes")
        todos = todos if ok_all else []
        n_emp = sum(1 for x in todos if x.get("tipo") == "Empresa")
        c = st.columns(3)
        with c[0]:
            kpi("Clientes", len(todos), "👥", "registrados", AZUL)
        with c[1]:
            kpi("Personas", len(todos) - n_emp, "👤", "a nombre propio", "#0891B2")
        with c[2]:
            kpi("Empresas", n_emp, "🏢", "con persona de contacto", "#7C3AED")
        st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)

        c = st.columns([2, 1, 1])
        buscar = c[0].text_input("🔎 Buscar cliente", placeholder="Nombre, cédula, NIT o contacto…")
        tipo_f = c[1].selectbox("Tipo", ["Todos", "Personas", "Empresas"])
        ciudades = sorted({x["ciudad"] for x in todos})
        ciudad = c[2].selectbox("Ciudad", ["Todas"] + ciudades)
        ok, lista = api.get("/clientes", buscar=buscar.strip() or None,
                            tipo={"Todos": None, "Personas": "Persona", "Empresas": "Empresa"}[tipo_f],
                            ciudad=None if ciudad == "Todas" else ciudad)
        if not ok:
            st.error(lista, icon="⛔")
        elif not lista:
            sin_datos("No hay clientes con esos filtros.")
        else:
            df = pd.DataFrame([{
                "Tipo": f"{icono_cliente(x.get('tipo'))} {nombre_tipo(x.get('tipo'))}",
                "Cliente": x["nombre"],
                "Cédula / NIT": x.get("documento"),
                "Ciudad": x["ciudad"],
                "Contacto": x["contacto"].get("nombre") if x.get("tipo") == "Empresa" else "—",
                "Email": x["contacto"]["email"],
                "Teléfono": x["contacto"]["telefono"],
                "Equipos": len(x.get("equipos", [])),
            } for x in lista])
            st.dataframe(df, hide_index=True, use_container_width=True,
                         column_config={"Equipos": st.column_config.ProgressColumn(
                             "Equipos", format="%d", min_value=0, max_value=max(5, int(df.Equipos.max())))})

    with tabs[1]:
        resp = st.radio("¿El cliente es una persona o viene de parte de una empresa?",
                        ["👤 Persona natural (a nombre propio)", "🏢 Empresa"], horizontal=True, key="tipo_nuevo_cli")
        tipo = "Empresa" if "Empresa" in resp else "Persona"
        with st.form(f"nuevo_cli_{tipo}_{contador_form('cliente')}"):
            datos = campos_cliente(tipo)
            if st.form_submit_button("💾 Registrar cliente", type="primary"):
                resultado(*api.post("/clientes", json=datos), limpiar="cliente")

    with tabs[2]:
        ok, lista = api.get("/clientes")
        if not ok or not lista:
            sin_datos("No hay clientes registrados.")
            return
        mapa = {x["id"]: x for x in lista}
        cid = st.selectbox("Cliente", list(mapa), key="cli_editar",
                           format_func=lambda i: f"{icono_cliente(mapa[i].get('tipo'))} {mapa[i]['nombre']} · "
                                                 f"{etiqueta_documento(mapa[i].get('tipo'))} {mapa[i].get('documento')}")
        x = mapa[cid]
        tipo = x.get("tipo", "Empresa")
        c = st.columns([1.15, 1])
        with c[0]:
            with st.form(f"edit_cli_{cid}"):
                st.markdown(f"**{icono_cliente(tipo)} {nombre_tipo(tipo)}** · el tipo y el documento no se pueden cambiar")
                datos = campos_cliente(tipo, x, nuevo=False)
                if st.form_submit_button("💾 Guardar cambios", type="primary"):
                    resultado(*api.put(f"/clientes/{cid}", json=datos))
            with st.container(border=True):
                st.markdown("##### 🗑️ Eliminar cliente")
                st.caption("Regla: no se elimina un cliente que tenga tickets registrados.")
                conf = st.checkbox(f"Confirmo eliminar a {x['nombre']}", key=f"conf_cli_{cid}")
                if st.button("Eliminar cliente", disabled=not conf, key=f"del_cli_{cid}"):
                    resultado(*api.delete(f"/clientes/{cid}"))

        with c[1]:
            with st.container(border=True):
                st.markdown(f"##### 🖥️ Equipos ({len(x.get('equipos', []))}) · embebidos en el cliente")
                for eq in x.get("equipos", []):
                    cc = st.columns([5, 1])
                    cc[0].markdown(f"**{e(eq['nombre'])}**  \n"
                                   f"<span style='color:#64748B;font-size:.85rem'>{e(eq['tipo'])} · "
                                   f"{e(eq['marca'])} · S/N {e(eq['serial'])}</span>", unsafe_allow_html=True)
                    if cc[1].button("🗑️", key=f"del_eq_{eq['equipo_id']}", help="Eliminar equipo"):
                        resultado(*api.delete(f"/clientes/{cid}/equipos/{eq['equipo_id']}"))
                if not x.get("equipos"):
                    st.caption("Sin equipos registrados.")
            with st.form(f"nuevo_eq_{cid}_{contador_form('equipo')}"):
                st.markdown("**➕ Agregar equipo**")
                datos_eq = campos_equipo()
                if st.form_submit_button("Agregar equipo", use_container_width=True):
                    resultado(*api.post(f"/clientes/{cid}/equipos", json=datos_eq), limpiar="equipo")


# ===========================================================================
# 6. ANALÍTICA (Aggregation Pipeline)
# ===========================================================================
def pagina_analitica():
    encabezado("📊 Analítica", "Indicadores calculados en MongoDB Atlas con Aggregation Pipeline")

    # --- Informe ejecutivo con IA ---
    with st.container(border=True):
        c = st.columns([3, 1])
        c[0].markdown("#### 🤖 Informe ejecutivo con IA")
        c[0].caption("El backend calcula los indicadores con agregaciones y Google Gemini los resume para la gerencia.")
        if c[1].button("Generar informe", type="primary", use_container_width=True):
            with st.spinner("🤖 Google Gemini está leyendo los indicadores…"):
                ok, r = api.get_directo("/ia/resumen-analitica")
            if ok:
                st.session_state["_informe_ia"] = r["informe"]
            else:
                st.error(r, icon="🤖")
        if st.session_state.get("_informe_ia"):
            st.markdown(st.session_state["_informe_ia"])

    # --- Rendimiento por técnico ---
    with st.container(border=True):
        st.markdown("#### 🏆 Ranking de técnicos")
        pregunta("¿Qué técnico resuelve más servicios, cuánto factura y qué tan rápido trabaja?")
        st.caption("Pipeline: $match → $lookup (tecnicos) → $unwind → $group → $sort → $project")
        ok, d = api.get("/analytics/rendimiento-tecnicos")
        if ok and d:
            df = pd.DataFrame(d)
            c = st.columns([1.2, 1])
            c[0].altair_chart(grafico_barras(df, "tecnico", "total_resueltos", "", "Tickets resueltos"),
                              use_container_width=True)
            c[1].dataframe(df.rename(columns={
                "tecnico": "Técnico", "total_resueltos": "Resueltos", "ingresos_totales": "Ingresos",
                "costo_promedio": "Costo prom.", "horas_promedio": "Horas prom."}),
                hide_index=True, use_container_width=True,
                column_config={"Ingresos": st.column_config.NumberColumn(format="$ %d"),
                               "Costo prom.": st.column_config.NumberColumn(format="$ %d")})
        else:
            sin_datos("Aún no hay tickets resueltos." if ok else d)

    c = st.columns(2)
    # --- Por categoría ---
    with c[0]:
        with st.container(border=True):
            st.markdown("#### 🗂️ Servicios por categoría")
            pregunta("¿Qué tipo de servicio se solicita más y cuál se resuelve mejor?")
            ok, d = api.get("/analytics/por-categoria")
            if ok and d:
                df = pd.DataFrame(d)
                largo = df.melt(id_vars="categoria", value_vars=["total", "resueltos"],
                                var_name="tipo", value_name="cantidad")
                largo["tipo"] = largo["tipo"].map({"total": "Solicitados", "resueltos": "Resueltos"})
                graf = alt.Chart(largo).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
                    x=alt.X("categoria:N", title=None, axis=alt.Axis(labelAngle=0)),
                    xOffset="tipo:N",
                    y=alt.Y("cantidad:Q", title="Tickets"),
                    color=alt.Color("tipo:N", scale=alt.Scale(range=["#93C5FD", "#1E3A8A"]),
                                    legend=alt.Legend(orient="bottom", title=None)),
                    tooltip=["categoria", "tipo", "cantidad"]).properties(height=280)
                st.altair_chart(graf, use_container_width=True)
                st.dataframe(df.rename(columns={"categoria": "Categoría", "total": "Total", "resueltos": "Resueltos",
                                                "ingresos": "Ingresos", "tasa_resolucion": "% resolución"}),
                             hide_index=True, use_container_width=True,
                             column_config={"Ingresos": st.column_config.NumberColumn(format="$ %d"),
                                            "% resolución": st.column_config.NumberColumn(format="%.1f %%")})
            else:
                sin_datos("Sin datos." if ok else d)
    # --- Top clientes ---
    with c[1]:
        with st.container(border=True):
            st.markdown("#### 💎 Clientes con mayor gasto")
            pregunta("¿Cuáles son los clientes más valiosos para la empresa?")
            limite = st.slider("Mostrar top", 3, 10, 5)
            ok, d = api.get("/analytics/top-clientes", limite=limite)
            if ok and d:
                df = pd.DataFrame(d)
                st.altair_chart(grafico_barras(df, "cliente", "gasto_total", "", "Gasto total (COP)",
                                               color="#7C3AED", horizontal=True, formato="$,.0f", alto=260),
                                use_container_width=True)
                st.caption("Pipeline: $match → $group → $sort → **$limit** → $lookup (clientes) → $unwind → $project")
            else:
                sin_datos("Aún no hay servicios resueltos." if ok else d)

    # --- Evolución mensual ---
    with st.container(border=True):
        st.markdown("#### 📈 Evolución mensual")
        pregunta("¿Cómo cambia la demanda de soporte y los ingresos mes a mes?")
        ok, d = api.get("/analytics/por-mes")
        if ok and d:
            df = pd.DataFrame(d)
            c = st.columns(2)
            largo = df.melt(id_vars="mes", value_vars=["creados", "resueltos"], var_name="tipo", value_name="tickets")
            lineas = alt.Chart(largo).mark_line(point=True, strokeWidth=3).encode(
                x=alt.X("mes:N", title="Mes", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("tickets:Q", title="Tickets"),
                color=alt.Color("tipo:N", scale=alt.Scale(domain=["creados", "resueltos"],
                                                          range=["#2563EB", "#059669"]),
                                legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["mes", "tipo", "tickets"]).properties(height=280)
            c[0].altair_chart(lineas, use_container_width=True)
            area = alt.Chart(df).mark_area(line={"color": "#059669"}, color=alt.Gradient(
                gradient="linear", stops=[alt.GradientStop(color="#FFFFFF", offset=0),
                                          alt.GradientStop(color="#6EE7B7", offset=1)],
                x1=1, x2=1, y1=1, y2=0)).encode(
                x=alt.X("mes:N", title="Mes", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("ingresos:Q", title="Ingresos (COP)"),
                tooltip=["mes", alt.Tooltip("ingresos:Q", format="$,.0f")]).properties(height=280)
            c[1].altair_chart(area, use_container_width=True)
        else:
            sin_datos("Sin datos." if ok else d)

    # --- Personas vs. empresas ---
    with st.container(border=True):
        st.markdown("#### 👤🏢 Personas vs. empresas")
        pregunta("¿Quién genera más trabajo e ingresos: los clientes particulares o las empresas?")
        st.caption("Pipeline: $lookup (clientes) → $unwind → $group (con $addToSet) → $project ($size) → $sort")
        ok, d = api.get("/analytics/por-tipo-cliente")
        if ok and d:
            df = pd.DataFrame(d)
            df["tipo"] = df["tipo"].map(lambda t: f"{icono_cliente(t)} {nombre_tipo(t)}")
            c = st.columns([1, 1, 1.2])
            dona = alt.Chart(df).mark_arc(innerRadius=55, cornerRadius=5).encode(
                theta="tickets:Q",
                color=alt.Color("tipo:N", scale=alt.Scale(range=["#7C3AED", "#0891B2"]),
                                legend=alt.Legend(orient="bottom", title=None)),
                tooltip=[alt.Tooltip("tipo:N", title="Tipo"), alt.Tooltip("tickets:Q", title="Tickets")],
            ).properties(height=240, title="Tickets")
            c[0].altair_chart(dona, use_container_width=True)
            barras = alt.Chart(df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
                x=alt.X("tipo:N", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("ingresos:Q", title="Ingresos (COP)"),
                color=alt.Color("tipo:N", scale=alt.Scale(range=["#7C3AED", "#0891B2"]), legend=None),
                tooltip=["tipo", alt.Tooltip("ingresos:Q", format="$,.0f")],
            ).properties(height=240, title="Ingresos")
            c[1].altair_chart(barras, use_container_width=True)
            c[2].dataframe(df.rename(columns={"tipo": "Tipo", "clientes": "Clientes", "tickets": "Tickets",
                                              "ingresos": "Ingresos", "ticket_promedio": "Ticket prom."}),
                           hide_index=True, use_container_width=True,
                           column_config={"Ingresos": st.column_config.NumberColumn(format="$ %d"),
                                          "Ticket prom.": st.column_config.NumberColumn(format="$ %d")})
        else:
            sin_datos("Sin datos." if ok else d)

    c = st.columns(2)
    # --- Por ciudad ---
    with c[0]:
        with st.container(border=True):
            st.markdown("#### 🗺️ Demanda por ciudad")
            pregunta("¿En qué ciudades hay más solicitudes de soporte?")
            ok, d = api.get("/analytics/por-ciudad")
            if ok and d:
                df = pd.DataFrame(d)
                st.altair_chart(grafico_barras(df, "ciudad", "tickets", "", "Tickets", color="#0891B2"),
                                use_container_width=True)
            else:
                sin_datos("Sin datos." if ok else d)
    # --- Equipos con más fallas ---
    with c[1]:
        with st.container(border=True):
            st.markdown("#### 🔧 Tipos de equipo con más fallas")
            pregunta("¿Qué equipos fallan más? (para planear mantenimiento preventivo)")
            ok, d = api.get("/analytics/equipos-fallas")
            if ok and d:
                df = pd.DataFrame(d)
                st.altair_chart(grafico_barras(df, "tipo_equipo", "fallas", "", "Fallas reportadas",
                                               color="#DC2626", horizontal=True),
                                use_container_width=True)
            else:
                sin_datos("Sin datos." if ok else d)

    c = st.columns(2)
    # --- Satisfacción ---
    with c[0]:
        with st.container(border=True):
            st.markdown("#### ⭐ Satisfacción por técnico")
            pregunta("¿Qué técnicos dejan más satisfechos a los clientes? (encuestas del portal)")
            ok, d = api.get("/analytics/satisfaccion")
            if ok and d:
                df = pd.DataFrame(d)
                graf = alt.Chart(df).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6,
                                              color="#F59E0B").encode(
                    y=alt.Y("tecnico:N", sort="-x", title=None),
                    x=alt.X("promedio:Q", title="Calificación promedio", scale=alt.Scale(domain=[0, 5])),
                    tooltip=[alt.Tooltip("tecnico:N", title="Técnico"), alt.Tooltip("promedio:Q", title="Promedio"),
                             alt.Tooltip("encuestas:Q", title="Encuestas")]).properties(height=230)
                st.altair_chart(graf, use_container_width=True)
                ok_c, com = api.get("/analytics/comentarios")
                if ok_c and com:
                    st.markdown("**Últimos comentarios**")
                    for x in com[:4]:
                        st.markdown(f"{estrellas(x['puntaje'])} <b>{e(x['cliente'])}</b> · "
                                    f"<span style='color:#64748B'>{e(x['comentario'])}</span>",
                                    unsafe_allow_html=True)
            else:
                sin_datos("Aún no hay encuestas." if ok else d)
    # --- Repuestos ---
    with c[1]:
        with st.container(border=True):
            st.markdown("#### 🔩 Repuestos más usados")
            pregunta("¿Qué repuestos se consumen más y cuánto dinero representan?")
            st.caption("Pipeline: $match → **$unwind** (repuestos_usados) → $group → $sort → $limit → $project")
            ok, d = api.get("/analytics/repuestos-mas-usados")
            if ok and d:
                df = pd.DataFrame(d)
                st.altair_chart(grafico_barras(df, "repuesto", "unidades", "", "Unidades usadas",
                                               color="#0F766E", horizontal=True, alto=230),
                                use_container_width=True)
            else:
                sin_datos("Aún no se han usado repuestos." if ok else d)
            ok, d = api.get("/analytics/stock-bajo")
            if ok and d:
                st.markdown("**⚠️ Para volver a comprar** (stock ≤ mínimo, consulta con `$expr`)")
                st.dataframe(pd.DataFrame(d).rename(columns={"sku": "Código", "nombre": "Repuesto",
                                                             "categoria": "Categoría", "stock": "Stock",
                                                             "stock_minimo": "Mínimo", "faltante": "Faltan"}),
                             hide_index=True, use_container_width=True)

    # --- Pendientes ---
    with st.container(border=True):
        st.markdown("#### ⏰ Solicitudes sin asignar")
        pregunta("¿Qué solicitudes llevan demasiado tiempo esperando un técnico?")
        horas = st.slider("Más de (horas)", 1, 240, 48, step=1)
        ok, d = api.get("/analytics/pendientes", horas=horas)
        if ok and d:
            df = pd.DataFrame(d).rename(columns={"codigo": "Código", "cliente": "Cliente", "equipo": "Equipo",
                                                 "prioridad": "Prioridad", "horas_esperando": "Horas esperando"})
            st.dataframe(df, hide_index=True, use_container_width=True)
        elif ok:
            st.success(f"No hay solicitudes con más de {horas} horas sin asignar.", icon="👌")
        else:
            st.error(d)


# ===========================================================================
# 7. INVENTARIO DE REPUESTOS
# ===========================================================================
def pagina_inventario():
    encabezado("📦 Inventario de repuestos",
               "Stock de repuestos. Al cerrar un ticket se descuentan con una transacción de MongoDB")
    ok, todos = api.get("/repuestos")
    if not ok:
        st.error(todos, icon="⛔")
        return
    bajos = [r for r in todos if r["stock"] <= r["stock_minimo"]]
    c = st.columns(4)
    with c[0]:
        kpi("Repuestos", len(todos), "📦", "referencias distintas", AZUL)
    with c[1]:
        kpi("Unidades", sum(r["stock"] for r in todos), "🔩", "en bodega", "#0891B2")
    with c[2]:
        kpi("Valor del inventario", dinero(sum(r["stock"] * r["precio_unitario"] for r in todos)), "💰",
            "stock × precio", "#059669")
    with c[3]:
        kpi("Stock bajo", len(bajos), "⚠️", "para volver a comprar", "#DC2626" if bajos else "#94A3B8")
    st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)

    tabs = st.tabs(["📋 Inventario", "➕ Nuevo repuesto", "🔄 Entradas · Editar · Eliminar"])
    with tabs[0]:
        c = st.columns([2, 1, 1])
        buscar = c[0].text_input("🔎 Buscar repuesto", placeholder="Código o nombre…")
        cat = c[1].selectbox("Categoría", ["Todas"] + CATEGORIAS_REPUESTO)
        solo_bajo = c[2].toggle("Solo stock bajo", value=False)
        ok, lista = api.get("/repuestos", buscar=buscar.strip() or None,
                            categoria=None if cat == "Todas" else cat,
                            solo_stock_bajo="true" if solo_bajo else None)
        if not ok:
            st.error(lista, icon="⛔")
        elif not lista:
            sin_datos("No hay repuestos con esos filtros.")
        else:
            df = pd.DataFrame([{
                "Estado": "🔴 Stock bajo" if r["stock"] <= r["stock_minimo"] else "🟢 OK",
                "Código": r["sku"], "Repuesto": r["nombre"], "Categoría": r["categoria"],
                "Stock": r["stock"], "Mínimo": r["stock_minimo"],
                "Precio unit.": r["precio_unitario"], "Valor en bodega": r["stock"] * r["precio_unitario"],
            } for r in lista])
            st.dataframe(df, hide_index=True, use_container_width=True, column_config={
                "Stock": st.column_config.ProgressColumn("Stock", format="%d", min_value=0,
                                                         max_value=max(10, int(df.Stock.max()))),
                "Precio unit.": st.column_config.NumberColumn(format="$ %d"),
                "Valor en bodega": st.column_config.NumberColumn(format="$ %d")})

    with tabs[1]:
        with st.form(f"nuevo_rep_{contador_form('repuesto')}"):
            c = st.columns([1, 2, 1])
            sku = c[0].text_input("Código (SKU)", placeholder="FTE-500W",
                                  help="Mayúsculas, números y guiones").upper()
            nombre = c[1].text_input("Nombre del repuesto", placeholder="Fuente de poder 500W")
            categoria = c[2].selectbox("Categoría", CATEGORIAS_REPUESTO)
            c = st.columns(3)
            precio = c[0].number_input("Precio unitario (COP)", min_value=0.0, step=5000.0, format="%.0f")
            stock = c[1].number_input("Stock inicial", min_value=0, step=1)
            minimo = c[2].number_input("Stock mínimo (alerta)", min_value=0, step=1, value=2)
            if st.form_submit_button("💾 Registrar repuesto", type="primary"):
                resultado(*api.post("/repuestos", json={"sku": sku, "nombre": nombre, "categoria": categoria,
                                                        "precio_unitario": precio, "stock": int(stock),
                                                        "stock_minimo": int(minimo)}), limpiar="repuesto")

    with tabs[2]:
        if not todos:
            sin_datos("No hay repuestos registrados.")
            return
        mapa = {r["id"]: r for r in todos}
        rid = st.selectbox("Repuesto", list(mapa), key="rep_sel",
                           format_func=lambda i: f"{mapa[i]['sku']} · {mapa[i]['nombre']} (stock {mapa[i]['stock']})")
        r = mapa[rid]
        c = st.columns([1, 1.2])
        with c[0]:
            with st.form(f"entrada_{rid}_{contador_form('entrada')}"):
                st.markdown("**📥 Registrar entrada de stock**")
                cant = st.number_input("Unidades que llegaron", min_value=1, step=1, value=5)
                nota = st.text_input("Referencia", value="Compra a proveedor")
                if st.form_submit_button("Registrar entrada", type="primary", use_container_width=True):
                    resultado(*api.post(f"/repuestos/{rid}/entrada", json={"cantidad": int(cant), "nota": nota}),
                              limpiar="entrada")
            with st.form(f"edit_rep_{rid}"):
                st.markdown("**✏️ Editar** · el stock solo cambia con entradas o al usarse en tickets")
                nombre = st.text_input("Nombre", r["nombre"])
                cc = st.columns(3)
                categoria = cc[0].selectbox("Categoría", CATEGORIAS_REPUESTO,
                                            index=CATEGORIAS_REPUESTO.index(r["categoria"]))
                precio = cc[1].number_input("Precio unitario", min_value=0.0, value=float(r["precio_unitario"]),
                                            step=5000.0, format="%.0f")
                minimo = cc[2].number_input("Stock mínimo", min_value=0, value=int(r["stock_minimo"]), step=1)
                if st.form_submit_button("💾 Guardar cambios"):
                    resultado(*api.put(f"/repuestos/{rid}", json={"nombre": nombre, "categoria": categoria,
                                                                   "precio_unitario": precio,
                                                                   "stock_minimo": int(minimo)}))
            with st.container(border=True):
                st.markdown("##### 🗑️ Eliminar repuesto")
                st.caption("Regla: un repuesto que ya se usó en algún ticket no se puede eliminar.")
                conf = st.checkbox(f"Confirmo eliminar {r['sku']}", key=f"conf_rep_{rid}")
                if st.button("Eliminar", disabled=not conf, key=f"del_rep_{rid}"):
                    resultado(*api.delete(f"/repuestos/{rid}"))
        with c[1]:
            with st.container(border=True):
                st.markdown("##### 🧾 Últimos movimientos (embebidos en el repuesto)")
                movs = list(reversed(r.get("movimientos") or []))[:15]
                if movs:
                    st.dataframe(pd.DataFrame([{
                        "Fecha": fecha(m["fecha"]),
                        "Tipo": ("📥 " if m["tipo"] == "Entrada" else "📤 ") + m["tipo"],
                        "Cantidad": m["cantidad"] if m["tipo"] == "Entrada" else -m["cantidad"],
                        "Referencia": m.get("referencia", ""),
                    } for m in movs]), hide_index=True, use_container_width=True)
                else:
                    st.caption("Sin movimientos.")


# ===========================================================================
# 8. PORTAL DEL CLIENTE
# ===========================================================================
PASOS_ESTADO = ["Abierto", "En Proceso", "Resuelto"]


def pagina_portal():
    encabezado("🙋 Portal del cliente", "Consulte el estado de su servicio y califique la atención recibida")

    col_form, col_ayuda = st.columns([1.3, 1])
    with col_form:
        with st.form("portal_buscar"):
            c = st.columns(2)
            codigo = c[0].text_input("Código del ticket", placeholder="TCK-2026-0001",
                                     value=st.session_state.get("portal_codigo", ""))
            documento = c[1].text_input("Su cédula o NIT", placeholder="Ej: 1036598741",
                                        value=st.session_state.get("portal_doc", ""))
            if st.form_submit_button("🔎 Consultar mi servicio", type="primary", use_container_width=True):
                st.session_state["portal_codigo"] = codigo.strip().upper()
                st.session_state["portal_doc"] = documento.strip()
    with col_ayuda:
        st.markdown("""<div class="tarjeta" style="background:#F8FAFC"><h4>ℹ️ ¿Cómo funciona?</h4>
            <ul style="margin:0 0 0 1rem;color:#475569;font-size:.9rem">
            <li>Escriba el código que le entregaron al registrar la solicitud.</li>
            <li>Por seguridad, debe coincidir con la cédula o el NIT del cliente.</li>
            <li>Cuando el servicio esté <b>Resuelto</b> podrá calificarlo una sola vez.</li></ul></div>""",
                    unsafe_allow_html=True)

    codigo, documento = st.session_state.get("portal_codigo"), st.session_state.get("portal_doc")
    if not codigo or not documento:
        return
    ok, t = api.get_directo("/portal/ticket", codigo=codigo, documento=documento)
    if not ok:
        st.error(t, icon="🔒")
        return

    estado = t["estado"]
    color = COLOR_ESTADO.get(estado, AZUL)
    st.markdown(f"""<div class="ticket-cab" style="--c:{color}">
        <div class="ticket-cod">{e(t['codigo'])} &nbsp;{badge_estado(estado)}{badge_prioridad(t['prioridad'])}</div>
        <div class="ticket-sub">Hola, <b>{e(t['cliente'])}</b> · 🖥️ {e(t['equipo']['nombre'])}
        ({e(t['equipo']['tipo'])}) · solicitado el {fecha(t['created_at'])}</div></div>""", unsafe_allow_html=True)

    # Línea de progreso del servicio
    if estado == "Cancelado":
        st.warning("Este servicio fue **cancelado**. Si tiene dudas, comuníquese con ServiFix.", icon="⚪")
    else:
        actual = PASOS_ESTADO.index(estado)
        nombres = {"Abierto": "Solicitud recibida", "En Proceso": "Técnico trabajando", "Resuelto": "Servicio terminado"}
        celdas = ""
        for i, p in enumerate(PASOS_ESTADO):
            hecho = i <= actual
            fondo = COLOR_ESTADO[p] if hecho else "#E2E8F0"
            texto = "white" if hecho else "#94A3B8"
            celdas += (f'<div style="flex:1;background:{fondo};color:{texto};padding:.65rem;border-radius:10px;'
                       f'text-align:center;font-weight:600">{"✅" if hecho else "⏳"} {nombres[p]}</div>')
        st.markdown(f'<div style="display:flex;gap:.5rem;margin-bottom:1rem">{celdas}</div>', unsafe_allow_html=True)

    c = st.columns([1.3, 1])
    with c[0]:
        items = "".join(f"""<div class="tl-item" style="--c:{COLOR_ESTADO.get(b.get('estado'), AZUL)}">
                <div class="tl-fecha">{fecha(b['fecha'])}</div><div class="tl-nota">{e(b['nota'])}</div></div>"""
                        for b in t.get("bitacora", []))
        st.markdown(f'<div class="tarjeta"><h4>🕓 Seguimiento</h4><div class="timeline">{items}</div></div>',
                    unsafe_allow_html=True)
    with c[1]:
        reps = "".join(f"<li>{x['cantidad']}× {e(x['nombre'])} — {dinero(x['subtotal'])}</li>"
                       for x in t.get("repuestos_usados", []))
        bloque_reps = (f"<div class='dato-etq'>Repuestos</div><ul style='margin:.2rem 0 0 1rem'>{reps}</ul>"
                       if reps else "")
        st.markdown(f"""<div class="tarjeta"><h4>🧾 Resumen</h4>
            <div class="dato-etq">Técnico asignado</div><div class="dato-val">{e(t.get('tecnico') or 'Pendiente de asignar')}</div>
            <div class="dato-etq">Falla reportada</div><div class="dato-val">{e(t['descripcion'])}</div>{bloque_reps}
            <div class="dato-etq">Valor del servicio</div>
            <div style="font-size:1.4rem;font-weight:800">{dinero(t.get('costo')) if estado == 'Resuelto' else 'Por definir'}</div>
            </div>""", unsafe_allow_html=True)
        if st.button("📄 Descargar orden de servicio (PDF)", use_container_width=True):
            ok_pdf, pdf = api.get_directo("/portal/ticket/pdf", codigo=codigo, documento=documento)
            if ok_pdf:
                st.session_state["_portal_pdf"] = (codigo, pdf)
            else:
                st.error(pdf)
        guardado = st.session_state.get("_portal_pdf")
        if guardado and guardado[0] == codigo:
            st.download_button("⬇️ Guardar PDF", guardado[1], f"orden_{codigo}.pdf", "application/pdf",
                               type="primary", use_container_width=True)

    # Encuesta de satisfacción
    if estado == "Resuelto":
        with st.container(border=True):
            cal = t.get("calificacion")
            if cal:
                st.markdown(f"#### ⭐ Su calificación: {estrellas(cal['puntaje'])} **{cal['puntaje']}/5**",
                            unsafe_allow_html=True)
                st.caption(f"“{cal.get('comentario') or 'Sin comentario'}” · ¡Gracias por ayudarnos a mejorar!")
            else:
                st.markdown("#### ⭐ ¿Cómo calificaría nuestro servicio?")
                with st.form(f"encuesta_{codigo}"):
                    opciones = {5: "⭐⭐⭐⭐⭐ Excelente", 4: "⭐⭐⭐⭐ Bueno", 3: "⭐⭐⭐ Aceptable",
                                2: "⭐⭐ Malo", 1: "⭐ Muy malo"}
                    puntaje = st.radio("Calificación", list(opciones), format_func=opciones.get, horizontal=True)
                    comentario = st.text_area("Comentario (opcional)", max_chars=300, height=80)
                    if st.form_submit_button("Enviar calificación", type="primary"):
                        resultado(*api.post("/portal/calificar", json={
                            "codigo": codigo, "documento": documento, "puntaje": puntaje,
                            "comentario": comentario.strip() or None}))


# ---------------------------------------------------------------------------
# ENRUTADOR
# ---------------------------------------------------------------------------
mostrar_aviso()
{
    PAGINAS[0]: pagina_panel,
    PAGINAS[1]: pagina_tickets,
    PAGINAS[2]: pagina_nuevo_ticket,
    PAGINAS[3]: pagina_tecnicos,
    PAGINAS[4]: pagina_clientes,
    PAGINAS[5]: pagina_inventario,
    PAGINAS[6]: pagina_analitica,
    PAGINAS[7]: pagina_portal,
}[pagina]()
