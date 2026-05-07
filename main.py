import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# ------------------------------------------------
# CONFIGURACIÓN
# ------------------------------------------------

st.set_page_config(
    page_title="Extractor Nóminas Comasur",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Extractor Inteligente de Nóminas")
st.markdown(
    "Detecta meses automáticamente y genera PDFs estructurados"
)

# ------------------------------------------------
# MESES
# ------------------------------------------------

MESES = [
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE"
]

# ------------------------------------------------
# FUNCIONES
# ------------------------------------------------

def detectar_meses(pdf):

    meses_detectados = {}

    for i, page in enumerate(pdf.pages):

        texto = page.extract_text()

        if not texto:
            continue

        texto = texto.upper()

        for mes in MESES:

            if mes in texto:

                if mes not in meses_detectados:
                    meses_detectados[mes] = []

                meses_detectados[mes].append(i)

    return meses_detectados


def limpiar_texto(texto):

    if texto is None:
        return ""

    texto = str(texto)

    texto = texto.replace("\n", " ")
    texto = texto.replace("  ", " ")

    return texto.strip()


# ------------------------------------------------
# EXTRACCIÓN REAL
# ------------------------------------------------

def extraer_tablas_mes(pdf, paginas):

    registros = []

    for pagina_num in paginas:

        page = pdf.pages[pagina_num]

        texto = page.extract_text()

        if not texto:
            continue

        lineas = texto.split("\n")

        for linea in lineas:

            linea = limpiar_texto(linea)

            if len(linea) < 20:
                continue

            # Detecta línea de empleado
            if re.match(r"^\d+\s+[A-ZÁÉÍÓÚÑ]", linea):

                # Separar bloques grandes
                partes = re.split(r"\s{2,}", linea)

                if len(partes) == 1:
                    partes = linea.split()

                registros.append(partes)

    return registros


# ------------------------------------------------
# PDF
# ------------------------------------------------

def generar_pdf(df, mes):

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )

    elementos = []

    styles = getSampleStyleSheet()

    titulo = Paragraph(
        f"<b>COMASUR SA - RESUMEN {mes}</b>",
        styles["Title"]
    )

    elementos.append(titulo)
    elementos.append(Spacer(1, 20))

    datos = [list(df.columns)] + df.astype(str).values.tolist()

    tabla = Table(datos, repeatRows=1)

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2f3")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
    ]))

    elementos.append(tabla)

    doc.build(elementos)

    buffer.seek(0)

    return buffer


# ------------------------------------------------
# SUBIR PDF
# ------------------------------------------------

archivo_pdf = st.file_uploader(
    "Sube el PDF de nóminas",
    type="pdf"
)

if not archivo_pdf:

    st.info("👆 Sube un PDF multiperiodo")
    st.stop()

# ------------------------------------------------
# ANALIZAR PDF
# ------------------------------------------------

with st.spinner("Analizando PDF..."):

    try:

        pdf = pdfplumber.open(archivo_pdf)

    except Exception as e:

        st.error(f"Error abriendo PDF: {e}")
        st.stop()

    meses_detectados = detectar_meses(pdf)

    if not meses_detectados:

        st.error("❌ No se detectaron meses automáticamente")
        st.stop()

# ------------------------------------------------
# SELECCIÓN MES
# ------------------------------------------------

st.success("✅ Meses detectados correctamente")

meses_lista = list(meses_detectados.keys())

mes_seleccionado = st.selectbox(
    "Selecciona el mes a procesar",
    meses_lista
)

paginas_mes = meses_detectados[mes_seleccionado]

st.write(
    f"📄 Páginas detectadas: "
    f"{', '.join(str(p + 1) for p in paginas_mes)}"
)

# ------------------------------------------------
# EXTRAER DATOS
# ------------------------------------------------

with st.spinner("Extrayendo datos del mes..."):

    datos = extraer_tablas_mes(
        pdf,
        paginas_mes
    )

    if not datos:

        st.error("❌ No se encontraron registros")
        st.stop()

    max_cols = max(len(fila) for fila in datos)

    datos_normalizados = [
        fila + [""] * (max_cols - len(fila))
        for fila in datos
    ]

    columnas = [
        f"Campo_{i+1}"
        for i in range(max_cols)
    ]

    df = pd.DataFrame(
        datos_normalizados,
        columns=columnas
    )

# ------------------------------------------------
# VISUALIZAR
# ------------------------------------------------

st.subheader(
    f"📋 Datos detectados - {mes_seleccionado}"
)

st.dataframe(
    df,
    use_container_width=True
)

# ------------------------------------------------
# GENERAR PDF
# ------------------------------------------------

pdf_generado = generar_pdf(
    df,
    mes_seleccionado
)

st.download_button(
    label="📥 Descargar PDF estructurado",
    data=pdf_generado,
    file_name=f"nominas_{mes_seleccionado.lower()}.pdf",
    mime="application/pdf"
)
