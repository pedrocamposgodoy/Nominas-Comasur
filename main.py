import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import landscape, A4

st.set_page_config(page_title="Nóminas COMASUR", layout="wide")

# =========================
# COLUMNAS REALES
# =========================

COLUMNAS = [
    "Codigo",
    "Apellido_1",
    "Apellido_2",
    "Nombre",
    "Empresa",
    "Centro",
    "Tipo",
    "Dias",
    "Devengado",
    "Base_SS",
    "Base_IRPF",
    "IRPF",
    "Extra_1",
    "Extra_2",
    "Seg_Social",
    "Liquido",
    "Coste_SS",
    "Retencion",
    "Anticipo",
    "Total"
]

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

# =========================
# FUNCIONES
# =========================

def limpiar_texto(texto):
    texto = texto.replace("\n", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()

def es_numero(valor):
    return bool(re.match(r"^[\d\.,]+$", valor))

def extraer_datos(pdf_file):

    registros = []

    with pdfplumber.open(pdf_file) as pdf:

        for pagina in pdf.pages:

            texto = pagina.extract_text()

            if not texto:
                continue

            lineas = texto.split("\n")

            for linea in lineas:

                linea = limpiar_texto(linea)

                if len(linea) < 20:
                    continue

                partes = linea.split()

                if len(partes) < 10:
                    continue

                # Buscar primer número = código trabajador
                if not partes[0].isdigit():
                    continue

                codigo = partes[0]

                # Buscar números monetarios
                numeros = [p for p in partes if es_numero(p)]

                if len(numeros) < 8:
                    continue

                try:

                    apellido_1 = partes[1]
                    apellido_2 = partes[2]
                    nombre = partes[3]

                    empresa = "COMASUR"

                    centro = "MOTRIL"

                    tipo = "Ord"

                    dias = numeros[0]

                    monetarios = numeros[1:]

                    fila = [
                        codigo,
                        apellido_1,
                        apellido_2,
                        nombre,
                        empresa,
                        centro,
                        tipo,
                        dias
                    ]

                    while len(monetarios) < 12:
                        monetarios.append("0,00")

                    fila.extend(monetarios[:12])

                    registros.append(fila)

                except:
                    pass

    if len(registros) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(registros, columns=COLUMNAS)

    return df


def generar_pdf(df, mes):

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=15,
        leftMargin=15,
        topMargin=15,
        bottomMargin=15
    )

    elementos = []

    estilos = getSampleStyleSheet()

    titulo = Paragraph(f"<b>NÓMINAS {mes}</b>", estilos["Title"])

    elementos.append(titulo)
    elementos.append(Spacer(1, 12))

    if df.empty:
        texto = Paragraph("No hay datos para generar el PDF", estilos["BodyText"])
        elementos.append(texto)

        doc.build(elementos)

        buffer.seek(0)

        return buffer

    # Tabla PDF
    data = [list(df.columns)] + df.values.tolist()

    tabla = Table(data, repeatRows=1)

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
    ]))

    elementos.append(tabla)

    doc.build(elementos)

    buffer.seek(0)

    return buffer

# =========================
# INTERFAZ
# =========================

st.title("📋 Gestión Nóminas COMASUR")

mes_seleccionado = st.selectbox(
    "Seleccione mes",
    MESES
)

archivo = st.file_uploader(
    "Suba PDF de nóminas",
    type=["pdf"]
)

if archivo:

    with st.spinner("Procesando PDF..."):

        df = extraer_datos(archivo)

    st.subheader(f"Datos detectados - {mes_seleccionado}")

    if df.empty:

        st.error("No se pudieron extraer datos válidos.")

    else:

        st.dataframe(
            df,
            use_container_width=True,
            height=500
        )

        pdf_generado = generar_pdf(df, mes_seleccionado)

        st.download_button(
            label="📥 Descargar PDF estructurado",
            data=pdf_generado,
            file_name=f"nominas_{mes_seleccionado.lower()}.pdf",
            mime="application/pdf"
        )

        csv = df.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="📥 Descargar CSV",
            data=csv,
            file_name=f"nominas_{mes_seleccionado.lower()}.csv",
            mime="text/csv"
        )
