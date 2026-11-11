"""
pdf_report.py
-------------
Genera la "Orden de Servicio Técnico" en PDF con ReportLab.
Recibe el ticket con los datos del cliente y del técnico (ya unidos con $lookup)
y devuelve los bytes del PDF.
"""
import io
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
import math

from reportlab.platypus import (CondPageBreak, Flowable, Image, KeepTogether, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

COL = timezone(timedelta(hours=-5))

# Paleta (la misma de la interfaz)
AZUL = colors.HexColor("#1E3A8A")
AZUL_CLARO = colors.HexColor("#EFF4FF")
GRIS = colors.HexColor("#64748B")
GRIS_LINEA = colors.HexColor("#E2E8F0")
TEXTO = colors.HexColor("#0F172A")

COLOR_ESTADO = {
    "Abierto": colors.HexColor("#2563EB"),
    "En Proceso": colors.HexColor("#D97706"),
    "Resuelto": colors.HexColor("#059669"),
    "Cancelado": colors.HexColor("#6B7280"),
}
COLOR_PRIORIDAD = {
    "Baja": colors.HexColor("#10B981"),
    "Media": colors.HexColor("#3B82F6"),
    "Alta": colors.HexColor("#F59E0B"),
    "Crítica": colors.HexColor("#DC2626"),
}

ANCHO_PAGINA, ALTO_PAGINA = letter
MARGEN = 1.6 * cm
ANCHO_UTIL = ANCHO_PAGINA - 2 * MARGEN

_base = getSampleStyleSheet()
E = {
    "normal": ParagraphStyle("n", parent=_base["Normal"], fontName="Helvetica",
                             fontSize=9, leading=12, textColor=TEXTO),
    "pequeno": ParagraphStyle("p", parent=_base["Normal"], fontName="Helvetica",
                              fontSize=8, leading=10, textColor=GRIS),
    "etiqueta": ParagraphStyle("e", parent=_base["Normal"], fontName="Helvetica-Bold",
                               fontSize=7.5, leading=9, textColor=GRIS),
    "valor": ParagraphStyle("v", parent=_base["Normal"], fontName="Helvetica-Bold",
                            fontSize=10, leading=13, textColor=TEXTO),
    "seccion": ParagraphStyle("s", parent=_base["Normal"], fontName="Helvetica-Bold",
                              fontSize=10.5, leading=14, textColor=AZUL, spaceBefore=10, spaceAfter=5),
    "celda_titulo": ParagraphStyle("ct", parent=_base["Normal"], fontName="Helvetica-Bold",
                                   fontSize=8, leading=10, textColor=colors.white),
    "centro": ParagraphStyle("c", parent=_base["Normal"], fontName="Helvetica",
                             fontSize=8, leading=10, textColor=GRIS, alignment=TA_CENTER),
    "total": ParagraphStyle("t", parent=_base["Normal"], fontName="Helvetica-Bold",
                            fontSize=15, leading=18, textColor=AZUL, alignment=TA_RIGHT),
}


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------
def _txt(valor, defecto="—") -> str:
    """Texto seguro para ReportLab (escapa < > & y quita caracteres que Helvetica no tiene)."""
    if valor is None or valor == "":
        return defecto
    s = str(valor).replace("→", "->")
    return escape(s)


def _fecha(valor, con_hora=True) -> str:
    if not valor:
        return "—"
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor)
        except ValueError:
            return valor
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    valor = valor.astimezone(COL)
    return valor.strftime("%d/%m/%Y %I:%M %p" if con_hora else "%d/%m/%Y")


def _dinero(valor) -> str:
    return "$ " + f"{float(valor or 0):,.0f}".replace(",", ".") + " COP"


def _duracion(inicio, fin) -> str:
    if not inicio or not fin:
        return "—"
    if isinstance(inicio, str):
        inicio = datetime.fromisoformat(inicio)
    if isinstance(fin, str):
        fin = datetime.fromisoformat(fin)
    horas = (fin - inicio).total_seconds() / 3600
    if horas < 24:
        return f"{horas:.1f} horas"
    return f"{horas / 24:.1f} días ({horas:.0f} h)"


def _par(etiqueta, valor):
    """Bloque etiqueta pequeña + valor."""
    return [Paragraph(etiqueta.upper(), E["etiqueta"]), Paragraph(valor, E["normal"])]


def _badge(texto, color):
    """Celda de color tipo 'etiqueta'."""
    t = Table([[Paragraph(f"<b>{_txt(texto)}</b>", ParagraphStyle(
        "b", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=TA_CENTER))]],
        colWidths=[3.2 * cm], rowHeights=[0.62 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return t


def _tarjeta(titulo: str, filas: list, ancho: float) -> Table:
    """Recuadro con título azul y pares etiqueta/valor."""
    contenido = [[Paragraph(titulo.upper(), E["celda_titulo"])]]
    for etiqueta, valor in filas:
        contenido.append([[Paragraph(etiqueta.upper(), E["etiqueta"]),
                           Paragraph(valor, E["normal"])]])
    t = Table(contenido, colWidths=[ancho])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS_LINEA),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _imagen_evidencia(url: str):
    """Descarga la foto de Cloudinary y la ajusta al ancho disponible."""
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        lector = ImageReader(io.BytesIO(r.content))
        ancho, alto = lector.getSize()
        max_ancho, max_alto = 9 * cm, 6.5 * cm
        escala = min(max_ancho / ancho, max_alto / alto)
        return Image(io.BytesIO(r.content), width=ancho * escala, height=alto * escala)
    except Exception:
        return None


class Estrellas(Flowable):
    """Dibuja de 1 a 5 estrellas (calificación del cliente) alineadas a la derecha."""

    def __init__(self, puntaje: int, ancho: float, tam: float = 9):
        super().__init__()
        self.puntaje, self.ancho, self.tam = int(puntaje), ancho, tam
        self.width, self.height = ancho, tam * 2 + 2

    def _estrella(self, c, cx, cy, r, color):
        puntos = []
        for i in range(10):
            ang = math.pi / 2 + i * math.pi / 5
            rad = r if i % 2 == 0 else r * 0.45
            puntos += [cx + rad * math.cos(ang), cy + rad * math.sin(ang)]
        c.setFillColor(color)
        p = c.beginPath()
        p.moveTo(puntos[0], puntos[1])
        for j in range(2, len(puntos), 2):
            p.lineTo(puntos[j], puntos[j + 1])
        p.close()
        c.drawPath(p, stroke=0, fill=1)

    def draw(self):
        c = self.canv
        paso = self.tam * 2.3
        x0 = self.ancho - paso * 5
        for i in range(5):
            color = colors.HexColor("#F59E0B") if i < self.puntaje else colors.HexColor("#CBD5E1")
            self._estrella(c, x0 + paso * i + self.tam, self.tam + 1, self.tam, color)


# ---------------------------------------------------------------------------
# Encabezado y pie de cada página
# ---------------------------------------------------------------------------
def _decorar_pagina(ticket):
    def dibujar(c, doc):
        c.saveState()
        # Banda superior
        c.setFillColor(AZUL)
        c.rect(0, ALTO_PAGINA - 2.6 * cm, ANCHO_PAGINA, 2.6 * cm, stroke=0, fill=1)
        # Logo (cuadro con llave)
        c.setFillColor(colors.white)
        c.roundRect(MARGEN, ALTO_PAGINA - 2.05 * cm, 1.5 * cm, 1.5 * cm, 6, stroke=0, fill=1)
        c.setFillColor(AZUL)
        c.setFont("Helvetica-Bold", 17)
        c.drawCentredString(MARGEN + 0.75 * cm, ALTO_PAGINA - 1.5 * cm, "SF")
        # Título
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(MARGEN + 2 * cm, ALTO_PAGINA - 1.2 * cm, "ServiFix")
        c.setFont("Helvetica", 10)
        c.drawString(MARGEN + 2 * cm, ALTO_PAGINA - 1.75 * cm, "Orden de Servicio Técnico")
        # Código y fecha de emisión
        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(ANCHO_PAGINA - MARGEN, ALTO_PAGINA - 1.2 * cm, ticket.get("codigo", ""))
        c.setFont("Helvetica", 8.5)
        c.drawRightString(ANCHO_PAGINA - MARGEN, ALTO_PAGINA - 1.75 * cm,
                          "Emitido: " + datetime.now(COL).strftime("%d/%m/%Y %I:%M %p"))
        # Pie
        c.setStrokeColor(GRIS_LINEA)
        c.line(MARGEN, 1.4 * cm, ANCHO_PAGINA - MARGEN, 1.4 * cm)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGEN, 0.95 * cm,
                     "ServiFix · Sistema de gestión de soporte técnico · Documento generado automáticamente")
        c.drawRightString(ANCHO_PAGINA - MARGEN, 0.95 * cm, f"Página {doc.page}")
        c.restoreState()
    return dibujar


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def generar_pdf_ticket(ticket: dict) -> bytes:
    cliente = ticket.get("cliente") or {}
    contacto = cliente.get("contacto") or {}
    equipo = ticket.get("equipo") or {}
    tecnico = ticket.get("tecnico") or {}
    estado = ticket.get("estado", "")
    prioridad = ticket.get("prioridad", "")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=MARGEN, rightMargin=MARGEN,
                            topMargin=3.2 * cm, bottomMargin=2 * cm,
                            title=f"Orden {ticket.get('codigo', '')}", author="ServiFix")
    h = []

    # 1. Franja de estado -------------------------------------------------
    ancho4 = ANCHO_UTIL / 4
    franja = Table([[
        [Paragraph("ESTADO", E["etiqueta"]), Spacer(1, 3), _badge(estado, COLOR_ESTADO.get(estado, GRIS))],
        [Paragraph("PRIORIDAD", E["etiqueta"]), Spacer(1, 3),
         _badge(prioridad, COLOR_PRIORIDAD.get(prioridad, GRIS))],
        _par("Categoría", f"<b>{_txt(ticket.get('categoria'))}</b>"),
        _par("Fecha de solicitud", f"<b>{_fecha(ticket.get('created_at'))}</b>"),
    ]], colWidths=[ancho4] * 4)
    franja.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    h += [franja, Spacer(1, 12)]

    # 2. Cliente | Equipo -------------------------------------------------
    medio = (ANCHO_UTIL - 10) / 2
    es_empresa = cliente.get("tipo") == "Empresa"
    filas_cliente = [
        ("Tipo de cliente", "Empresa" if es_empresa else "Persona natural"),
        ("Empresa" if es_empresa else "Nombre", f"<b>{_txt(cliente.get('nombre'))}</b>"),
        ("NIT" if es_empresa else "Cédula", _txt(cliente.get("documento"))),
        ("Ciudad / Dirección", f"{_txt(cliente.get('ciudad'))} · {_txt(cliente.get('direccion'))}"),
    ]
    if es_empresa:
        filas_cliente.append(("Persona de contacto", _txt(contacto.get("nombre"))))
    filas_cliente.append(("Email / Teléfono", f"{_txt(contacto.get('email'))} · {_txt(contacto.get('telefono'))}"))
    t_cliente = _tarjeta("Datos del cliente", filas_cliente, medio)
    t_equipo = _tarjeta("Equipo atendido", [
        ("Equipo", f"<b>{_txt(equipo.get('nombre'))}</b>"),
        ("Tipo", _txt(equipo.get("tipo"))),
        ("Marca", _txt(equipo.get("marca"))),
        ("Serial", _txt(equipo.get("serial"))),
    ], medio)
    fila = Table([[t_cliente, "", t_equipo]], colWidths=[medio, 10, medio])
    fila.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    h += [fila, Spacer(1, 10)]

    # 3. Técnico | Resumen del servicio -----------------------------------
    especialidades = ", ".join(tecnico.get("especialidades") or []) or None
    t_tecnico = _tarjeta("Técnico asignado", [
        ("Nombre", f"<b>{_txt(tecnico.get('nombre'), 'Sin asignar')}</b>"),
        ("Email", _txt(tecnico.get("email"))),
        ("Teléfono", _txt(tecnico.get("telefono"))),
        ("Especialidades", _txt(especialidades)),
    ], medio)
    t_resumen = _tarjeta("Resumen del servicio", [
        ("Fecha de resolución", _fecha(ticket.get("resolved_at"))),
        ("Tiempo de atención", _duracion(ticket.get("created_at"), ticket.get("resolved_at"))),
        ("Última actualización", _fecha(ticket.get("updated_at"))),
        ("Registros en bitácora", str(len(ticket.get("bitacora") or []))),
    ], medio)
    fila2 = Table([[t_tecnico, "", t_resumen]], colWidths=[medio, 10, medio])
    fila2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    h += [fila2]

    # 4. Descripción ------------------------------------------------------
    titulo_desc = Paragraph("Descripción de la falla reportada", E["seccion"])
    caja = Table([[Paragraph(_txt(ticket.get("descripcion")), E["normal"])]], colWidths=[ANCHO_UTIL])
    caja.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, GRIS_LINEA),
        ("LINEBEFORE", (0, 0), (0, -1), 3, AZUL),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    h.append(KeepTogether([titulo_desc, caja]))

    if ticket.get("diagnostico_ia"):
        titulo_ia = Paragraph("Diagnóstico preliminar sugerido por IA (Google Gemini)", E["seccion"])
        caja_ia = Table([[Paragraph(_txt(ticket["diagnostico_ia"]).replace("\n", "<br/>"), E["normal"])]],
                        colWidths=[ANCHO_UTIL])
        caja_ia.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F3FF")),
            ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#7C3AED")),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        h.append(KeepTogether([titulo_ia, caja_ia]))

    # 5. Bitácora ---------------------------------------------------------
    h.append(CondPageBreak(3.5 * cm))  # si queda poco espacio, la tabla empieza en otra página
    h.append(Paragraph("Historial de la orden (bitácora)", E["seccion"]))
    filas = [[Paragraph(x, E["celda_titulo"]) for x in ("Fecha", "Estado", "Responsable", "Detalle")]]
    for b in ticket.get("bitacora") or []:
        filas.append([
            Paragraph(_fecha(b.get("fecha")), E["pequeno"]),
            Paragraph(f"<b>{_txt(b.get('estado'))}</b>", E["pequeno"]),
            Paragraph(_txt(b.get("autor")), E["pequeno"]),
            Paragraph(_txt(b.get("nota")), E["normal"]),
        ])
    bit = Table(filas, colWidths=[3.3 * cm, 2.3 * cm, 3.4 * cm, ANCHO_UTIL - 9 * cm], repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, GRIS_LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(2, len(filas), 2):
        estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))
    bit.setStyle(TableStyle(estilo))
    h.append(bit)

    usados = ticket.get("repuestos_usados") or []
    if usados:
        titulo_rep = Paragraph("Repuestos utilizados (descontados del inventario)", E["seccion"])
        filas_r = [[Paragraph(x, E["celda_titulo"]) for x in ("Código", "Repuesto", "Cant.", "Precio unit.", "Subtotal")]]
        for u in usados:
            filas_r.append([Paragraph(_txt(u.get("sku")), E["pequeno"]), Paragraph(_txt(u.get("nombre")), E["normal"]),
                            Paragraph(str(u.get("cantidad")), E["normal"]),
                            Paragraph(_dinero(u.get("precio_unitario")), E["normal"]),
                            Paragraph(f"<b>{_dinero(u.get('subtotal'))}</b>", E["normal"])])
        tab_r = Table(filas_r, colWidths=[2.8 * cm, ANCHO_UTIL - 13.3 * cm, 1.5 * cm, 4.5 * cm, 4.5 * cm], repeatRows=1)
        tab_r.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AZUL),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, GRIS_LINEA),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        h.append(KeepTogether([titulo_rep, tab_r]))

    # 6. Evidencia + total ------------------------------------------------
    titulo_evid = Paragraph("Evidencia y costo del servicio", E["seccion"])
    foto = _imagen_evidencia(ticket["foto_url"]) if ticket.get("foto_url") else None
    if foto is None:
        texto_foto = ("No fue posible cargar la imagen de evidencia." if ticket.get("foto_url")
                      else "Sin evidencia fotográfica registrada.")
        foto = Paragraph(texto_foto, E["pequeno"])

    if estado == "Cancelado":
        etiqueta_total = "Servicio cancelado"
    elif estado == "Resuelto":
        etiqueta_total = "Total del servicio"
    else:
        etiqueta_total = "Costo (pendiente de cierre)"
    derecha = ParagraphStyle("der", parent=E["normal"], alignment=TA_RIGHT)
    filas_total = []
    if estado == "Resuelto":
        filas_total += [
            [Paragraph(f"Mano de obra: <b>{_dinero(ticket.get('costo_mano_obra', ticket.get('costo')))}</b>", derecha)],
            [Paragraph(f"Repuestos: <b>{_dinero(ticket.get('costo_repuestos'))}</b>", derecha)],
        ]
    filas_total += [
        [Paragraph(etiqueta_total.upper(), ParagraphStyle("et", parent=E["etiqueta"], alignment=TA_RIGHT))],
        [Paragraph(_dinero(ticket.get("costo")), E["total"])],
    ]
    cal = ticket.get("calificacion") or {}
    if cal.get("puntaje"):
        filas_total.append([Paragraph(f"Calificación del cliente: <b>{cal['puntaje']}/5</b>", derecha)])
        filas_total.append([Estrellas(cal["puntaje"], 6.5 * cm - 20)])
        if cal.get("comentario"):
            filas_total.append([Paragraph(f"<i>“{_txt(cal['comentario'])}”</i>",
                                          ParagraphStyle("com", parent=E["pequeno"], alignment=TA_RIGHT))])
    total = Table(filas_total, colWidths=[6.5 * cm])
    total.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    bloque = Table([[foto, total]], colWidths=[ANCHO_UTIL - 6.5 * cm, 6.5 * cm])
    bloque.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    h.append(KeepTogether([titulo_evid, bloque]))

    # 7. Firmas -----------------------------------------------------------
    firma_ancho = (ANCHO_UTIL - 2 * cm) / 2
    firmas = Table([
        ["", "", ""],
        [Paragraph(f"<b>Firma del técnico</b><br/>{_txt(tecnico.get('nombre'), '')}", E["centro"]), "",
         Paragraph(f"<b>{'Firma y sello del cliente' if es_empresa else 'Firma del cliente'}</b>"
                   f"<br/>{_txt(contacto.get('nombre'), '')}", E["centro"])],
    ], colWidths=[firma_ancho, 2 * cm, firma_ancho], rowHeights=[1.6 * cm, None])
    firmas.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (0, 0), 0.8, TEXTO),
        ("LINEBELOW", (2, 0), (2, 0), 0.8, TEXTO),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
    ]))
    h += [Spacer(1, 18), KeepTogether([firmas])]

    pagina = _decorar_pagina(ticket)
    doc.build(h, onFirstPage=pagina, onLaterPages=pagina)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# REPORTE: LISTADO DE TICKETS (horizontal)
# ---------------------------------------------------------------------------
def generar_pdf_listado(lista: list, descripcion_filtros: str) -> bytes:
    from reportlab.lib.pagesizes import landscape
    ancho_p, alto_p = landscape(letter)
    util = ancho_p - 2 * MARGEN
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), leftMargin=MARGEN, rightMargin=MARGEN,
                            topMargin=3.1 * cm, bottomMargin=2 * cm, title="Reporte de tickets", author="ServiFix")

    def decorar(c, d):
        c.saveState()
        c.setFillColor(AZUL)
        c.rect(0, alto_p - 2.4 * cm, ancho_p, 2.4 * cm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.roundRect(MARGEN, alto_p - 1.95 * cm, 1.4 * cm, 1.4 * cm, 6, stroke=0, fill=1)
        c.setFillColor(AZUL)
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(MARGEN + 0.7 * cm, alto_p - 1.45 * cm, "SF")
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(MARGEN + 1.9 * cm, alto_p - 1.15 * cm, "ServiFix · Reporte de tickets")
        c.setFont("Helvetica", 9)
        c.drawString(MARGEN + 1.9 * cm, alto_p - 1.7 * cm, descripcion_filtros[:140])
        c.drawRightString(ancho_p - MARGEN, alto_p - 1.15 * cm,
                          "Generado: " + datetime.now(COL).strftime("%d/%m/%Y %I:%M %p"))
        c.setStrokeColor(GRIS_LINEA)
        c.line(MARGEN, 1.4 * cm, ancho_p - MARGEN, 1.4 * cm)
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(MARGEN, 0.95 * cm, "ServiFix · Sistema de gestión de soporte técnico")
        c.drawRightString(ancho_p - MARGEN, 0.95 * cm, f"Página {d.page}")
        c.restoreState()

    h = []
    # Tarjetas de resumen
    conteo = {e: sum(1 for t in lista if t.get("estado") == e) for e in COLOR_ESTADO}
    facturado = sum(t.get("costo") or 0 for t in lista if t.get("estado") == "Resuelto")
    celdas = [("Tickets", str(len(lista)), AZUL)] + \
             [(e, str(n), COLOR_ESTADO[e]) for e, n in conteo.items()] + \
             [("Facturado", _dinero(facturado), colors.HexColor("#059669"))]
    fila = [[Paragraph(f"<font size='7.5' color='#64748B'><b>{_txt(t).upper()}</b></font><br/>"
                       f"<font size='13' color='{c.hexval().replace('0x', '#')}'><b>{_txt(v)}</b></font>",
                       ParagraphStyle("k", parent=E["normal"], leading=17)) for t, v, c in celdas]]
    tarjetas = Table(fila, colWidths=[util / len(celdas)] * len(celdas))
    tarjetas.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO),
        ("LINEAFTER", (0, 0), (-2, -1), 1, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    h += [tarjetas, Spacer(1, 12)]

    if not lista:
        h.append(Paragraph("No hay tickets que cumplan los filtros seleccionados.", E["normal"]))
    else:
        titulos = ("Código", "Estado", "Prioridad", "Cliente", "Equipo", "Categoría", "Técnico", "Creado", "Costo")
        anchos = [2.6, 2.1, 1.8, 4.0, 3.8, 2.1, 3.0, 2.1, 0]
        anchos = [a * cm for a in anchos]
        anchos[-1] = util - sum(anchos)
        filas = [[Paragraph(x, E["celda_titulo"]) for x in titulos]]
        estilo = [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("LINEBELOW", (0, 1), (-1, -1), 0.4, GRIS_LINEA),
                  ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        chico = ParagraphStyle("ch", parent=E["normal"], fontSize=8, leading=10)
        for i, t in enumerate(lista, start=1):
            cli = t.get("cliente") or {}
            tec = (t.get("tecnico") or {}).get("nombre") or "Sin asignar"
            col_e = COLOR_ESTADO.get(t.get("estado"), GRIS).hexval().replace("0x", "#")
            col_p = COLOR_PRIORIDAD.get(t.get("prioridad"), GRIS).hexval().replace("0x", "#")
            filas.append([
                Paragraph(f"<b>{_txt(t.get('codigo'))}</b>", chico),
                Paragraph(f"<font color='{col_e}'><b>{_txt(t.get('estado'))}</b></font>", chico),
                Paragraph(f"<font color='{col_p}'><b>{_txt(t.get('prioridad'))}</b></font>", chico),
                Paragraph(_txt(cli.get("nombre")) + f"<br/><font color='#94A3B8'>{_txt(cli.get('ciudad'), '')}</font>", chico),
                Paragraph(_txt((t.get("equipo") or {}).get("nombre")), chico),
                Paragraph(_txt(t.get("categoria")), chico),
                Paragraph(_txt(tec), chico),
                Paragraph(_fecha(t.get("created_at"), con_hora=False), chico),
                Paragraph(_dinero(t.get("costo")).replace(" COP", ""),
                          ParagraphStyle("cr", parent=chico, alignment=TA_RIGHT)),
            ])
            if i % 2 == 0:
                estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))
        tabla = Table(filas, colWidths=anchos, repeatRows=1)
        tabla.setStyle(TableStyle(estilo))
        h.append(tabla)

    doc.build(h, onFirstPage=decorar, onLaterPages=decorar)
    return buffer.getvalue()
