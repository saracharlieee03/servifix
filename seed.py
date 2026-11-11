"""
seed.py
-------
Llena MongoDB Atlas con datos de ejemplo: técnicos, clientes (con equipos) y
tickets de los últimos ~5 meses, para que la app y los reportes tengan qué mostrar.

ATENCIÓN: borra los datos actuales de las colecciones de ServiFix.
Uso:  python seed.py
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from database import clientes, contadores, crear_indices, db, repuestos, tecnicos, tickets

COL = timezone(timedelta(hours=-5))
AHORA = datetime.now(timezone.utc)

TECNICOS = [
    {"nombre": "Carlos Mendoza", "email": "carlos@servifix.com", "telefono": "3104567812",
     "especialidades": ["Hardware", "Preventivo"], "activo": True},
    {"nombre": "Ana Gutiérrez", "email": "ana@servifix.com", "telefono": "3157788990",
     "especialidades": ["Software", "Redes"], "activo": True},
    {"nombre": "Roberto Gómez", "email": "roberto@servifix.com", "telefono": "3002345671",
     "especialidades": ["Hardware", "Redes"], "activo": True},
    {"nombre": "Daniela Ríos", "email": "daniela@servifix.com", "telefono": "3186655443",
     "especialidades": ["Software", "Preventivo"], "activo": True},
    {"nombre": "Jorge Patiño", "email": "jorge@servifix.com", "telefono": "3013322110",
     "especialidades": ["Redes"], "activo": False},
]


def eq(nombre, tipo, marca, serial):
    return {"equipo_id": ObjectId(), "nombre": nombre, "tipo": tipo, "marca": marca, "serial": serial}


CLIENTES = [
    {"tipo": "Empresa", "nombre": "Universidad EAFIT", "documento": "890901389-1", "ciudad": "Medellín",
     "direccion": "Carrera 49 # 7 Sur-50",
     "contacto": {"nombre": "Laura Restrepo", "email": "lrestrepo@eafit.edu.co", "telefono": "6042619500"},
     "equipos": [eq("Proyector auditorio principal", "Proyector", "Epson", "EP-4K-88123"),
                 eq("Servidor académico", "Servidor", "Dell", "DL-R740-0021"),
                 eq("Switch core bloque 19", "Red", "Cisco", "CS-9300-4471")]},
    {"tipo": "Empresa", "nombre": "Hospital San Vicente", "documento": "890900518-4", "ciudad": "Medellín",
     "direccion": "Calle 64 # 51D-154",
     "contacto": {"nombre": "Andrés Zapata", "email": "sistemas@sanvicente.org", "telefono": "6044441333"},
     "equipos": [eq("Servidor de admisiones", "Servidor", "Dell", "DL-R650-1180"),
                 eq("Monitor de signos vitales UCI", "Equipo médico", "Philips", "PH-MX450-332"),
                 eq("Impresora de etiquetas", "Impresora", "Zebra", "ZB-ZT411-908")]},
    {"tipo": "Empresa", "nombre": "Banco Nacional", "documento": "860002964-4", "ciudad": "Bogotá",
     "direccion": "Avenida Calle 26 # 69-63",
     "contacto": {"nombre": "Marcela Torres", "email": "mtorres@banconacional.co", "telefono": "6013078000"},
     "equipos": [eq("Impresora de cheques", "Impresora", "Epson", "EP-TMS9-555"),
                 eq("Firewall sede principal", "Red", "Fortinet", "FG-200F-771"),
                 eq("Estación de caja 04", "Computador", "Lenovo", "LN-M70Q-204")]},
    {"tipo": "Empresa", "nombre": "Constructora Bolívar", "documento": "860513493-1", "ciudad": "Bogotá",
     "direccion": "Calle 99 # 9A-54",
     "contacto": {"nombre": "Felipe Cárdenas", "email": "fcardenas@bolivar.com.co", "telefono": "6016015000"},
     "equipos": [eq("Plotter de planos", "Impresora", "HP", "HP-T830-6620"),
                 eq("Workstation CAD", "Computador", "HP", "HP-Z4-3301")]},
    {"tipo": "Empresa", "nombre": "Laboratorio Bioquímico del Valle", "documento": "805012345-6", "ciudad": "Cali",
     "direccion": "Avenida 6N # 23-45",
     "contacto": {"nombre": "Paola Murillo", "email": "pmurillo@labvalle.com", "telefono": "6023334455"},
     "equipos": [eq("Centrífuga industrial", "Industrial", "Thermo Fisher", "TF-SL16-4410"),
                 eq("Servidor LIMS", "Servidor", "HPE", "HPE-DL380-217"),
                 eq("Red WiFi del laboratorio", "Red", "Ubiquiti", "UB-U6P-998")]},
    {"tipo": "Empresa", "nombre": "Clínica del Caribe", "documento": "802003456-2", "ciudad": "Barranquilla",
     "direccion": "Calle 80 # 49C-65",
     "contacto": {"nombre": "Luis Pacheco", "email": "lpacheco@clinicacaribe.co", "telefono": "6053567890"},
     "equipos": [eq("Ecógrafo", "Equipo médico", "GE", "GE-LOGIQ-E10-55"),
                 eq("Computador de recepción", "Computador", "Dell", "DL-OPT7010-12"),
                 eq("Servidor historia clínica", "Servidor", "Lenovo", "LN-SR650-87")]},
    # Personas naturales (vienen a nombre propio: el contacto son ellas mismas)
    {"tipo": "Persona", "nombre": "María Fernanda López", "documento": "1036598741", "ciudad": "Medellín",
     "direccion": "Calle 10 # 43-21, El Poblado",
     "contacto": {"nombre": "María Fernanda López", "email": "mflopez@gmail.com", "telefono": "3014567890"},
     "equipos": [eq("Portátil personal", "Computador", "Lenovo", "LN-IP5-77810"),
                 eq("Impresora de la casa", "Impresora", "Epson", "EP-L3250-4410")]},
    {"tipo": "Persona", "nombre": "Juan Camilo Herrera", "documento": "80123456", "ciudad": "Bogotá",
     "direccion": "Carrera 15 # 85-30, apto 402",
     "contacto": {"nombre": "Juan Camilo Herrera", "email": "jcherrera@hotmail.com", "telefono": "3209876543"},
     "equipos": [eq("PC de escritorio", "Computador", "ASUS", "AS-ROG-5521"),
                 eq("Router de la casa", "Red", "TP-Link", "TP-AX55-118")]},
]

# (cliente, equipo, categoría, prioridad, descripción, estado, técnico, costo, días atrás,
#  horas hasta cierre, nota de cierre)
TICKETS = [
    (0, 0, "Hardware", "Alta", "El proyector parpadea al encender y se apaga después de 10 minutos de uso.",
     "Resuelto", 0, 180000, 148, 30, "Se reemplazó la lámpara y se limpiaron los filtros de ventilación."),
    (1, 0, "Software", "Crítica", "Falla en la base de datos de admisiones: no se pueden registrar pacientes.",
     "Resuelto", 3, 350000, 140, 6, "Se restauró el respaldo de la noche anterior y se reindexaron las tablas."),
    (4, 0, "Preventivo", "Media", "Mantenimiento preventivo semestral de la centrífuga.",
     "Resuelto", 0, 120000, 132, 52, "Calibración completa, cambio de escobillas y lubricación del rotor."),
    (2, 1, "Redes", "Alta", "Caídas intermitentes de la VPN entre la sede principal y las sucursales.",
     "Resuelto", 1, 420000, 120, 12, "Se actualizó el firmware del firewall y se ajustaron los túneles IPsec."),
    (3, 0, "Hardware", "Media", "El plotter mancha los planos con franjas de tinta cian.",
     "Resuelto", 2, 260000, 110, 40, "Cambio del cabezal de impresión cian y alineación de cabezales."),
    (5, 0, "Preventivo", "Baja", "Revisión preventiva trimestral del ecógrafo.",
     "Resuelto", 3, 150000, 101, 70, "Limpieza de transductores y verificación de actualizaciones de software."),
    (0, 2, "Redes", "Alta", "El bloque 19 se quedó sin red; el switch no responde.",
     "Resuelto", 2, 310000, 95, 20, "Se reemplazó la fuente de poder del switch y se restauró la configuración."),
    (1, 1, "Hardware", "Crítica", "El monitor de signos vitales de la UCI muestra lecturas erróneas de presión.",
     "Resuelto", 0, 480000, 88, 5, "Se cambió el módulo de presión no invasiva y se calibró con simulador."),
    (2, 0, "Hardware", "Media", "La impresora de cheques atasca el papel en la bandeja principal.",
     "Cancelado", 2, 0, 80, 26, "El cliente decidió reemplazar el equipo por uno nuevo en garantía."),
    (4, 1, "Software", "Alta", "El sistema LIMS no genera los reportes de resultados en PDF.",
     "Resuelto", 1, 390000, 72, 18, "Se corrigió la configuración del motor de reportes y se actualizó Java."),
    (5, 2, "Software", "Media", "El servidor de historia clínica está muy lento en horas pico.",
     "Resuelto", 3, 280000, 63, 26, "Se optimizaron consultas y se amplió la memoria asignada a la base de datos."),
    (3, 1, "Hardware", "Baja", "La workstation se reinicia sola cuando se renderizan modelos 3D.",
     "Resuelto", 0, 210000, 55, 60, "Se reemplazó la pasta térmica y un ventilador defectuoso de la GPU."),
    (1, 2, "Hardware", "Media", "La impresora de etiquetas imprime en blanco.",
     "Resuelto", 2, 95000, 47, 22, "Se cambió la cinta de transferencia térmica y se limpió el cabezal."),
    (0, 1, "Software", "Alta", "El servidor académico no levanta la plataforma de clases virtuales.",
     "Resuelto", 1, 450000, 40, 9, "Se renovó el certificado SSL vencido y se reinició el servicio web."),
    (2, 2, "Software", "Baja", "Solicitud de instalación de software contable en la caja 04.",
     "Cancelado", None, 0, 33, 30, "Solicitud duplicada: el área de TI del banco lo instaló internamente."),
    (4, 2, "Redes", "Media", "Zonas del laboratorio sin cobertura WiFi.",
     "Resuelto", 2, 175000, 26, 14, "Se reubicaron dos access points y se ajustaron los canales."),
    (5, 1, "Hardware", "Media", "El computador de recepción no enciende.",
     "Resuelto", 0, 130000, 18, 33, "Se reemplazó la fuente de poder."),
    (1, 0, "Preventivo", "Baja", "Mantenimiento preventivo del servidor de admisiones.",
     "Resuelto", 3, 160000, 12, 48, "Actualización de parches, revisión de discos y prueba de respaldos."),
    (6, 0, "Software", "Media", "El portátil está muy lento y aparecen ventanas de publicidad al navegar.",
     "Resuelto", 3, 90000, 70, 20, "Se eliminó malware, se actualizaron controladores y se optimizó el inicio."),
    (6, 1, "Hardware", "Baja", "La impresora no toma las hojas de la bandeja.",
     "Resuelto", 2, 60000, 35, 48, "Se limpiaron los rodillos de arrastre y se cambió la almohadilla separadora."),
    (7, 0, "Hardware", "Alta", "El computador se apaga solo cuando se abren programas pesados.",
     "Resuelto", 0, 240000, 22, 30, "Se cambió la fuente de poder por una de mayor capacidad y se limpió el disipador."),
    # Tickets activos (En Proceso)
    (2, 0, "Hardware", "Alta", "La nueva impresora de cheques no reconoce la tinta magnética.",
     "En Proceso", 2, 0, 4, None, None),
    (1, 1, "Hardware", "Crítica", "Alarma de batería baja permanente en el monitor de signos vitales.",
     "En Proceso", 0, 0, 2, None, None),
    (4, 1, "Software", "Media", "Error de sincronización entre el LIMS y los equipos de análisis.",
     "En Proceso", 1, 0, 3, None, None),
    (5, 2, "Software", "Alta", "El servidor de historia clínica no completa los respaldos nocturnos.",
     "En Proceso", 3, 0, 1, None, None),
    (3, 1, "Preventivo", "Media", "Mantenimiento preventivo anual de la workstation CAD.",
     "En Proceso", 0, 0, 2, None, None),
    # Tickets abiertos (sin técnico)
    (3, 0, "Hardware", "Media", "El plotter muestra el error 01:10 en el cartucho de tinta.",
     "Abierto", None, 0, 4, None, None),
    (2, 1, "Redes", "Crítica", "El firewall reporta uso de CPU al 100 % y lentitud general.",
     "Abierto", None, 0, 3, None, None),
    (0, 0, "Preventivo", "Baja", "Limpieza y revisión preventiva del proyector del auditorio.",
     "Abierto", None, 0, 0.2, None, None),
    (7, 1, "Redes", "Media", "El WiFi de la casa se desconecta varias veces al día.",
     "Abierto", None, 0, 1, None, None),
]


# Inventario: (sku, nombre, categoría, precio, stock FINAL después de los usos, stock mínimo)
REPUESTOS = [
    ("LMP-EPS-4K", "Lámpara para proyector Epson", "Componentes", 150000, 2, 1),
    ("FLT-AIRE", "Filtro de aire universal", "Consumibles", 15000, 14, 4),
    ("FTE-500W", "Fuente de poder 500W", "Componentes", 180000, 2, 3),
    ("FTE-750W", "Fuente de poder 750W", "Componentes", 260000, 3, 1),
    ("PASTA-TER", "Pasta térmica (jeringa)", "Consumibles", 18000, 9, 3),
    ("VENT-GPU", "Ventilador para tarjeta gráfica", "Componentes", 65000, 4, 2),
    ("CAB-HP-CIAN", "Cabezal de impresión HP cian", "Consumibles", 190000, 0, 1),
    ("CINTA-ZEB", "Cinta de transferencia Zebra", "Consumibles", 45000, 6, 4),
    ("MOD-PNI", "Módulo de presión no invasiva Philips", "Equipo médico", 320000, 1, 1),
    ("FTE-SW-CIS", "Fuente para switch Cisco", "Redes", 210000, 2, 1),
    ("RODILLO-EPS", "Kit de rodillos para impresora Epson", "Consumibles", 35000, 5, 2),
    ("AP-U6", "Access point Ubiquiti U6", "Redes", 520000, 3, 1),
    ("RAM-16GB", "Memoria RAM 16GB DDR4", "Componentes", 160000, 6, 2),
    ("SSD-1TB", "Disco SSD 1TB", "Componentes", 290000, 4, 2),
]

# Repuestos usados en tickets resueltos (se identifica el ticket por un texto de su descripción)
USOS = {
    "proyector parpadea": [("LMP-EPS-4K", 1), ("FLT-AIRE", 1)],
    "franjas de tinta cian": [("CAB-HP-CIAN", 1)],
    "switch no responde": [("FTE-SW-CIS", 1)],
    "lecturas erróneas de presión": [("MOD-PNI", 1)],
    "muy lento en horas pico": [("RAM-16GB", 2)],
    "se reinicia sola": [("PASTA-TER", 1), ("VENT-GPU", 1)],
    "imprime en blanco": [("CINTA-ZEB", 2)],
    "recepción no enciende": [("FTE-500W", 1)],
    "no toma las hojas": [("RODILLO-EPS", 1)],
    "se apaga solo cuando": [("FTE-750W", 1), ("PASTA-TER", 1)],
}

# Encuestas del portal del cliente (se asignan en orden a los tickets resueltos; None = no calificó)
ENCUESTAS = [
    (5, "Excelente servicio, el proyector quedó como nuevo."), (5, "Muy rápidos, salvaron el día."),
    (4, "Buen trabajo, aunque tardaron un poco en llegar."), (5, None), (3, "Resolvieron, pero tuve que llamar dos veces."),
    None, (5, "El técnico explicó todo muy claro."), (4, None), (5, "Atención impecable."),
    (4, "Todo bien, el precio fue justo."), None, (5, "Súper recomendados."), (2, "Demoraron más de lo prometido."),
    (5, "Rápido y amable."), (4, "Buen servicio."), (5, None),
]


def poblar():
    print(f"Base de datos: {db.name}")
    print("Limpiando colecciones…")
    # drop_collection borra también los índices viejos (ej: el de "nit" de la versión anterior)
    for nombre in ("clientes", "tecnicos", "tickets", "contadores", "repuestos", "users"):
        db.drop_collection(nombre)

    for t in TECNICOS:
        t["created_at"] = AHORA - timedelta(days=200)
    tec_ids = tecnicos.insert_many(TECNICOS).inserted_ids
    print(f"✅ {len(tec_ids)} técnicos")

    for c in CLIENTES:
        c["created_at"] = AHORA - timedelta(days=190)
    cli_ids = clientes.insert_many(CLIENTES).inserted_ids
    n_emp = sum(1 for c in CLIENTES if c["tipo"] == "Empresa")
    print(f"✅ {len(cli_ids)} clientes ({n_emp} empresas, {len(cli_ids) - n_emp} personas) con {sum(len(c['equipos']) for c in CLIENTES)} equipos embebidos")

    precios = {r[0]: r for r in REPUESTOS}
    rep_ids = {r[0]: ObjectId() for r in REPUESTOS}
    salidas = []          # (sku, cantidad, fecha, código del ticket)
    encuestas = iter(ENCUESTAS)

    docs = []
    por_anio = Counter()
    # Se ordenan del más antiguo al más reciente para que los códigos sigan el orden de creación
    for (ci, ei, cat, pri, desc, estado, ti, costo, dias, horas, nota) in sorted(TICKETS, key=lambda x: -x[8]):
        cliente = CLIENTES[ci]
        equipo = cliente["equipos"][ei]
        creado = (AHORA - timedelta(days=dias)).replace(microsecond=0)
        anio = creado.astimezone(COL).year
        por_anio[anio] += 1
        tec = TECNICOS[ti] if ti is not None else None

        bitacora = [{"fecha": creado, "nota": "Solicitud registrada.",
                     "autor": cliente["contacto"]["nombre"], "estado": "Abierto"}]
        if tec:
            asignado = creado + timedelta(hours=1.5)
            bitacora.append({"fecha": asignado, "nota": f"Asignado al técnico {tec['nombre']}.",
                             "autor": "Coordinador", "estado": "En Proceso"})
            if estado == "En Proceso":
                bitacora.append({"fecha": asignado + timedelta(hours=3),
                                 "nota": "Diagnóstico inicial realizado; se programó visita técnica.",
                                 "autor": tec["nombre"], "estado": "En Proceso"})
        codigo = f"TCK-{anio}-{por_anio[anio]:04d}"
        cerrado = creado + timedelta(hours=horas) if horas else None
        usados = []
        if estado == "Resuelto":
            for clave, lista in USOS.items():
                if clave in desc:
                    for sku, cant in lista:
                        precio = precios[sku][3]
                        usados.append({"repuesto_id": rep_ids[sku], "sku": sku, "nombre": precios[sku][1],
                                       "cantidad": cant, "precio_unitario": float(precio),
                                       "subtotal": float(precio * cant)})
                        salidas.append((sku, cant, cerrado, codigo))
        costo_rep = sum(u["subtotal"] for u in usados)
        if estado in ("Resuelto", "Cancelado"):
            texto = f"{estado}: {nota}"
            if usados:
                texto += " | Repuestos: " + ", ".join(f"{u['cantidad']}x {u['nombre']}" for u in usados)
            bitacora.append({"fecha": cerrado, "nota": texto,
                             "autor": tec["nombre"] if tec else "Coordinador", "estado": estado})
        calificacion = None
        if estado == "Resuelto":
            enc = next(encuestas, None)
            if enc:
                fecha_cal = min(cerrado + timedelta(hours=20), AHORA - timedelta(minutes=5))
                calificacion = {"puntaje": enc[0], "comentario": enc[1], "fecha": fecha_cal}
                bitacora.append({"fecha": fecha_cal, "nota": f"El cliente calificó el servicio con {enc[0]}/5.",
                                 "autor": cliente["contacto"]["nombre"], "estado": "Resuelto"})

        docs.append({
            "codigo": codigo,
            "cliente_id": cli_ids[ci],
            "equipo": {k: equipo[k] for k in ("equipo_id", "nombre", "tipo", "marca", "serial")},
            "categoria": cat,
            "prioridad": pri,
            "descripcion": desc,
            "estado": estado,
            "tecnico_id": tec_ids[ti] if ti is not None else None,
            "costo": float(costo) + costo_rep,          # total = mano de obra + repuestos
            "costo_mano_obra": float(costo),
            "costo_repuestos": costo_rep,
            "repuestos_usados": usados,
            "calificacion": calificacion,
            "diagnostico_ia": None,
            "foto_url": ("https://res.cloudinary.com/demo/image/upload/sample.jpg"
                         if estado == "Resuelto" and dias == 148 else None),
            "created_at": creado,
            "updated_at": bitacora[-1]["fecha"],
            "resolved_at": cerrado if estado == "Resuelto" else None,
            "bitacora": bitacora,
        })

    tickets.insert_many(docs)

    # Inventario: stock inicial = stock final + lo que se usó; movimientos embebidos en orden
    inicio = AHORA - timedelta(days=180)
    rep_docs = []
    for sku, nombre, cat, precio, final, minimo in REPUESTOS:
        usos = sorted([x for x in salidas if x[0] == sku], key=lambda x: x[2])
        inicial = final + sum(x[1] for x in usos)
        movimientos = [{"fecha": inicio, "tipo": "Entrada", "cantidad": inicial, "referencia": "Inventario inicial"}]
        movimientos += [{"fecha": f, "tipo": "Salida", "cantidad": c, "referencia": f"Ticket {cod}"}
                        for _, c, f, cod in usos]
        rep_docs.append({"_id": rep_ids[sku], "sku": sku, "nombre": nombre, "categoria": cat,
                         "precio_unitario": float(precio), "stock": final, "stock_minimo": minimo,
                         "created_at": inicio, "movimientos": movimientos})
    repuestos.insert_many(rep_docs)
    bajos = sum(1 for r in rep_docs if r["stock"] <= r["stock_minimo"])
    print(f"✅ {len(rep_docs)} repuestos en inventario ({bajos} con stock bajo, {len(salidas)} usos en tickets)")
    for anio, n in por_anio.items():
        contadores.insert_one({"_id": f"tickets-{anio}", "secuencia": n})
    n_cal = sum(1 for d in docs if d["calificacion"])
    print(f"✅ {len(docs)} tickets ({n_cal} calificados por el cliente)")

    crear_indices()
    print("✅ Índices creados. ¡Listo!")


if __name__ == "__main__":
    poblar()
