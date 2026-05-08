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
                                    "empleados": set(),  # Usar set para evitar duplicados
                                    "retribuciones": 0.0,
                                    "base_cc": 0.0,
                                    "base_cp": 0.0,
                                    "base_irpf": 0.0,
                                    "deduccion": 0.0,
                                    "costes_empresa": 0.0,
                                    "irpf": 0.0,
                                    "otras_retenciones": 0.0,
                                    "liquido": 0.0,
                                    "valor_especie": 0.0
                                }
                
                # Detectar línea de totales del mes
                # Formato real: "Total de la Cuenta 18007705134 Principal (Enero) 10.179,82 10.179,82 9.549,31 659,67 0,00 0,00 3.279,93 9.549,31 907,32 150,00 7.832,32"
                if mes_actual and "Total de la Cuenta" in linea:
                    numeros = re.findall(r"[\d\.]+,\d{2}", linea)
                    
                    if len(numeros) >= 10:
                        try:
                            # Orden correcto basado en el PDF:
                            # [0]: Base C.C. = 10.179,82
                            # [1]: Base C.P. = 10.179,82
                            # [2]: Retribuciones/Base IRPF = 9.549,31
                            # [3]: Deducción = 659,67
                            # [4-5]: Valor Especie = 0,00
                            # [6]: Costes Empresa (SS) = 3.279,93
                            # [7]: Base IRPF repetido = 9.549,31
                            # [8]: IRPF = 907,32
                            # [9]: Otras Retenciones = 150,00
                            # [10]: Líquido = 7.832,32
                            
                            datos_meses[mes_actual]["base_cc"] = convertir_a_float(numeros[0])
                            datos_meses[mes_actual]["base_cp"] = convertir_a_float(numeros[1])
                            datos_meses[mes_actual]["retribuciones"] = convertir_a_float(numeros[2])
                            datos_meses[mes_actual]["base_irpf"] = convertir_a_float(numeros[2])
                            datos_meses[mes_actual]["deduccion"] = convertir_a_float(numeros[3])
                            datos_meses[mes_actual]["valor_especie"] = convertir_a_float(numeros[4])
                            datos_meses[mes_actual]["costes_empresa"] = convertir_a_float(numeros[6])
                            datos_meses[mes_actual]["irpf"] = convertir_a_float(numeros[8])
                            datos_meses[mes_actual]["otras_retenciones"] = convertir_a_float(numeros[9])
                            datos_meses[mes_actual]["liquido"] = convertir_a_float(numeros[10])
                        
                        except Exception as e:
                            continue
                
                # Contar empleados únicos por código de trabajador
                if mes_actual and re.match(r"^\d+\s+[A-Z]", linea):
                    codigo_match = re.match(r"^(\d+)\s+", linea)
                    if codigo_match:
                        codigo_trabajador = codigo_match.group(1)
                        datos_meses[mes_actual]["empleados"].add(codigo_trabajador)
    
    # Convertir sets de empleados a conteos
    for mes in datos_meses:
        datos_meses[mes]["empleados"] = len(datos_meses[mes]["empleados"])
    
    return datos_meses

def calcular_coste_total_empresa(datos_mes):
    """Calcula el coste total para la empresa"""
    # Coste total = Retribuciones + Costes Empresa (SS empresa)
    return datos_mes["retribuciones"] + datos_mes["costes_empresa"]

def calcular_kpis_mes(datos_mes):
    """Calcula KPIs para un mes específico"""
    if datos_mes["empleados"] == 0:
        return {}
    
    coste_total = calcular_coste_total_empresa(datos_mes)
    
    return {
        "salario_medio": datos_mes["retribuciones"] / datos_mes["empleados"],
        "coste_medio_empleado": coste_total / datos_mes["empleados"],
        "ratio_ss_salarial": (datos_mes["deduccion"] / datos_mes["retribuciones"] * 100) if datos_mes["retribuciones"] > 0 else 0,
        "ratio_irpf": (datos_mes["irpf"] / datos_mes["retribuciones"] * 100) if datos_mes["retribuciones"] > 0 else 0,
        "ratio_liquido": (datos_mes["liquido"] / datos_mes["retribuciones"] * 100) if datos_mes["retribuciones"] > 0 else 0,
        "coste_total": coste_total
    }

def generar_pdf_ejecutivo(datos_meses, empresa="COMASUR", centro="MOTRIL"):
    """Genera PDF ejecutivo con análisis multimensual"""
    
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
        alignment=TA_CENTER
    )
    
    estilo_subtitulo = ParagraphStyle(
        'CustomHeading',
        parent=estilos['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#003366'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Portada
    elementos.append(Spacer(1, 100))
    titulo = Paragraph(f"<b>INFORME FINANCIERO<br/>NÓMINAS {empresa}</b>", estilo_titulo)
    elementos.append(titulo)
    elementos.append(Spacer(1, 20))
    
    fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")
    info_portada = f"""
    <para align=center>
    <b>Centro:</b> {centro}<br/>
    <b>Período:</b> {', '.join(sorted(datos_meses.keys(), key=lambda x: MESES_ES[x]))}<br/>
    <b>Generado:</b> {fecha_generacion}<br/>
    </para>
    """
    elementos.append(Paragraph(info_portada, estilos['Normal']))
    elementos.append(Spacer(1, 30))
    
    nota_confidencial = Paragraph(
        "<i>🔒 Documento conforme RGPD - Sin datos personales de trabajadores</i>",
        ParagraphStyle('Italic', parent=estilos['Normal'], alignment=TA_CENTER, textColor=colors.grey)
    )
    elementos.append(nota_confidencial)
    elementos.append(PageBreak())
    
    # Resumen ejecutivo por mes
    elementos.append(Paragraph("<b>RESUMEN EJECUTIVO POR MES</b>", estilo_subtitulo))
    elementos.append(Spacer(1, 12))
    
    # Tabla resumen mensual
    meses_ordenados = sorted(datos_meses.keys(), key=lambda x: MESES_ES[x])
    
    datos_tabla = [["Mes", "Empleados", "Retribuciones", "SS Empresa", "IRPF", "Líquido", "Coste Total"]]
    
    for mes in meses_ordenados:
        datos = datos_meses[mes]
        coste_total = calcular_coste_total_empresa(datos)
        
        datos_tabla.append([
            mes.capitalize(),
            str(datos["empleados"]),
            f"{datos['retribuciones']:,.2f} €",
            f"{datos['costes_empresa']:,.2f} €",
            f"{datos['irpf']:,.2f} €",
            f"{datos['liquido']:,.2f} €",
            f"{coste_total:,.2f} €"
        ])
    
    # Totales
    total_empleados = sum(d["empleados"] for d in datos_meses.values())
    total_retrib = sum(d["retribuciones"] for d in datos_meses.values())
    total_ss = sum(d["costes_empresa"] for d in datos_meses.values())
    total_irpf = sum(d["irpf"] for d in datos_meses.values())
    total_liquido = sum(d["liquido"] for d in datos_meses.values())
    total_coste = total_retrib + total_ss
    
    datos_tabla.append([
        "TOTAL",
        str(total_empleados // len(datos_meses)),  # Promedio empleados
        f"{total_retrib:,.2f} €",
        f"{total_ss:,.2f} €",
        f"{total_irpf:,.2f} €",
        f"{total_liquido:,.2f} €",
        f"{total_coste:,.2f} €"
    ])
    
    tabla_resumen = Table(datos_tabla, repeatRows=1)
    tabla_resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#003366')),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor('#CCE5FF')),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))
    
    elementos.append(tabla_resumen)
    elementos.append(Spacer(1, 20))
    
    # KPIs promedio del período
    elementos.append(PageBreak())
    elementos.append(Paragraph("<b>INDICADORES PROMEDIO DEL PERÍODO</b>", estilo_subtitulo))
    elementos.append(Spacer(1, 12))
    
    salario_medio_periodo = total_retrib / total_empleados if total_empleados > 0 else 0
    coste_medio_periodo = total_coste / total_empleados if total_empleados > 0 else 0
    
    datos_kpis = [
        ["Indicador", "Valor"],
        ["Salario Medio Mensual", f"{salario_medio_periodo:,.2f} €"],
        ["Coste Medio por Empleado", f"{coste_medio_periodo:,.2f} €"],
        ["% SS Empresa sobre Salarios", f"{(total_ss/total_retrib*100):.2f}%" if total_retrib > 0 else "N/A"],
        ["% IRPF sobre Salarios", f"{(total_irpf/total_retrib*100):.2f}%" if total_retrib > 0 else "N/A"],
        ["% Líquido sobre Salarios", f"{(total_liquido/total_retrib*100):.2f}%" if total_retrib > 0 else "N/A"]
    ]
    
    tabla_kpis = Table(datos_kpis)
    tabla_kpis.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
    ]))
    
    elementos.append(tabla_kpis)
    elementos.append(Spacer(1, 30))
    
    # Pie de página legal
    elementos.append(Spacer(1, 50))
    nota_legal = Paragraph(
        "<i>Informe generado automáticamente sin inclusión de datos personales identificables.<br/>"
        "Cumplimiento RGPD - Reglamento (UE) 2016/679</i>",
        ParagraphStyle('Footer', parent=estilos['Normal'], fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    )
    elementos.append(nota_legal)
    
    doc.build(elementos)
    buffer.seek(0)
    
    return buffer

# =========================
# INTERFAZ STREAMLIT
# =========================

st.title("📊 Análisis Financiero COMASUR")
st.caption("🔒 Sistema anonimizado - Cumplimiento RGPD")

st.markdown("---")

# Información del sistema
col1, col2 = st.columns([2, 3])

with col1:
    st.info("ℹ️ **Esta aplicación:**\n- ✅ Extrae solo datos financieros agregados\n- ✅ NO almacena nombres de trabajadores\n- ✅ Cumple con RGPD")

with col2:
    st.warning("⚠️ **Uso autorizado únicamente para:**\n- Dirección / Gerencia\n- Análisis financiero empresarial\n- Informes de costes laborales")

# Upload PDF
st.markdown("---")
archivo = st.file_uploader(
    "📤 Suba el PDF de resumen contable (ENERO-OCTUBRE 2025 u otro período)",
    type=["pdf"],
    help="El sistema extraerá datos agregados por mes sin información personal"
)

if archivo:
    
    with st.spinner("🔄 Procesando PDF y anonimizando datos..."):
        datos_meses = extraer_datos_por_mes(archivo)
    
    if not datos_meses or all(d["empleados"] == 0 for d in datos_meses.values()):
        st.error("❌ No se pudieron extraer datos válidos del PDF")
    
    else:
        st.success(f"✅ Procesados {len(datos_meses)} meses correctamente")
        
        # Ordenar meses
        meses_ordenados = sorted(datos_meses.keys(), key=lambda x: MESES_ES[x])
        
        st.markdown("---")
        st.subheader("📊 Resumen por Mes")
        
        # Crear DataFrame para visualización
        df_resumen = []
        for mes in meses_ordenados:
            datos = datos_meses[mes]
            kpis = calcular_kpis_mes(datos)
            
            df_resumen.append({
                "Mes": mes.capitalize(),
                "Empleados": datos["empleados"],
                "Retribuciones": f"{datos['retribuciones']:,.2f} €",
                "SS Empresa": f"{datos['costes_empresa']:,.2f} €",
                "IRPF": f"{datos['irpf']:,.2f} €",
                "Líquido": f"{datos['liquido']:,.2f} €",
                "Coste Total": f"{kpis.get('coste_total', 0):,.2f} €"
            })
        
        df_display = pd.DataFrame(df_resumen)
        st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # Gráficos
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📈 Evolución Costes Mensuales")
            
            fig_lineas = go.Figure()
            
            retribuciones_mes = [datos_meses[m]["retribuciones"] for m in meses_ordenados]
            costes_empresa_mes = [datos_meses[m]["costes_empresa"] for m in meses_ordenados]
            coste_total_mes = [r + c for r, c in zip(retribuciones_mes, costes_empresa_mes)]
            
            fig_lineas.add_trace(go.Scatter(
                x=[m.capitalize() for m in meses_ordenados],
                y=retribuciones_mes,
                mode='lines+markers',
                name='Retribuciones',
                line=dict(color='#2E86AB', width=2)
            ))
            
            fig_lineas.add_trace(go.Scatter(
                x=[m.capitalize() for m in meses_ordenados],
                y=coste_total_mes,
                mode='lines+markers',
                name='Coste Total',
                line=dict(color='#C73E1D', width=2)
            ))
            
            fig_lineas.update_layout(
                height=400,
                xaxis_title="Mes",
                yaxis_title="Importe (€)",
                hovermode='x unified'
            )
            
            st.plotly_chart(fig_lineas, use_container_width=True)
        
        with col2:
            st.subheader("📊 Distribución Costes (Total Período)")
            
            total_retrib = sum(d["retribuciones"] for d in datos_meses.values())
            total_ss = sum(d["costes_empresa"] for d in datos_meses.values())
            total_irpf = sum(d["irpf"] for d in datos_meses.values())
            total_liquido = sum(d["liquido"] for d in datos_meses.values())
            
            fig_pie = go.Figure(data=[go.Pie(
                labels=['Líquido Empleados', 'IRPF', 'SS Empresa'],
                values=[total_liquido, total_irpf, total_ss],
                hole=.3,
                marker_colors=['#2E86AB', '#A23B72', '#C73E1D']
            )])
            
            fig_pie.update_layout(height=400)
            
            st.plotly_chart(fig_pie, use_container_width=True)
        
        st.markdown("---")
        
        # KPIs generales
        st.subheader("📈 Indicadores del Período")
        
        total_empleados = sum(d["empleados"] for d in datos_meses.values())
        promedio_empleados = total_empleados // len(datos_meses)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("👥 Empleados Promedio", promedio_empleados)
        
        with col2:
            salario_medio = total_retrib / total_empleados if total_empleados > 0 else 0
            st.metric("💰 Salario Medio", f"{salario_medio:,.0f} €")
        
        with col3:
            total_coste = total_retrib + total_ss
            st.metric("🏢 Coste Total Período", f"{total_coste:,.0f} €")
        
        with col4:
            coste_medio = total_coste / total_empleados if total_empleados > 0 else 0
            st.metric("💼 Coste Medio/Empleado", f"{coste_medio:,.0f} €")
        
        st.markdown("---")
        
        # Descargas
        st.subheader("📥 Exportar Informes")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # PDF ejecutivo
            pdf_buffer = generar_pdf_ejecutivo(datos_meses)
            
            st.download_button(
                label="📄 Descargar Informe PDF Ejecutivo",
                data=pdf_buffer,
                file_name=f"informe_comasur_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        with col2:
            # CSV agregado
            csv_data = []
            for mes in meses_ordenados:
                datos = datos_meses[mes]
                kpis = calcular_kpis_mes(datos)
                
                csv_data.append({
                    "Mes": mes,
                    "Empleados": datos["empleados"],
                    "Retribuciones": datos["retribuciones"],
                    "Costes_SS_Empresa": datos["costes_empresa"],
                    "IRPF": datos["irpf"],
                    "Liquido": datos["liquido"],
                    "Coste_Total": kpis.get("coste_total", 0),
                    "Salario_Medio": kpis.get("salario_medio", 0),
                    "Coste_Medio_Empleado": kpis.get("coste_medio_empleado", 0)
                })
            
            df_csv = pd.DataFrame(csv_data)
            csv = df_csv.to_csv(index=False).encode("utf-8")
            
            st.download_button(
                label="📊 Descargar CSV Financiero",
                data=csv,
                file_name=f"datos_comasur_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

st.markdown("---")
st.caption("🔐 Aplicación conforme con RGPD - No se almacenan datos personales de trabajadores | © COMASUR 2025")
