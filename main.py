import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
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
        # Eliminar espacios, puntos de miles y convertir coma a punto
        valor_limpio = str(valor_str).strip().replace(".", "").replace(",", ".")
        return float(valor_limpio)
    except:
        return 0.0

def extraer_datos_por_mes(pdf_file):
    """
    Extrae datos agregados por mes del PDF de COMASUR.
    NO almacena nombres de trabajadores, solo totales financieros.
    Incluye desglose por tipo de nómina (Ordinaria/Extraordinaria).
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
                # Detectar inicio de mes (formato: "Mes :Enero" o "Mes : Enero")
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
                                    "retribuciones": 0.0,
                                    "retribuciones_ordinarias": 0.0,
                                    "retribuciones_extraordinarias": 0.0,
                                    "base_cc": 0.0,
                                    "base_cp": 0.0,
                                    "base_irpf": 0.0,
                                    "deduccion_ss_trabajador": 0.0,
                                    "valor_especie": 0.0,
                                    "deducciones_adicionales": 0.0,  # Nueva columna
                                    "coste_ss_empresa": 0.0,
                                    "retencion_irpf": 0.0,
                                    "otras_retenciones": 0.0,
                                    "liquido": 0.0
                                }
                
                # Detectar línea de totales del mes
                # Formato: "Total de la Cuenta 18007705134 Principal (Enero) 10.179,82 10.179,82 9.549,31 659,67 0,00 0,00 3.279,93 9.549,31 907,32 150,00 7.832,32"
                if mes_actual and "Total de la Cuenta" in linea:
                    numeros = re.findall(r"[\d\.]+,\d{2}", linea)
                    
                    if len(numeros) >= 11:
                        try:
                            # Orden de columnas en línea de totales:
                            # [0]: Base C.C.
                            # [1]: Base C.P.
                            # [2]: Retribuciones (salario bruto)
                            # [3]: Deducción SS Trabajador
                            # [4]: Valor Especie (primera aparición)
                            # [5]: Deducciones Adicionales (anticipos/embargos) ← NUEVA
                            # [6]: Coste SS Empresa
                            # [7]: Base IRPF (repetida)
                            # [8]: Retención IRPF
                            # [9]: Otras Retenciones
                            # [10]: Líquido
                            
                            datos_meses[mes_actual]["base_cc"] = convertir_a_float(numeros[0])
                            datos_meses[mes_actual]["base_cp"] = convertir_a_float(numeros[1])
                            datos_meses[mes_actual]["retribuciones"] = convertir_a_float(numeros[2])
                            datos_meses[mes_actual]["base_irpf"] = convertir_a_float(numeros[2])
                            datos_meses[mes_actual]["deduccion_ss_trabajador"] = convertir_a_float(numeros[3])
                            datos_meses[mes_actual]["valor_especie"] = convertir_a_float(numeros[4])
                            datos_meses[mes_actual]["deducciones_adicionales"] = convertir_a_float(numeros[5])
                            datos_meses[mes_actual]["coste_ss_empresa"] = convertir_a_float(numeros[6])
                            datos_meses[mes_actual]["retencion_irpf"] = convertir_a_float(numeros[8])
                            datos_meses[mes_actual]["otras_retenciones"] = convertir_a_float(numeros[9])
                            datos_meses[mes_actual]["liquido"] = convertir_a_float(numeros[10])
                        
                        except Exception as e:
                            continue
                
                # Contar empleados y clasificar nóminas por tipo (Ord/Ext)
                if mes_actual and re.match(r"^\d+\s+[A-Z]", linea):
                    codigo_match = re.match(r"^(\d+)\s+", linea)
                    if codigo_match:
                        codigo_trabajador = codigo_match.group(1)
                        datos_meses[mes_actual]["empleados"].add(codigo_trabajador)
                        
                        # Detectar tipo de nómina (Ord = Ordinaria, Ext = Extraordinaria)
                        if " Ord " in linea:
                            datos_meses[mes_actual]["nominas_ordinarias"] += 1
                            # Extraer retribución de la línea individual (aproximado)
                            nums_linea = re.findall(r"[\d\.]+,\d{2}", linea)
                            if len(nums_linea) >= 3:
                                datos_meses[mes_actual]["retribuciones_ordinarias"] += convertir_a_float(nums_linea[2])
                        elif " Ext " in linea:
                            datos_meses[mes_actual]["nominas_extraordinarias"] += 1
                            nums_linea = re.findall(r"[\d\.]+,\d{2}", linea)
                            if len(nums_linea) >= 3:
                                datos_meses[mes_actual]["retribuciones_extraordinarias"] += convertir_a_float(nums_linea[2])
    
    # Convertir sets de empleados a conteos
    for mes in datos_meses:
        datos_meses[mes]["empleados"] = len(datos_meses[mes]["empleados"])
    
    return datos_meses

def calcular_coste_total_empresa(datos_mes):
    """Calcula el coste total para la empresa"""
    # Coste total = Retribuciones + Coste SS Empresa
    return datos_mes["retribuciones"] + datos_mes["coste_ss_empresa"]

def calcular_kpis_mes(datos_mes):
    """Calcula KPIs para un mes específico"""
    if datos_mes["empleados"] == 0:
        return {}
    
    coste_total = calcular_coste_total_empresa(datos_mes)
    
    return {
        "salario_medio": datos_mes["retribuciones"] / datos_mes["empleados"],
        "coste_medio_empleado": coste_total / datos_mes["empleados"],
        "ratio_ss_trabajador": (datos_mes["deduccion_ss_trabajador"] / datos_mes["retribuciones"] * 100) if datos_mes["retribuciones"] > 0 else 0,
        "ratio_ss_empresa": (datos_mes["coste_ss_empresa"] / datos_mes["retribuciones"] * 100) if datos_mes["retribuciones"] > 0 else 0,
        "ratio_irpf": (datos_mes["retencion_irpf"] / datos_mes["retribuciones"] * 100) if datos_mes["retribuciones"] > 0 else 0,
        "ratio_liquido": (datos_mes["liquido"] / datos_mes["retribuciones"] * 100) if datos_mes["retribuciones"] > 0 else 0,
        "coste_total": coste_total,
        "porcentaje_ordinarias": (datos_mes["nominas_ordinarias"] / (datos_mes["nominas_ordinarias"] + datos_mes["nominas_extraordinarias"]) * 100) if (datos_mes["nominas_ordinarias"] + datos_mes["nominas_extraordinarias"]) > 0 else 100
    }

def generar_pdf_ejecutivo(datos_meses, empresa="COMASUR", centro="MOTRIL"):
    """Genera PDF ejecutivo profesional con análisis multimensual completo"""
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=30)
    elementos = []
    estilos = getSampleStyleSheet()
    
    # Estilos personalizados
    estilo_titulo = ParagraphStyle(
        'CustomTitle',
        parent=estilos['Title'],
        fontSize=18,
        textColor=colors.HexColor('#003366'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    estilo_subtitulo = ParagraphStyle(
        'CustomHeading',
        parent=estilos['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#003366'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    # === PORTADA ===
    elementos.append(Spacer(1, 100))
    titulo = Paragraph(f"<b>INFORME LABORAL Y FINANCIERO<br/>{empresa}</b>", estilo_titulo)
    elementos.append(titulo)
    elementos.append(Spacer(1, 20))
    
    fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")
    info_portada = f"""
    <para align=center>
    <b>Centro de Trabajo:</b> {centro}<br/>
    <b>Período analizado:</b> {', '.join(sorted(datos_meses.keys(), key=lambda x: MESES_ES[x]))}<br/>
    <b>Generado:</b> {fecha_generacion}<br/>
    <br/>
    <i>Documento profesional para asesoría laboral</i>
    </para>
    """
    elementos.append(Paragraph(info_portada, estilos['Normal']))
    elementos.append(Spacer(1, 30))
    
    nota_confidencial = Paragraph(
        "🔒 <b>RGPD COMPLIANT</b> - Datos agregados sin información personal identificable",
        ParagraphStyle('Footer', parent=estilos['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    )
    elementos.append(nota_confidencial)
    elementos.append(PageBreak())
    
    # === TABLA ÚNICA COMPLETA ===
    elementos.append(Paragraph("<b>RESUMEN COMPLETO MENSUAL</b>", estilo_subtitulo))
    elementos.append(Spacer(1, 8))
    
    # Nota explicativa
    nota_tabla = Paragraph(
        "<i>Tabla completa con todos los datos financieros y técnicos del período</i>",
        ParagraphStyle('Note', parent=estilos['Normal'], fontSize=7, textColor=colors.grey, alignment=TA_CENTER)
    )
    elementos.append(nota_tabla)
    elementos.append(Spacer(1, 10))
    
    meses_ordenados = sorted(datos_meses.keys(), key=lambda x: MESES_ES[x])
    
    # Tabla única horizontal con TODAS las columnas organizadas inteligentemente
    # Usar abreviaturas y diseño compacto
    datos_tabla = [[
        # Identificación
        "Mes", "Emp.",
        # Tipos nómina
        "Ord", "Ext",
        # Bases oficiales (grupo 1)
        "Base\nC.C.", "Base\nC.P.", "Base\nIRPF",
        # Retribuciones
        "Retrib.\nTotal",
        # Deducciones (grupo 2)
        "SS\nTrab.", "SS\nEmp.", "IRPF",
        # Otros conceptos
        "Val.\nEsp.", "Ded.\nAdic.", "Otras\nRet.",
        # Resultado final
        "Líquido", "Coste\nTotal"
    ]]
    
    for mes in meses_ordenados:
        datos = datos_meses[mes]
        coste_total = calcular_coste_total_empresa(datos)
        
        datos_tabla.append([
            mes[:3].upper(),  # Abreviar mes (ENE, FEB, MAR...)
            str(datos["empleados"]),
            str(datos["nominas_ordinarias"]),
            str(datos["nominas_extraordinarias"]),
            f"{datos['base_cc']:,.2f}",
            f"{datos['base_cp']:,.2f}",
            f"{datos['base_irpf']:,.2f}",
            f"{datos['retribuciones']:,.2f}",
            f"{datos['deduccion_ss_trabajador']:,.2f}",
            f"{datos['coste_ss_empresa']:,.2f}",
            f"{datos['retencion_irpf']:,.2f}",
            f"{datos['valor_especie']:,.2f}",
            f"{datos['deducciones_adicionales']:,.2f}",
            f"{datos['otras_retenciones']:,.2f}",
            f"{datos['liquido']:,.2f}",
            f"{coste_total:,.2f}"
        ])
    
    # Fila de totales
    total_empleados = sum(d["empleados"] for d in datos_meses.values())
    promedio_empleados = total_empleados // len(datos_meses)
    total_ord = sum(d["nominas_ordinarias"] for d in datos_meses.values())
    total_ext = sum(d["nominas_extraordinarias"] for d in datos_meses.values())
    total_base_cc = sum(d["base_cc"] for d in datos_meses.values())
    total_base_cp = sum(d["base_cp"] for d in datos_meses.values())
    total_base_irpf = sum(d["base_irpf"] for d in datos_meses.values())
    total_retrib = sum(d["retribuciones"] for d in datos_meses.values())
    total_ss_trab = sum(d["deduccion_ss_trabajador"] for d in datos_meses.values())
    total_ss_emp = sum(d["coste_ss_empresa"] for d in datos_meses.values())
    total_irpf = sum(d["retencion_irpf"] for d in datos_meses.values())
    total_valor_especie = sum(d["valor_especie"] for d in datos_meses.values())
    total_deduc_adic = sum(d["deducciones_adicionales"] for d in datos_meses.values())
    total_otras_ret = sum(d["otras_retenciones"] for d in datos_meses.values())
    total_liquido = sum(d["liquido"] for d in datos_meses.values())
    total_coste = total_retrib + total_ss_emp
    
    datos_tabla.append([
        "TOT",
        str(promedio_empleados),
        str(total_ord),
        str(total_ext),
        f"{total_base_cc:,.2f}",
        f"{total_base_cp:,.2f}",
        f"{total_base_irpf:,.2f}",
        f"{total_retrib:,.2f}",
        f"{total_ss_trab:,.2f}",
        f"{total_ss_emp:,.2f}",
        f"{total_irpf:,.2f}",
        f"{total_valor_especie:,.2f}",
        f"{total_deduc_adic:,.2f}",
        f"{total_otras_ret:,.2f}",
        f"{total_liquido:,.2f}",
        f"{total_coste:,.2f}"
    ])
    
    # Anchos de columna optimizados para mostrar decimales (total ~540 puntos)
    col_widths = [
        28,   # Mes (abreviado)
        20,   # Emp
        18,   # Ord
        18,   # Ext
        38,   # Base CC (con decimales)
        38,   # Base CP (con decimales)
        38,   # Base IRPF (con decimales)
        42,   # Retrib Total (con decimales)
        35,   # SS Trab (con decimales)
        35,   # SS Emp (con decimales)
        35,   # IRPF (con decimales)
        32,   # Val Esp (con decimales)
        32,   # Ded Adic (con decimales)
        32,   # Otras Ret (con decimales)
        42,   # Líquido (con decimales)
        45    # Coste Total (con decimales)
    ]
    
    tabla_unica = Table(datos_tabla, colWidths=col_widths, repeatRows=1)
    
    # Estilo profesional con separadores visuales entre grupos
    tabla_unica.setStyle(TableStyle([
        # === ENCABEZADO ===
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#003366')),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 5.5),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.white),
        
        # === FILA DE TOTALES ===
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor('#CCE5FF')),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 6),
        
        # === DATOS GENERALES ===
        ("FONTSIZE", (0, 1), (-1, -2), 5.5),
        ("PADDING", (0, 0), (-1, -1), 2.5),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        
        # === BORDES ===
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        
        # === SEPARADORES VERTICALES ENTRE GRUPOS (líneas más gruesas) ===
        ("LINEAFTER", (1, 0), (1, -1), 0.75, colors.HexColor('#666666')),  # Después de Emp
        ("LINEAFTER", (3, 0), (3, -1), 0.75, colors.HexColor('#666666')),  # Después de Ext
        ("LINEAFTER", (6, 0), (6, -1), 0.75, colors.HexColor('#666666')),  # Después de Base IRPF
        ("LINEAFTER", (7, 0), (7, -1), 0.75, colors.HexColor('#666666')),  # Después de Retrib
        ("LINEAFTER", (10, 0), (10, -1), 0.75, colors.HexColor('#666666')), # Después de IRPF
        ("LINEAFTER", (13, 0), (13, -1), 0.75, colors.HexColor('#666666')), # Después de Otras Ret
        
        # === ALTERNAR COLORES DE FILA ===
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor('#F8F8F8')]),
        
        # === DESTACAR COLUMNAS CLAVE CON FONDOS SUTILES ===
        ("BACKGROUND", (7, 1), (7, -2), colors.HexColor('#FFFACD')),   # Retrib Total (amarillo claro)
        ("BACKGROUND", (14, 1), (14, -2), colors.HexColor('#E0F7FA')),  # Líquido (azul claro)
        ("BACKGROUND", (15, 1), (15, -2), colors.HexColor('#FFEBEE')),  # Coste Total (rojo claro)
    ]))
    
    elementos.append(tabla_unica)
    elementos.append(Spacer(1, 12))
    
    # === LEYENDA COMPACTA ===
    leyenda = """
    <b>Abreviaturas:</b> Emp.=Empleados | Ord=Nóminas Ordinarias | Ext=Nóminas Extraordinarias | 
    Base C.C.=Contingencias Comunes | Base C.P.=Contingencias Profesionales | Base IRPF=Base Imponible | 
    Retrib.=Retribuciones | SS=Seguridad Social | Trab.=Trabajador | Emp.=Empresa | 
    Val.Esp.=Valor en Especie | Ded.Adic.=Deducciones Adicionales (anticipos/embargos) | 
    Otras Ret.=Otras Retenciones
    """
    elementos.append(Paragraph(leyenda, ParagraphStyle('Legend', parent=estilos['Normal'], fontSize=6.5, textColor=colors.grey)))
    elementos.append(Spacer(1, 20))
    
    # === KPIs PROMEDIO ===
    elementos.append(PageBreak())
    elementos.append(Paragraph("<b>INDICADORES CLAVE DEL PERÍODO</b>", estilo_subtitulo))
    elementos.append(Spacer(1, 12))
    
    salario_medio_periodo = total_retrib / total_empleados if total_empleados > 0 else 0
    coste_medio_periodo = total_coste / total_empleados if total_empleados > 0 else 0
    
    datos_kpis = [
        ["Indicador", "Valor"],
        ["Empleados Promedio Mensual", f"{promedio_empleados}"],
        ["Salario Medio Mensual", f"{salario_medio_periodo:,.2f} €"],
        ["Coste Medio por Empleado/Mes", f"{coste_medio_periodo:,.2f} €"],
        ["% SS Trabajador sobre Salarios", f"{(total_ss_trab/total_retrib*100):.2f}%" if total_retrib > 0 else "N/A"],
        ["% SS Empresa sobre Salarios", f"{(total_ss_emp/total_retrib*100):.2f}%" if total_retrib > 0 else "N/A"],
        ["% IRPF sobre Salarios", f"{(total_irpf/total_retrib*100):.2f}%" if total_retrib > 0 else "N/A"],
        ["% Líquido sobre Salarios", f"{(total_liquido/total_retrib*100):.2f}%" if total_retrib > 0 else "N/A"],
        ["Total Nóminas Ordinarias", f"{total_ord}"],
        ["Total Nóminas Extraordinarias", f"{total_ext}"],
    ]
    
    tabla_kpis = Table(datos_kpis, colWidths=[300, 150])
    tabla_kpis.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#CC6600')),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
    ]))
    
    elementos.append(tabla_kpis)
    elementos.append(Spacer(1, 30))
    
    # === NOTAS TÉCNICAS ===
    elementos.append(Paragraph("<b>NOTAS TÉCNICAS</b>", estilo_subtitulo))
    elementos.append(Spacer(1, 8))
    
    notas = """
    <b>Abreviaturas utilizadas:</b><br/>
    • <b>Base C.C.:</b> Base de Cotización por Contingencias Comunes<br/>
    • <b>Base C.P.:</b> Base de Cotización por Contingencias Profesionales<br/>
    • <b>Base IRPF:</b> Base imponible para retención de IRPF<br/>
    • <b>SS Trab.:</b> Cotizaciones Seguridad Social a cargo del trabajador<br/>
    • <b>SS Empresa:</b> Cotizaciones Seguridad Social a cargo de la empresa<br/>
    • <b>Deduc. Adic.:</b> Deducciones adicionales (anticipos, embargos, préstamos)<br/>
    • <b>Otras Ret.:</b> Otras retenciones aplicadas<br/>
    • <b>Nóm. Ord:</b> Nóminas ordinarias mensuales<br/>
    • <b>Nóm. Ext:</b> Nóminas extraordinarias (pagas extras, gratificaciones)<br/>
    <br/>
    <b>Validez del documento:</b><br/>
    Este informe contiene datos agregados aptos para presentación a asesoría laboral,
    gestoría o auditoría. Los datos están anonimizados conforme al RGPD (UE) 2016/679.
    """
    
    elementos.append(Paragraph(notas, ParagraphStyle('Notes', parent=estilos['Normal'], fontSize=8)))
    elementos.append(Spacer(1, 30))
    
    # === PIE DE PÁGINA ===
    nota_legal = Paragraph(
        f"<i>Documento generado automáticamente el {fecha_generacion}<br/>"
        "Sistema de análisis laboral anonimizado - Cumplimiento RGPD</i>",
        ParagraphStyle('Footer', parent=estilos['Normal'], fontSize=7, textColor=colors.grey, alignment=TA_CENTER)
    )
    elementos.append(nota_legal)
    
    doc.build(elementos)
    buffer.seek(0)
    
    return buffer
def generar_csv_tecnico_completo(datos_meses):
    """
    Genera CSV técnico completo con TODAS las columnas oficiales
    para asesoría laboral y gestoría.
    """
    meses_ordenados = sorted(datos_meses.keys(), key=lambda x: MESES_ES[x])
    
    csv_data = []
    
    for mes in meses_ordenados:
        datos = datos_meses[mes]
        coste_total = calcular_coste_total_empresa(datos)
        kpis = calcular_kpis_mes(datos)
        
        csv_data.append({
            "Mes": mes,
            "Numero_Mes": MESES_ES[mes],
            "Empleados": datos["empleados"],
            "Nominas_Ordinarias": datos["nominas_ordinarias"],
            "Nominas_Extraordinarias": datos["nominas_extraordinarias"],
            "Base_Contingencias_Comunes": round(datos["base_cc"], 2),
            "Base_Contingencias_Profesionales": round(datos["base_cp"], 2),
            "Base_IRPF": round(datos["base_irpf"], 2),
            "Retribuciones_Totales": round(datos["retribuciones"], 2),
            "Retribuciones_Ordinarias": round(datos["retribuciones_ordinarias"], 2),
            "Retribuciones_Extraordinarias": round(datos["retribuciones_extraordinarias"], 2),
            "Deduccion_SS_Trabajador": round(datos["deduccion_ss_trabajador"], 2),
            "Valor_Especie": round(datos["valor_especie"], 2),
            "Deducciones_Adicionales": round(datos["deducciones_adicionales"], 2),
            "Coste_SS_Empresa": round(datos["coste_ss_empresa"], 2),
            "Retencion_IRPF": round(datos["retencion_irpf"], 2),
            "Otras_Retenciones": round(datos["otras_retenciones"], 2),
            "Liquido_Total": round(datos["liquido"], 2),
            "Coste_Total_Empresa": round(coste_total, 2),
            "Salario_Medio": round(kpis.get("salario_medio", 0), 2),
            "Coste_Medio_Empleado": round(kpis.get("coste_medio_empleado", 0), 2),
            "Porcentaje_SS_Trabajador": round(kpis.get("ratio_ss_trabajador", 0), 2),
            "Porcentaje_SS_Empresa": round(kpis.get("ratio_ss_empresa", 0), 2),
            "Porcentaje_IRPF": round(kpis.get("ratio_irpf", 0), 2),
            "Porcentaje_Liquido": round(kpis.get("ratio_liquido", 0), 2),
            "Porcentaje_Nominas_Ordinarias": round(kpis.get("porcentaje_ordinarias", 100), 2)
        })
    
    df = pd.DataFrame(csv_data)
    return df



st.title("📊 Análisis Laboral y Financiero Profesional")
st.caption("🔒 Sistema anonimizado - Cumplimiento RGPD | ✅ Apto para asesoría laboral")

st.markdown("---")

# Información del sistema
col1, col2, col3 = st.columns(3)

with col1:
    st.info("**✅ SIN datos personales**\n- No almacena nombres\n- No almacena apellidos\n- Solo datos agregados")

with col2:
    st.success("**📋 Para asesoría laboral**\n- Todas las bases oficiales\n- Desglose Ord/Ext\n- Formato profesional")

with col3:
    st.warning("**🎯 Uso autorizado**\n- Dirección/Gerencia\n- Asesoría laboral\n- Auditoría")

# Upload PDF
st.markdown("---")
archivo = st.file_uploader(
    "📤 Suba el PDF de resumen contable mensual",
    type=["pdf"],
    help="El sistema extraerá todos los datos financieros necesarios para la asesoría"
)

if archivo:
    
    with st.spinner("🔄 Procesando PDF completo y anonimizando datos..."):
        datos_meses = extraer_datos_por_mes(archivo)
    
    if not datos_meses or all(d["empleados"] == 0 for d in datos_meses.values()):
        st.error("❌ No se pudieron extraer datos válidos del PDF")
    
    else:
        st.success(f"✅ Procesados {len(datos_meses)} meses correctamente")
        
        # Ordenar meses
        meses_ordenados = sorted(datos_meses.keys(), key=lambda x: MESES_ES[x])
        
        st.markdown("---")
        st.subheader("📊 Resumen Completo Mensual - Todas las Columnas")
        
        # Crear DataFrame completo con las 16 columnas (igual que el PDF)
        df_resumen = []
        for mes in meses_ordenados:
            datos = datos_meses[mes]
            kpis = calcular_kpis_mes(datos)
            
            df_resumen.append({
                "Mes": mes.capitalize(),
                "Emp.": datos["empleados"],
                "Nóm.Ord": datos["nominas_ordinarias"],
                "Nóm.Ext": datos["nominas_extraordinarias"],
                "Base C.C.": f"{datos['base_cc']:,.2f} €",
                "Base C.P.": f"{datos['base_cp']:,.2f} €",
                "Base IRPF": f"{datos['base_irpf']:,.2f} €",
                "Retribuciones": f"{datos['retribuciones']:,.2f} €",
                "SS Trab.": f"{datos['deduccion_ss_trabajador']:,.2f} €",
                "SS Empresa": f"{datos['coste_ss_empresa']:,.2f} €",
                "IRPF": f"{datos['retencion_irpf']:,.2f} €",
                "Val.Especie": f"{datos['valor_especie']:,.2f} €",
                "Ded.Adic.": f"{datos['deducciones_adicionales']:,.2f} €",
                "Otras Ret.": f"{datos['otras_retenciones']:,.2f} €",
                "Líquido": f"{datos['liquido']:,.2f} €",
                "Coste Total": f"{kpis.get('coste_total', 0):,.2f} €"
            })
        
        df_display = pd.DataFrame(df_resumen)
        st.dataframe(df_display, use_container_width=True, hide_index=True, height=400)
        
        st.caption("✅ **16 columnas completas** | 📊 Datos con 2 decimales (sin redondeo)")
        
        st.markdown("---")
        
        # KPIs principales
        st.subheader("📈 Indicadores Clave del Período")
        
        total_empleados = sum(d["empleados"] for d in datos_meses.values())
        promedio_empleados = total_empleados // len(datos_meses)
        total_retrib = sum(d["retribuciones"] for d in datos_meses.values())
        total_ss_emp = sum(d["coste_ss_empresa"] for d in datos_meses.values())
        total_coste = total_retrib + total_ss_emp
        total_ord = sum(d["nominas_ordinarias"] for d in datos_meses.values())
        total_ext = sum(d["nominas_extraordinarias"] for d in datos_meses.values())
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("👥 Empleados Promedio", promedio_empleados)
        
        with col2:
            salario_medio = total_retrib / total_empleados if total_empleados > 0 else 0
            st.metric("💰 Salario Medio/Mes", f"{salario_medio:,.0f} €")
        
        with col3:
            st.metric("🏢 Coste Total Período", f"{total_coste:,.0f} €")
        
        with col4:
            st.metric("📋 Nóminas Ordinarias", total_ord)
        
        with col5:
            st.metric("🎁 Nóminas Extras", total_ext)
        
        st.markdown("---")
        
        # Gráficos
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Evolución Mensual")
            
            retribuciones_mes = [datos_meses[m]["retribuciones"] for m in meses_ordenados]
            costes_empresa_mes = [datos_meses[m]["coste_ss_empresa"] for m in meses_ordenados]
            coste_total_mes = [r + c for r, c in zip(retribuciones_mes, costes_empresa_mes)]
            
            fig_lineas = go.Figure()
            
            fig_lineas.add_trace(go.Scatter(
                x=[m.capitalize() for m in meses_ordenados],
                y=retribuciones_mes,
                mode='lines+markers',
                name='Retribuciones',
                line=dict(color='#2E86AB', width=3),
                marker=dict(size=8)
            ))
            
            fig_lineas.add_trace(go.Scatter(
                x=[m.capitalize() for m in meses_ordenados],
                y=coste_total_mes,
                mode='lines+markers',
                name='Coste Total Empresa',
                line=dict(color='#C73E1D', width=3),
                marker=dict(size=8)
            ))
            
            fig_lineas.update_layout(
                height=400,
                xaxis_title="Mes",
                yaxis_title="Importe (€)",
                hovermode='x unified',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            st.plotly_chart(fig_lineas, use_container_width=True)
        
        with col2:
            st.subheader("📊 Distribución Costes")
            
            total_liquido = sum(d["liquido"] for d in datos_meses.values())
            total_irpf = sum(d["retencion_irpf"] for d in datos_meses.values())
            total_ss_trab = sum(d["deduccion_ss_trabajador"] for d in datos_meses.values())
            
            fig_pie = go.Figure(data=[go.Pie(
                labels=['Líquido Empleados', 'IRPF', 'SS Trabajador', 'SS Empresa'],
                values=[total_liquido, total_irpf, total_ss_trab, total_ss_emp],
                hole=.4,
                marker_colors=['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
            )])
            
            fig_pie.update_layout(
                height=400,
                showlegend=True,
                legend=dict(
                    orientation="v",
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    x=1.05
                )
            )
            
            st.plotly_chart(fig_pie, use_container_width=True)
        
        st.markdown("---")
        
        st.markdown("---")
        
        # Descargas
        st.subheader("📥 Exportar Informes")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📄 PDF Profesional Ejecutivo")
            st.caption("Informe completo con todas las tablas, KPIs y análisis para dirección y asesoría laboral")
            
            pdf_buffer = generar_pdf_ejecutivo(datos_meses)
            
            st.download_button(
                label="📄 Descargar PDF Completo",
                data=pdf_buffer,
                file_name=f"informe_laboral_comasur_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        with col2:
            st.markdown("### 📊 CSV Técnico para Asesoría")
            st.caption("Todas las columnas oficiales (27 campos) listos para importar a Excel o software contable")
            
            df_csv_completo = generar_csv_tecnico_completo(datos_meses)
            csv_completo = df_csv_completo.to_csv(index=False).encode("utf-8")
            
            st.download_button(
                label="📊 Descargar CSV Técnico Completo",
                data=csv_completo,
                file_name=f"datos_tecnicos_comasur_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        st.markdown("---")
        
        # Vista previa CSV
        with st.expander("👁️ Vista Previa del CSV Técnico Completo"):
            st.dataframe(df_csv_completo, use_container_width=True, height=400)
            st.caption(f"✅ **{len(df_csv_completo.columns)} columnas** con todos los datos necesarios para asesoría laboral")

st.markdown("---")
st.markdown("""
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p><b>🔐 Aplicación conforme con RGPD (UE) 2016/679</b></p>
        <p>No se almacenan datos personales identificables | Datos agregados por mes</p>
        <p>© COMASUR 2025 | Sistema de análisis laboral profesional</p>
    </div>
""", unsafe_allow_html=True)
