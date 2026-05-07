# 📄 main.py

```python
import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# -------------------------
# CONFIG
# -------------------------

st.set_page_config(
    page_title="Extractor Nóminas Comasur",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Extractor Inteligente de Nóminas")
st.markdown("Detecta meses automáticamente y genera PDFs estructurados")

# -------------------------
# FUNCIONES
# -------------------------

MESES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"
]


def limpiar_monto(valor):
    if not valor:
        return valor

    texto = str(valor).strip()

    if texto == "":
        return valor

    texto = texto.replace('.', '').replace(',', '.')

    match = re.search(r"[-+]?\d*\.\d+|\d+", texto)

    if match:
        try:
            return float(match.group())
        except:
            return valor

    return valor



def detectar_meses(pdf):
    meses_detectados = {}

    for i, page in enumerate(pdf.pages):
        texto = page.extract_text()

        if not texto:
            continue

        texto_upper = texto.upper()

        for mes in MESES:
            if mes in texto_upper:
                clave = mes

                if clave not in meses_detectados:
                    meses_detectados[clave] = []

                meses_detectados[clave].append(i)

    return meses_detectados



def extraer_tablas_mes(pdf, paginas):
    all_data = []

    for pagina_num in paginas:
        page = pdf.pages[pagina_num]

        tabla = page.extract_table()

        if tabla:
            for fila in tabla:
                if fila and any(fila):
                    all_data.append(fila)

    return all_data



def deduplicar_columnas(cols):
    nuevas = []
    contador = {}

    for col in cols:
        col = str(col)

        if col in contador:
            contador[col] += 1
            nuevas.append(f"{col}_{contador[col]}")
        else:
            contador[col] = 0
            nuevas.append(col)

    return nuevas



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
        styles['Title']
    )

    elementos.append(titulo)
    elementos.append(Spacer(1, 20))

    datos = [list(df.columns)] + df.astype(str).values.tolist()

    tabla = Table(datos, repeatRows=1)

    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d9e2f3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
    ]))

    elementos.append(tabla)

    doc.build(elementos)

    buffer.seek(0)

    return buffer


# -------------------------
# UI
# -------------------------

archivo_pdf = st.file_uploader(
    "Sube el PDF de nóminas",
    type="pdf"
)

if not archivo_pdf:
    st.info("👆 Sube un PDF multiperiodo")
    st.stop()


# -------------------------
# PROCESAR PDF
# -------------------------

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


# -------------------------
# SELECCIÓN MES
# -------------------------

st.success("✅ Meses detectados correctamente")

meses_lista = list(meses_detectados.keys())

mes_seleccionado = st.selectbox(
    "Selecciona el mes a procesar",
    meses_lista
)

paginas_mes = meses_detectados[mes_seleccionado]

st.write(f"📄 Páginas detectadas: {', '.join(str(p + 1) for p in paginas_mes)}")


# -------------------------
# EXTRAER TABLAS
# -------------------------

with st.spinner("Extrayendo tablas del mes..."):

    datos = extraer_tablas_mes(pdf, paginas_mes)

    if not datos:
        st.error("❌ No se detectaron tablas")
        st.stop()

    df = pd.DataFrame(datos)

    if len(df) < 2:
        st.error("❌ No hay estructura suficiente")
        st.stop()

    df.columns = df.iloc[0].astype(str)
    df = df[1:]

    df.columns = deduplicar_columnas(df.columns)

    df = df.dropna(how='all')

    # Limpiar números donde sea posible
    for col in df.columns:
        df[col] = df[col].apply(limpiar_monto)


# -------------------------
# VISUALIZAR
# -------------------------

st.subheader(f"📋 Datos detectados - {mes_seleccionado}")

st.dataframe(df, use_container_width=True)


# -------------------------
# GENERAR PDF
# -------------------------

pdf_generado = generar_pdf(df, mes_seleccionado)

st.download_button(
    label="📥 Descargar PDF estructurado",
    data=pdf_generado,
    file_name=f"nominas_{mes_seleccionado.lower()}.pdf",
    mime="application/pdf"
)
```

---

# 📄 requirements.txt

```txt
streamlit==1.35.0
pandas==2.2.2
pdfplumber==0.11.4
reportlab==4.2.0
Pillow
```

---

# 📄 runtime.txt

```txt
python-3.11
```

---

# 📄 .gitignore

```txt
*.pyc
__pycache__/
.streamlit/
.env
venv/
```

---

# 🚀 ESTRUCTURA FINAL DEL REPO

```text
/nominas-comasur
│
├── main.py
├── requirements.txt
├── runtime.txt
├── .gitignore
```

---

# ✅ QUÉ HACE ESTA VERSIÓN

* Detecta automáticamente los meses del PDF
* Permite elegir el mes
* Extrae solo ese bloque
* Mantiene las columnas originales
* Genera un PDF estructurado profesional
* Compatible con Streamlit Cloud
* Compatible con Python 3.11
