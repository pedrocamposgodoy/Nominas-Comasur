import streamlit as st
import pandas as pd
import pdfplumber
import re

# -------------------------
# CONFIGURACIÓN
# -------------------------
st.set_page_config(page_title="Extractor Comasur", page_icon="📊", layout="wide")
st.title("📊 Extractor de Nóminas: Comasur SA")

# -------------------------
# CONSTANTES
# -------------------------

# Nombres de columnas numéricas en el orden en que aparecen en el PDF
COLUMNAS_NUMERICAS = [
    "Base C.C.",
    "Base C.P.",
    "Base IRPF",
    "Deducción C.C.",
    "Valor Especie",
    "Otras Deducciones",
    "Coste Cot. Empresa",
    "Retribuciones",
    "Retención IRPF",
    "Otras Retenciones",
    "Líquido",
]

# Expresión regular para detectar una fila de empleado:
# cod  APELLIDO, NOMBRE  CENTRO  (Ord|Ext)  dias  num num num...
PATRON_EMPLEADO = re.compile(
    r"^(\d+)\s+"                               # código trabajador
    r"([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ ,\.]+?)\s+"    # nombre en mayúsculas
    r"(COMASUR\s+\w+(?:\s+\w+)?)\s+"           # centro (ej. COMASUR MOTRIL)
    r"(Ord|Ext)\s+"                            # tipo de jornada
    r"(\d+)\s+"                                # días
    r"([\d\.,]+(?:\s+[\d\.,]+)*)\s*$"          # números al final
)


# -------------------------
# FUNCIONES
# -------------------------

def limpiar_monto(valor_str):
    """Convierte string numérico en formato español (1.234,56) a float."""
    s = str(valor_str).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parsear_fila_empleado(texto):
    """
    Intenta extraer los datos de un empleado de una línea de texto.
    Devuelve un dict con los campos o None si la línea no es de empleado.
    """
    m = PATRON_EMPLEADO.match(texto.strip())
    if not m:
        return None

    codigo   = m.group(1)
    nombre   = m.group(2).strip().rstrip(",").strip()
    centro   = m.group(3).strip()
    tipo     = m.group(4)
    dias     = int(m.group(5))
    nums_str = m.group(6).split()

    if len(nums_str) != len(COLUMNAS_NUMERICAS):
        # Si el número de valores no cuadra, ignorar la fila
        return None

    fila = {
        "Código":  codigo,
        "Nombre":  nombre,
        "Centro":  centro,
        "Tipo":    tipo,
        "Días":    dias,
    }
    for col, val in zip(COLUMNAS_NUMERICAS, nums_str):
        fila[col] = limpiar_monto(val)

    return fila


def extraer_empleados_pdf(archivo):
    """
    Lee el PDF y devuelve una lista de dicts, uno por fila de empleado.
    """
    empleados = []

    with pdfplumber.open(archivo) as pdf:
        for page in pdf.pages:
            texto = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            for linea in texto.splitlines():
                linea = linea.strip()
                if not linea:
                    continue
                resultado = parsear_fila_empleado(linea)
                if resultado:
                    empleados.append(resultado)

    return empleados


# -------------------------
# UI
# -------------------------

st.markdown("Sube el PDF de resumen contable para procesarlo.")
archivo_pdf = st.file_uploader("Subir PDF", type="pdf")

if not archivo_pdf:
    st.info("👆 Sube un PDF para comenzar")
    st.stop()

# -------------------------
# PROCESAMIENTO
# -------------------------

with st.spinner("Procesando documento..."):
    try:
        empleados = extraer_empleados_pdf(archivo_pdf)
    except Exception as e:
        st.error(f"Error leyendo el PDF: {e}")
        st.stop()

    if not empleados:
        st.error(
            "No se detectaron empleados en el documento. "
            "Comprueba que el PDF es un Resumen Contable de Comasur."
        )
        st.stop()

    df = pd.DataFrame(empleados)

# -------------------------
# RESULTADOS
# -------------------------

st.success(f"✅ Procesamiento completado — {df['Nombre'].nunique()} empleados detectados")

# ---- Tabla de totales ----
st.subheader("📋 Totales del período")

totales = df[list(COLUMNAS_NUMERICAS)].sum().rename("Total")
totales["Nº Empleados"] = df["Nombre"].nunique()

tabla = totales.to_frame().T.set_index("Nº Empleados")

fmt = {c: "{:,.2f} €" for c in COLUMNAS_NUMERICAS}
st.dataframe(tabla.style.format(fmt), use_container_width=True)

# ---- Descarga ----
csv = totales.to_frame("Total").to_csv(sep=";", decimal=",").encode("utf-8-sig")
st.download_button("📥 Descargar totales (CSV)", csv, "totales.csv", "text/csv")
