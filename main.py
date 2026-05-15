import os
import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(
    page_title="Análisis Financiero COMASUR",
    layout="wide",
    page_icon="📊"
)

# =========================
# CONFIGURACIÓN
# =========================

MESES_ES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12
}

# =========================
# FUNCIONES DE EXTRACCIÓN
# =========================

def convertir_a_float(valor_str):
    """Convierte string monetario español a float"""
    try:
        if isinstance(valor_str, (int, float)):
            return float(valor_str)
        valor_limpio = str(valor_str).strip().replace(".", "").replace(",", ".")
        return float(valor_limpio)
    except:
        return 0.0


def extraer_metadatos_pdf(pdf_file):
    """
    Extrae centro, empresa y año del PDF de COMASUR.

    Patrones reales del PDF:
      - Empresa:  "EMPRESA : 360 SUMINISTROS INDUSTRIALES COMASUR SA"
                  "EMPRESA : <nombre>"
      - Centro:   "Del Centro COMASUR MOTRIL Desde el Centro ..."
                  "Del Centro <nombre> Desde..."
      - Año:      "Hasta DICIEMBRE del ejercicio 2025"
                  cualquier año 20XX en cabecera
    """
    empresa = ""
    centro = ""
    anyo = ""

    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages[:5]:
            texto = pagina.extract_text()
            if not texto:
                continue

            for linea in texto.split("\n"):
                s = linea.strip()

                # ── Año ────────────────────────────────────────────────────
                # "Hasta DICIEMBRE del ejercicio 2025"
                if not anyo:
                    m = re.search(r"ejercicio\s+(20\d{2})", s, re.IGNORECASE)
                    if m:
                        anyo = m.group(1)
                if not anyo:
                    m = re.search(r"\b(20\d{2})\b", s)
                    if m:
                        anyo = m.group(1)

                # ── Centro ─────────────────────────────────────────────────
                # Formato real: "Del Centro COMASUR MOTRIL Desde el Centro ..."
                if not centro:
                    m = re.search(
                        r"Del\s+Centro\s+(.+?)\s+Desde\s+el\s+Centro",
                        s, re.IGNORECASE
                    )
                    if m:
                        centro = m.group(1).strip()

                # Fallback: "Filtro : EMPRESA : xxx   Del Centro COMASUR MOTRIL"
                if not centro:
                    m = re.search(r"Del\s+Centro\s+([A-Z0-9ÁÉÍÓÚÑa-záéíóúñ\s\-\.]+?)(?:\s{2,}|$|Desde)",
                                  s, re.IGNORECASE)
                    if m:
                        centro = m.group(1).strip()

                # ── Empresa ────────────────────────────────────────────────
                # Formato real: "EMPRESA : 360 SUMINISTROS INDUSTRIALES COMASUR SA"
                if not empresa:
                    m = re.search(r"EMPRESA\s*:\s*(.+)", s, re.IGNORECASE)
                    if m:
                        candidato = m.group(1).strip()
                        # Evitar capturar el filtro de cabecera completo (demasiado largo)
                        if len(candidato) < 80:
                            empresa = candidato

                # Fallback empresa: "Filtro : EMPRESA : 360 SUMINISTROS ..."
                if not empresa:
                    m = re.search(r"Filtro\s*:.*?EMPRESA\s*:\s*([A-Z0-9ÁÉÍÓÚÑa-z\s\.\-]+?)(?:\s{2,}|$)",
                                  s, re.IGNORECASE)
                    if m:
                        empresa = m.group(1).strip()

    return {
        "empresa": empresa if empresa else "COMASUR",
        "centro":  centro  if centro  else "No detectado",
        "anyo":    anyo    if anyo    else str(datetime.now().year),
    }


def extraer_datos_por_mes(pdf_file):
    """
    Extrae datos agregados por mes del PDF de COMASUR.
    Columnas exactas del PDF original:
      Base C.C. | Base C.P. | Retribuciones | Costes trabajador |
      Valor Especie | Deducción | Costes Empresa | Base IRPF |
      Retención IRPF | Otras Retenciones | Líquido
    Más columnas calculadas: Empleados, Nóm.Ord, Nóm.Ext
    """
    datos_meses = {}
    mes_actual = None

    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if not texto:
                continue

            lineas = texto.split("\n")

            for linea in lineas:
                # ── Detectar mes ──────────────────────────────────────────
                if "Mes :" in linea:
                    mes_match = re.search(r"Mes\s*:\s*(\w+)", linea)
                    if mes_match:
                        mes_nombre = mes_match.group(1).upper()
                        if mes_nombre in MESES_ES:
                            mes_actual = mes_nombre
                            if mes_actual not in datos_meses:
                                datos_meses[mes_actual] = {
                                    "empleados": set(),
                                    "nominas_ordinarias": 0,
                                    "nominas_extraordinarias": 0,
                                    # Columnas exactas del PDF (orden original):
                                    "base_cc": 0.0,            # [0]
                                    "base_cp": 0.0,            # [1]
                                    "retribuciones": 0.0,      # [2]
                                    "deduccion_ss_trab": 0.0,  # [3] Costes trabajador
                                    "valor_especie": 0.0,      # [4]
                                    "deduccion_adicional": 0.0,# [5] Deducción
                                    "coste_ss_empresa": 0.0,   # [6] Costes Empresa
                                    "base_irpf": 0.0,          # [7] Base IRPF
                                    "retencion_irpf": 0.0,     # [8]
                                    "otras_retenciones": 0.0,  # [9]
                                    "liquido": 0.0,            # [10]
                                    # Calculada:
                                    "retribuciones_ordinarias": 0.0,
                                    "retribuciones_extraordinarias": 0.0,
                                }

                # ── Línea de totales de cuenta ────────────────────────────
                # Formato: "Total de la Cuenta XXXXXXXX NombreCentro (Mes) n1 n2 ... n11"
                if mes_actual and "Total de la Cuenta" in linea:
                    numeros = re.findall(r"[\d\.]+,\d{2}", linea)

                    if len(numeros) >= 11:
                        try:
                            d = datos_meses[mes_actual]
                            d["base_cc"]            = convertir_a_float(numeros[0])
                            d["base_cp"]            = convertir_a_float(numeros[1])
                            d["retribuciones"]      = convertir_a_float(numeros[2])
                            d["deduccion_ss_trab"]  = convertir_a_float(numeros[3])
                            d["valor_especie"]      = convertir_a_float(numeros[4])
                            d["deduccion_adicional"]= convertir_a_float(numeros[5])
                            d["coste_ss_empresa"]   = convertir_a_float(numeros[6])
                            d["base_irpf"]          = convertir_a_float(numeros[7])  # ← CORREGIDO (era [2])
                            d["retencion_irpf"]     = convertir_a_float(numeros[8])
                            d["otras_retenciones"]  = convertir_a_float(numeros[9])
                            d["liquido"]            = convertir_a_float(numeros[10])
                        except Exception:
                            continue

                # ── Contar empleados y clasificar nóminas ─────────────────
                if mes_actual and re.match(r"^\d+\s+[A-Z]", linea):
                    codigo_match = re.match(r"^(\d+)\s+", linea)
                    if codigo_match:
                        codigo = codigo_match.group(1)
                        datos_meses[mes_actual]["empleados"].add(codigo)

                        nums_linea = re.findall(r"[\d\.]+,\d{2}", linea)
                        if " Ord " in linea:
                            datos_meses[mes_actual]["nominas_ordinarias"] += 1
                            if len(nums_linea) >= 3:
                                datos_meses[mes_actual]["retribuciones_ordinarias"] += convertir_a_float(nums_linea[2])
                        elif " Ext " in linea:
                            datos_meses[mes_actual]["nominas_extraordinarias"] += 1
                            if len(nums_linea) >= 3:
                                datos_meses[mes_actual]["retribuciones_extraordinarias"] += convertir_a_float(nums_linea[2])

    # Convertir sets a conteos
    for mes in datos_meses:
        datos_meses[mes]["empleados"] = len(datos_meses[mes]["empleados"])

    return datos_meses


def calcular_coste_total(d):
    """Coste total empresa = Retribuciones + Costes SS Empresa"""
    return d["retribuciones"] + d["coste_ss_empresa"]


def calcular_kpis_mes(d):
    """KPIs para un mes"""
    if d["empleados"] == 0:
        return {}
    coste_total = calcular_coste_total(d)
    retrib = d["retribuciones"]
    return {
        "salario_medio":       retrib / d["empleados"],
        "coste_medio":         coste_total / d["empleados"],
        "ratio_ss_trab":       (d["deduccion_ss_trab"] / retrib * 100) if retrib > 0 else 0,
        "ratio_ss_empresa":    (d["coste_ss_empresa"]  / retrib * 100) if retrib > 0 else 0,
        "ratio_irpf":          (d["retencion_irpf"]    / retrib * 100) if retrib > 0 else 0,
        "ratio_liquido":       (d["liquido"]            / retrib * 100) if retrib > 0 else 0,
        "coste_total":         coste_total,
    }


# =========================
# GENERACIÓN PDF (1 FOLIO)
# =========================

def generar_pdf_ejecutivo(datos_meses, empresa="COMASUR", centro="", anyo="", logo_path=None):
    """
    Genera PDF en A4 apaisado (landscape).
    Todo en un solo folio: cabecera + tabla con columnas exactas del PDF + KPIs.
    Columnas exactas PDF: Base C.C. | Base C.P. | Retribuciones | Costes trab. |
                          Val. Esp. | Deducción | Costes Emp. | Base IRPF |
                          Ret. IRPF | Otras Ret. | Líquido
    Columnas informativas: Mes | Emp. | Ord | Ext
    Columna calculada: Coste Total
    """
    buffer = BytesIO()
    # ── A4 landscape: 841.9 x 595.3 pt, márgenes ajustados ──
    PAGE = landscape(A4)
    doc = SimpleDocTemplate(
        buffer, pagesize=PAGE,
        rightMargin=18, leftMargin=18,
        topMargin=18, bottomMargin=18
    )
    elementos = []
    estilos = getSampleStyleSheet()

    estilo_cabecera = ParagraphStyle(
        'Cabecera', parent=estilos['Normal'],
        fontSize=9, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#003366'),
        alignment=TA_LEFT, spaceAfter=2
    )
    estilo_subcab = ParagraphStyle(
        'SubCab', parent=estilos['Normal'],
        fontSize=7, fontName='Helvetica',
        textColor=colors.HexColor('#444444'),
        alignment=TA_LEFT, spaceAfter=6
    )
    estilo_leyenda = ParagraphStyle(
        'Leyenda', parent=estilos['Normal'],
        fontSize=5.5, textColor=colors.grey,
        alignment=TA_LEFT
    )

    meses_ordenados = sorted(datos_meses.keys(), key=lambda x: MESES_ES[x])
    periodo = ", ".join(m.capitalize() for m in meses_ordenados)
    fecha_gen = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ── CABECERA: LOGO + TÍTULO ────────────────────────────────────────────
    titulo_txt = f"INFORME LABORAL Y FINANCIERO"
    subtitulo_txt = empresa
    if centro:
        subtitulo_txt += f"  |  Centro: {centro}"
    if anyo:
        subtitulo_txt += f"  |  Año: {anyo}"
    meta_txt = (
        f"Período: {periodo}   ·   Generado: {fecha_gen}   ·   "
        "RGPD Compliant — datos agregados sin información personal"
    )

    # Celda izquierda: logo (si existe) o celda vacía
    LOGO_H = 52  # altura del logo en pt (mantenemos proporción 1:1)
    if logo_path and os.path.exists(logo_path):
        celda_logo = RLImage(logo_path, width=LOGO_H, height=LOGO_H)
    else:
        celda_logo = Paragraph("", estilos['Normal'])

    # Celda derecha: título + subtítulo + meta
    estilo_titulo_cab = ParagraphStyle(
        'TituloCab', parent=estilos['Normal'],
        fontSize=11, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#003366'),
        spaceAfter=2
    )
    estilo_sub_cab = ParagraphStyle(
        'SubCab2', parent=estilos['Normal'],
        fontSize=8, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#CC6600'),
        spaceAfter=2
    )
    estilo_meta_cab = ParagraphStyle(
        'MetaCab', parent=estilos['Normal'],
        fontSize=6.5, fontName='Helvetica',
        textColor=colors.HexColor('#555555'),
    )

    celda_texto = [
        Paragraph(titulo_txt, estilo_titulo_cab),
        Paragraph(subtitulo_txt, estilo_sub_cab),
        Paragraph(meta_txt, estilo_meta_cab),
    ]

    # Tabla de 1 fila, 2 columnas: [logo | texto]
    tabla_cab = Table(
        [[celda_logo, celda_texto]],
        colWidths=[LOGO_H + 8, 805 - LOGO_H - 8],
        rowHeights=[LOGO_H + 4]
    )
    tabla_cab.setStyle(TableStyle([
        ("VALIGN",   (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 6),
        ("LEFTPADDING",  (1, 0), (1, 0), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor('#003366')),
    ]))
    elementos.append(tabla_cab)
    elementos.append(Spacer(1, 5))

    # ── TABLA PRINCIPAL ───────────────────────────────────────────────────
    # Cabecera con nombres EXACTOS del PDF original
    cabecera = [
        "Mes", "Emp.", "Ord", "Ext",
        "Base\nC.C.", "Base\nC.P.", "Retribuciones", "Costes\nTrab.",
        "Val.\nEspecie", "Deducción", "Costes\nEmpresa", "Base\nIRPF",
        "Ret.\nIRPF", "Otras\nRet.", "Líquido",
        "Coste\nTotal"
    ]
    datos_tabla = [cabecera]

    # Acumuladores para totales
    tots = {k: 0.0 for k in [
        "empleados", "nominas_ordinarias", "nominas_extraordinarias",
        "base_cc", "base_cp", "retribuciones", "deduccion_ss_trab",
        "valor_especie", "deduccion_adicional", "coste_ss_empresa",
        "base_irpf", "retencion_irpf", "otras_retenciones", "liquido"
    ]}

    for mes in meses_ordenados:
        d = datos_meses[mes]
        coste_total = calcular_coste_total(d)
        datos_tabla.append([
            mes[:3].capitalize(),
            str(d["empleados"]),
            str(d["nominas_ordinarias"]),
            str(d["nominas_extraordinarias"]),
            f"{d['base_cc']:,.2f}",
            f"{d['base_cp']:,.2f}",
            f"{d['retribuciones']:,.2f}",
            f"{d['deduccion_ss_trab']:,.2f}",
            f"{d['valor_especie']:,.2f}",
            f"{d['deduccion_adicional']:,.2f}",
            f"{d['coste_ss_empresa']:,.2f}",
            f"{d['base_irpf']:,.2f}",
            f"{d['retencion_irpf']:,.2f}",
            f"{d['otras_retenciones']:,.2f}",
            f"{d['liquido']:,.2f}",
            f"{coste_total:,.2f}",
        ])
        # Acumular
        for k in tots:
            tots[k] += d.get(k, 0.0) if k not in ("empleados",) else d["empleados"]

    # Fila de totales
    prom_emp = tots["empleados"] // len(datos_meses)
    datos_tabla.append([
        "TOTAL",
        str(prom_emp),
        str(int(tots["nominas_ordinarias"])),
        str(int(tots["nominas_extraordinarias"])),
        f"{tots['base_cc']:,.2f}",
        f"{tots['base_cp']:,.2f}",
        f"{tots['retribuciones']:,.2f}",
        f"{tots['deduccion_ss_trab']:,.2f}",
        f"{tots['valor_especie']:,.2f}",
        f"{tots['deduccion_adicional']:,.2f}",
        f"{tots['coste_ss_empresa']:,.2f}",
        f"{tots['base_irpf']:,.2f}",
        f"{tots['retencion_irpf']:,.2f}",
        f"{tots['otras_retenciones']:,.2f}",
        f"{tots['liquido']:,.2f}",
        f"{tots['retribuciones'] + tots['coste_ss_empresa']:,.2f}",
    ])

    # Anchuras: espacio disponible = 841 - 18 - 18 = 805 pt → 16 columnas
    col_widths = [
        30,   # Mes
        22,   # Emp.
        20,   # Ord
        20,   # Ext
        46,   # Base C.C.
        46,   # Base C.P.
        55,   # Retribuciones
        46,   # Costes Trab.
        38,   # Val. Especie
        42,   # Deducción
        48,   # Costes Empresa
        46,   # Base IRPF
        42,   # Ret. IRPF
        40,   # Otras Ret.
        52,   # Líquido
        52,   # Coste Total
    ]
    # Suma = 645 pt → hay margen (160 pt libres)
    # Los estiramos proporcionalmente para rellenar los 805 disponibles
    total_w = sum(col_widths)
    disponible = 805
    col_widths = [round(w * disponible / total_w, 1) for w in col_widths]

    tabla = Table(datos_tabla, colWidths=col_widths, repeatRows=1)
    num_filas = len(datos_tabla)

    tabla.setStyle(TableStyle([
        # Encabezado
        ("BACKGROUND",   (0, 0), (-1, 0),    colors.HexColor('#003366')),
        ("TEXTCOLOR",    (0, 0), (-1, 0),    colors.white),
        ("FONTNAME",     (0, 0), (-1, 0),    "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0),    5.8),
        ("ALIGN",        (0, 0), (-1, 0),    "CENTER"),
        ("VALIGN",       (0, 0), (-1, 0),    "MIDDLE"),
        ("ROWHEIGHT",    (0, 0), (0, 0),     22),

        # Datos
        ("FONTSIZE",     (0, 1), (-1, -2),   5.5),
        ("FONTNAME",     (0, 1), (-1, -2),   "Helvetica"),
        ("ALIGN",        (1, 1), (-1, -2),   "RIGHT"),
        ("ALIGN",        (0, 1), (0, -1),    "CENTER"),
        ("VALIGN",       (0, 1), (-1, -1),   "MIDDLE"),
        ("PADDING",      (0, 0), (-1, -1),   2.5),

        # Fila totales
        ("BACKGROUND",   (0, -1), (-1, -1),  colors.HexColor('#CCE5FF')),
        ("FONTNAME",     (0, -1), (-1, -1),  "Helvetica-Bold"),
        ("FONTSIZE",     (0, -1), (-1, -1),  6),
        ("ALIGN",        (1, -1), (-1, -1),  "RIGHT"),

        # Alternado filas
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor('#F5F8FF')]),

        # Columnas destacadas
        ("BACKGROUND",   (6,  1), (6,  -2),  colors.HexColor('#FFFDE7')),  # Retribuciones
        ("BACKGROUND",   (14, 1), (14, -2),  colors.HexColor('#E8F5E9')),  # Líquido
        ("BACKGROUND",   (15, 1), (15, -2),  colors.HexColor('#FFEBEE')),  # Coste Total

        # Separadores verticales entre grupos
        ("LINEAFTER",    (3, 0),  (3, -1),   0.75, colors.HexColor('#888888')),   # Tras Ext
        ("LINEAFTER",    (5, 0),  (5, -1),   0.75, colors.HexColor('#888888')),   # Tras Base C.P.
        ("LINEAFTER",    (10, 0), (10, -1),  0.75, colors.HexColor('#888888')),   # Tras Costes Empresa
        ("LINEAFTER",    (14, 0), (14, -1),  0.75, colors.HexColor('#888888')),   # Tras Líquido

        # Bordes
        ("BOX",          (0, 0),  (-1, -1),  1,    colors.black),
        ("INNERGRID",    (0, 0),  (-1, -1),  0.25, colors.lightgrey),
    ]))

    elementos.append(tabla)
    elementos.append(Spacer(1, 6))

    # ── KPIs INLINE (debajo de la tabla, en la misma hoja) ────────────────
    total_retrib = tots["retribuciones"]
    total_emp_sum = tots["empleados"]
    total_ss_emp  = tots["coste_ss_empresa"]
    total_irpf    = tots["retencion_irpf"]
    total_ss_trab = tots["deduccion_ss_trab"]
    total_liq     = tots["liquido"]
    coste_periodo = total_retrib + total_ss_emp
    sal_medio = total_retrib / total_emp_sum if total_emp_sum > 0 else 0
    coste_med = coste_periodo / total_emp_sum if total_emp_sum > 0 else 0

    kpi_data = [
        ["Indicador", "Valor", "Indicador", "Valor", "Indicador", "Valor"],
        [
            "Empleados Prom./Mes",    str(prom_emp),
            "Salario Medio Mensual",  f"{sal_medio:,.2f} EUR",
            "Coste Medio/Empleado",   f"{coste_med:,.2f} EUR",
        ],
        [
            "% SS Trabajador",        f"{(total_ss_trab/total_retrib*100):.2f}%" if total_retrib else "N/A",
            "% SS Empresa",           f"{(total_ss_emp/total_retrib*100):.2f}%"  if total_retrib else "N/A",
            "% IRPF sobre Retrib.",   f"{(total_irpf/total_retrib*100):.2f}%"   if total_retrib else "N/A",
        ],
        [
            "% Líquido sobre Retrib.",f"{(total_liq/total_retrib*100):.2f}%"   if total_retrib else "N/A",
            "Total Nóm. Ordinarias",  str(int(tots["nominas_ordinarias"])),
            "Total Nóm. Extraordin.", str(int(tots["nominas_extraordinarias"])),
        ],
    ]

    kpi_col_w = [disponible / 6] * 6
    tabla_kpis = Table(kpi_data, colWidths=kpi_col_w)
    tabla_kpis.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),   colors.HexColor('#CC6600')),
        ("TEXTCOLOR",   (0, 0), (-1, 0),   colors.white),
        ("FONTNAME",    (0, 0), (-1, 0),   "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1),  7),
        ("FONTNAME",    (0, 1), (-2, -1),  "Helvetica-Bold"),  # labels
        ("FONTNAME",    (1, 1), (-1, -1),  "Helvetica"),       # valores
        ("ALIGN",       (1, 1), (-1, -1),  "RIGHT"),
        ("ALIGN",       (0, 0), (-1, 0),   "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1),  "MIDDLE"),
        ("PADDING",     (0, 0), (-1, -1),  4),
        ("GRID",        (0, 0), (-1, -1),  0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor('#FFF8F0'), colors.HexColor('#FFFFFF')]),
    ]))

    elementos.append(tabla_kpis)
    elementos.append(Spacer(1, 5))

    # ── LEYENDA PIE ───────────────────────────────────────────────────────
    leyenda_txt = (
        "<b>Leyenda (nombres exactos del PDF original):</b>  "
        "Base C.C. = Base Cotiz. Contingencias Comunes  |  "
        "Base C.P. = Base Cotiz. Contingencias Profesionales  |  "
        "Retribuciones = Salario bruto  |  "
        "Costes Trab. = Cuota SS trabajador  |  "
        "Val. Especie = Retrib. no dineraria  |  "
        "Deducción = Anticipos/embargos  |  "
        "Costes Empresa = Cuota SS empresa  |  "
        "Base IRPF = Base imponible retención  |  "
        "Ret. IRPF = Retención fiscal  |  "
        "Otras Ret. = Otros descuentos  |  "
        "Coste Total = Retribuciones + Costes Empresa (calculado)"
    )
    elementos.append(Paragraph(leyenda_txt, estilo_leyenda))

    doc.build(elementos)
    buffer.seek(0)
    return buffer


# =========================
# GENERACIÓN CSV
# =========================

def generar_csv(datos_meses):
    """CSV técnico completo con separador ; para Excel español"""
    meses_ordenados = sorted(datos_meses.keys(), key=lambda x: MESES_ES[x])
    rows = []
    for mes in meses_ordenados:
        d = datos_meses[mes]
        kpis = calcular_kpis_mes(d)
        coste_total = calcular_coste_total(d)
        rows.append({
            "Mes": mes,
            "Numero_Mes": MESES_ES[mes],
            "Empleados": d["empleados"],
            "Nominas_Ordinarias": d["nominas_ordinarias"],
            "Nominas_Extraordinarias": d["nominas_extraordinarias"],
            "Base_CC": round(d["base_cc"], 2),
            "Base_CP": round(d["base_cp"], 2),
            "Retribuciones": round(d["retribuciones"], 2),
            "Retribuciones_Ordinarias": round(d["retribuciones_ordinarias"], 2),
            "Retribuciones_Extraordinarias": round(d["retribuciones_extraordinarias"], 2),
            "Costes_Trabajador_SS": round(d["deduccion_ss_trab"], 2),
            "Valor_Especie": round(d["valor_especie"], 2),
            "Deduccion_Adicional": round(d["deduccion_adicional"], 2),
            "Costes_Empresa_SS": round(d["coste_ss_empresa"], 2),
            "Base_IRPF": round(d["base_irpf"], 2),
            "Retencion_IRPF": round(d["retencion_irpf"], 2),
            "Otras_Retenciones": round(d["otras_retenciones"], 2),
            "Liquido": round(d["liquido"], 2),
            "Coste_Total_Empresa": round(coste_total, 2),
            "Salario_Medio": round(kpis.get("salario_medio", 0), 2),
            "Coste_Medio_Empleado": round(kpis.get("coste_medio", 0), 2),
            "Pct_SS_Trabajador": round(kpis.get("ratio_ss_trab", 0), 2),
            "Pct_SS_Empresa": round(kpis.get("ratio_ss_empresa", 0), 2),
            "Pct_IRPF": round(kpis.get("ratio_irpf", 0), 2),
            "Pct_Liquido": round(kpis.get("ratio_liquido", 0), 2),
        })
    return pd.DataFrame(rows)


# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

st.title("📊 Análisis Laboral y Financiero Profesional")
st.caption("🔒 Sistema anonimizado — Cumplimiento RGPD | ✅ Apto para asesoría laboral")

st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    st.info("**✅ SIN datos personales**\n- No almacena nombres\n- No almacena apellidos\n- Solo datos agregados")
with col2:
    st.success("**📋 Para asesoría laboral**\n- Columnas exactas del PDF\n- Desglose Ord/Ext\n- Formato profesional")
with col3:
    st.warning("**🎯 Uso autorizado**\n- Dirección/Gerencia\n- Asesoría laboral\n- Auditoría")

st.markdown("---")

# ── Subida PDF ──────────────────────────────────────────────────────────────
archivo = st.file_uploader(
    "📤 Suba el PDF de resumen contable mensual",
    type=["pdf"],
    help="El sistema extraerá todos los datos financieros y detectará el centro/año automáticamente"
)

if archivo:
    try:
        with st.spinner("🔄 Procesando PDF y detectando metadatos..."):
            # Necesitamos leer el archivo dos veces → guardamos bytes
            pdf_bytes = archivo.read()
            meta = extraer_metadatos_pdf(BytesIO(pdf_bytes))
            datos_meses = extraer_datos_por_mes(BytesIO(pdf_bytes))

    except Exception as e:
        st.error(f"❌ Error al procesar el PDF: {e}")
        st.stop()

    if not datos_meses or all(d["empleados"] == 0 for d in datos_meses.values()):
        st.error("❌ No se pudieron extraer datos válidos del PDF. Verifique que el formato sea el esperado.")
        st.stop()

    # ── Mostrar metadatos detectados + opción de corrección ─────────────────
    st.success(f"✅ Procesados **{len(datos_meses)}** meses correctamente")

    with st.expander("🏢 Datos detectados automáticamente (editable si es necesario)", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            empresa = st.text_input("Empresa", value=meta["empresa"])
        with c2:
            centro = st.text_input("Centro de trabajo", value=meta["centro"])
        with c3:
            anyo = st.text_input("Año", value=meta["anyo"])

    meses_ordenados = sorted(datos_meses.keys(), key=lambda x: MESES_ES[x])

    st.markdown("---")
    st.subheader("📊 Resumen Completo Mensual")

    # ── Tabla resumen ────────────────────────────────────────────────────────
    df_resumen = []
    for mes in meses_ordenados:
        d = datos_meses[mes]
        kpis = calcular_kpis_mes(d)
        df_resumen.append({
            "Mes":              mes.capitalize(),
            "Empleados":        d["empleados"],
            "Nóm.Ord":          d["nominas_ordinarias"],
            "Nóm.Ext":          d["nominas_extraordinarias"],
            # Columnas exactas PDF en orden:
            "Base C.C.":        f"{d['base_cc']:,.2f} €",
            "Base C.P.":        f"{d['base_cp']:,.2f} €",
            "Retribuciones":    f"{d['retribuciones']:,.2f} €",
            "Costes Trab.":     f"{d['deduccion_ss_trab']:,.2f} €",
            "Val. Especie":     f"{d['valor_especie']:,.2f} €",
            "Deducción":        f"{d['deduccion_adicional']:,.2f} €",
            "Costes Empresa":   f"{d['coste_ss_empresa']:,.2f} €",
            "Base IRPF":        f"{d['base_irpf']:,.2f} €",
            "Ret. IRPF":        f"{d['retencion_irpf']:,.2f} €",
            "Otras Ret.":       f"{d['otras_retenciones']:,.2f} €",
            "Líquido":          f"{d['liquido']:,.2f} €",
            # Calculada:
            "Coste Total":      f"{calcular_coste_total(d):,.2f} €",
        })

    ORDEN_COLS = [
        "Mes", "Empleados", "Nóm.Ord", "Nóm.Ext",
        "Base C.C.", "Base C.P.", "Retribuciones", "Costes Trab.",
        "Val. Especie", "Deducción", "Costes Empresa", "Base IRPF",
        "Ret. IRPF", "Otras Ret.", "Líquido", "Coste Total"
    ]
    df_display = pd.DataFrame(df_resumen)[ORDEN_COLS]
    st.dataframe(df_display, use_container_width=True, hide_index=True)
    st.caption("✅ Columnas en el orden exacto del PDF original")

    st.markdown("---")

    # ── KPIs ─────────────────────────────────────────────────────────────────
    st.subheader("📈 Indicadores Clave del Período")

    total_emp_sum = sum(d["empleados"] for d in datos_meses.values())
    prom_emp      = total_emp_sum // len(datos_meses)
    total_retrib  = sum(d["retribuciones"]  for d in datos_meses.values())
    total_ss_emp  = sum(d["coste_ss_empresa"] for d in datos_meses.values())
    total_coste   = total_retrib + total_ss_emp
    total_ord     = sum(d["nominas_ordinarias"]      for d in datos_meses.values())
    total_ext     = sum(d["nominas_extraordinarias"] for d in datos_meses.values())

    # Salario medio correcto: retrib total / (promedio empleados × nº meses)
    sal_medio = total_retrib / total_emp_sum if total_emp_sum > 0 else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("👥 Empleados Prom.", prom_emp)
    with c2:
        st.metric("💰 Salario Medio/Mes", f"{sal_medio:,.0f} €")
    with c3:
        st.metric("🏢 Coste Total Período", f"{total_coste:,.0f} €")
    with c4:
        st.metric("📋 Nóm. Ordinarias", total_ord)
    with c5:
        st.metric("🎁 Nóm. Extraordinarias", total_ext)

    st.markdown("---")

    # ── Gráficos ──────────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 Evolución Mensual")
        retribs  = [datos_meses[m]["retribuciones"]  for m in meses_ordenados]
        ss_emps  = [datos_meses[m]["coste_ss_empresa"] for m in meses_ordenados]
        costes_t = [r + c for r, c in zip(retribs, ss_emps)]
        eje_x    = [m.capitalize() for m in meses_ordenados]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=eje_x, y=retribs, mode='lines+markers', name='Retribuciones',
            line=dict(color='#2E86AB', width=3), marker=dict(size=8)
        ))
        fig.add_trace(go.Scatter(
            x=eje_x, y=costes_t, mode='lines+markers', name='Coste Total',
            line=dict(color='#C73E1D', width=3), marker=dict(size=8)
        ))
        # Delta mes a mes
        if len(retribs) > 1:
            deltas = [None] + [retribs[i] - retribs[i-1] for i in range(1, len(retribs))]
            fig.add_trace(go.Bar(
                x=eje_x, y=deltas, name='Variación Retrib.',
                marker_color=['#4CAF50' if (d or 0) >= 0 else '#F44336' for d in deltas],
                opacity=0.4, yaxis='y2'
            ))
            fig.update_layout(yaxis2=dict(overlaying='y', side='right', showgrid=False, title='Variación (€)'))

        fig.update_layout(
            height=380, xaxis_title="Mes", yaxis_title="Importe (€)",
            hovermode='x unified',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("📊 Distribución de Costes")
        total_liq      = sum(d["liquido"]           for d in datos_meses.values())
        total_irpf     = sum(d["retencion_irpf"]    for d in datos_meses.values())
        total_ss_trab  = sum(d["deduccion_ss_trab"] for d in datos_meses.values())

        fig_pie = go.Figure(data=[go.Pie(
            labels=['Líquido Empleados', 'IRPF', 'SS Trabajador', 'SS Empresa'],
            values=[total_liq, total_irpf, total_ss_trab, total_ss_emp],
            hole=.4,
            marker_colors=['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
        )])
        fig_pie.update_layout(
            height=380, showlegend=True,
            legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.05)
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # ── Gráfico Ord vs Ext ────────────────────────────────────────────────────
    st.subheader("📊 Nóminas Ordinarias vs Extraordinarias por Mes")
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=eje_x,
        y=[datos_meses[m]["retribuciones_ordinarias"] for m in meses_ordenados],
        name='Retrib. Ordinarias', marker_color='#2E86AB'
    ))
    fig_bar.add_trace(go.Bar(
        x=eje_x,
        y=[datos_meses[m]["retribuciones_extraordinarias"] for m in meses_ordenados],
        name='Retrib. Extraordinarias', marker_color='#F18F01'
    ))
    fig_bar.update_layout(
        barmode='stack', height=300,
        xaxis_title="Mes", yaxis_title="Importe (€)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    # ── Exportar ─────────────────────────────────────────────────────────────
    st.subheader("📥 Exportar Informes")
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### 📄 PDF Ejecutivo — 1 Folio A4 Apaisado")
        st.caption(
            f"Columnas exactas del PDF original · Centro: **{centro}** · "
            f"Año: **{anyo}** · Todo en un único folio"
        )

        # Logo para el PDF: usa el subido, o el de la carpeta de la app si existe
        logo_uploader = st.file_uploader(
            "🖼️ Logo para el PDF (opcional — PNG/JPG)",
            type=["png", "jpg", "jpeg"],
            key="logo_uploader"
        )
        # Determinar ruta del logo
        logo_path = None
        LOGO_APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LOGO.png")
        if logo_uploader:
            # Guardar logo subido en temporal
            logo_tmp = "/tmp/logo_informe.png"
            with open(logo_tmp, "wb") as f:
                f.write(logo_uploader.read())
            logo_path = logo_tmp
        elif os.path.exists(LOGO_APP):
            logo_path = LOGO_APP

        pdf_buffer = generar_pdf_ejecutivo(
            datos_meses, empresa=empresa, centro=centro, anyo=anyo, logo_path=logo_path
        )
        st.download_button(
            label="📄 Descargar PDF",
            data=pdf_buffer,
            file_name=f"informe_laboral_{empresa.lower().replace(' ','_')}_{anyo}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    with c2:
        st.markdown("### 📊 CSV Técnico (separador ; para Excel)")
        st.caption("Todas las columnas oficiales listas para importar a Excel o software contable")
        df_csv = generar_csv(datos_meses)
        csv_bytes = df_csv.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        st.download_button(
            label="📊 Descargar CSV",
            data=csv_bytes,
            file_name=f"datos_laborales_{empresa.lower().replace(' ','_')}_{anyo}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )

    with st.expander("👁️ Vista previa del CSV"):
        st.dataframe(df_csv, use_container_width=True, height=350)
        st.caption(f"✅ **{len(df_csv.columns)} columnas** | Separador: `;` | Decimal: `,`")

st.markdown("---")
st.markdown("""
    <div style='text-align: center; color: #666; padding: 16px;'>
        <p><b>🔐 Aplicación conforme con RGPD (UE) 2016/679</b></p>
        <p>No se almacenan datos personales identificables · Datos agregados por mes</p>
        <p>© COMASUR 2025 · Sistema de análisis laboral profesional</p>
    </div>
""", unsafe_allow_html=True)
