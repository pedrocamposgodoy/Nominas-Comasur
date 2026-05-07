import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import landscape, A4

st.set_page_config(page_title="Nóminas COMASUR", layout="wide")

MESES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL",
    "MAYO", "JUNIO", "JULIO", "AGOSTO",
    "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
]

COLUMNAS = [
    "Código",
    "Apellidos",
    "Nombre",
    "Empresa",
    "Centro",
    "Tipo",
    "Días",
    "Devengo",
    "Base",
    "Cotización",
    "SS",
    "IRPF",
    "Otros",
    "Líquido"
]

st.title("📄 Analizador de Nóminas COMASUR")

uploaded_file = st.file_uploader(
    "Sube PDF de nóminas",
    type="pdf"
)

def extraer_texto(pdf_file):
    texto = ""

    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            contenido = pagina.extract_text()
            if contenido:
                texto += contenido + "\n"

    return texto

def detectar_meses(texto):
    encontrados = []

    for mes in MESES:
        if mes in texto.upper():
            encontrados.append(mes)

    return list(dict.fromkeys(encontrados))

def extraer_bloque_mes(texto, mes):
    texto = texto.upper()

    inicio = texto.find(mes)

    if inicio == -1:
        return ""

    siguiente = len(texto)

    for m in MESES:
        if m == mes:
            continue

        pos = texto.find(m, inicio + 10)

        if pos != -1 and pos < siguiente:
            siguiente = pos

    return texto[inicio:siguiente]

def es_numero(valor):
    return bool(re.match(r"^\d+[.,]?\d*$", valor))

def parsear_linea(linea):

    linea = re.sub(r"\s+", " ", linea).strip()

    partes = linea.split()

    if len(partes) < 15:
        return None

    if not partes[0].isdigit():
        return None

    try:

        codigo = partes[0]

        tipo_idx = None

        for i, p in enumerate(partes):
            if p in ["ORD", "EXT"]:
                tipo_idx = i
                break

        if tipo_idx is None:
            return None

        empresa = partes[tipo_idx - 2]
        centro = partes[tipo_idx - 1]

        nombre_partes = partes[1:tipo_idx - 2]

        if len(nombre_partes) < 2:
            return None

        apellidos = " ".join(nombre_partes[:-1])
        nombre = nombre_partes[-1]

        tipo = partes[tipo_idx]

        dias = partes[tipo_idx + 1]

        numeros = partes[tipo_idx + 2:]

        numeros = [n for n in numeros if re.search(r"\d", n)]

        if len(numeros) < 10:
            return None

        fila = {
            "Código": codigo,
            "Apellidos": apellidos,
            "Nombre": nombre,
            "Empresa": empresa,
            "Centro": centro,
            "Tipo": tipo,
            "Días": dias,
            "Devengo": numeros[0],
            "Base": numeros[1],
            "Cotización": numeros[2],
            "SS": numeros[3],
            "IRPF": numeros[6],
            "Otros": numeros[8],
            "Líquido": numeros[-1]
        }

        return fila

    except:
        return None

def extraer_datos(texto_mes):

    filas = []

    lineas = texto_mes.split("\n")

    for linea in lineas:

        fila = parsear_linea(linea)

        if fila:
            filas.append(fila)

    df = pd.DataFrame(filas)

    return df

def generar_pdf(df, mes):

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4)
    )

    elementos = []

    styles = getSampleStyleSheet()

    titulo = Paragraph(
        f"<b>COMASUR SA - RESUMEN {mes}</b>",
        styles["Heading1"]
    )

    elementos.append(titulo)
    elementos.append(Spacer(1, 12))

    data = [df.columns.tolist()] + df.values.tolist()

    tabla = Table(data)

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
    ]))

    elementos.append(tabla)

    doc.build(elementos)

    pdf = buffer.getvalue()
    buffer.close()

    return pdf

if uploaded_file:

    texto = extraer_texto(uploaded_file)

    meses = detectar_meses(texto)

    if not meses:
        st.error("No se detectaron meses")
        st.stop()

    mes_seleccionado = st.selectbox(
        "Selecciona mes",
        meses
    )

    bloque_mes = extraer_bloque_mes(texto, mes_seleccionado)

    df = extraer_datos(bloque_mes)

    st.subheader(f"📋 Datos detectados - {mes_seleccionado}")

    st.dataframe(df, use_container_width=True)

    pdf = generar_pdf(df, mes_seleccionado)

    st.download_button(
        "📥 Descargar PDF estructurado",
        data=pdf,
        file_name=f"nominas_{mes_seleccionado.lower()}.pdf",
        mime="application/pdf"
    )
