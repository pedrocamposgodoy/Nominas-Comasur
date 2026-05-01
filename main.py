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
# FUNCIONES
# -------------------------

def limpiar_monto(valor):
    """Convierte un string con formato numérico español a float."""
    if not valor or str(valor).strip() == "":
        return 0.0
    s = str(valor).strip().replace('.', '').replace(',', '.')
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else 0.0


def es_columna_numerica(serie):
    """Devuelve True si la columna contiene principalmente valores numéricos."""
    no_vacias = serie[serie.astype(str).str.strip() != ""]
    if len(no_vacias) == 0:
        return False
    def intenta_numero(v):
        try:
            s = str(v).replace('.', '').replace(',', '.')
            match = re.search(r"[-+]?\d*\.\d+|\d+", s)
            return match is not None
        except Exception:
            return False
    ratio = no_vacias.apply(intenta_numero).mean()
    return ratio > 0.5


def deduplicar_columnas(columnas):
    """Añade sufijo numérico a columnas duplicadas."""
    nuevas = []
    contador = {}
    for col in columnas:
        if col in contador:
            contador[col] += 1
            nuevas.append(f"{col}_{contador[col]}")
        else:
            contador[col] = 0
            nuevas.append(col)
    return nuevas


def identificar_centro(fila_completa):
    """
    Busca el nombre del centro en cualquier celda de la fila.
    Devuelve el nombre del centro o None si no lo reconoce.
    """
    texto = " ".join(str(c) for c in fila_completa).upper()
    if "MOTRIL" in texto:
        return "COMASUR MOTRIL"
    # Añade aquí más centros si los hay, por ejemplo:
    # if "GRANADA" in texto:
    #     return "COMASUR GRANADA"
    return None


# -------------------------
# UI INICIAL
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
    all_data = []

    try:
        with pdfplumber.open(archivo_pdf) as pdf:
            for page in pdf.pages:
                tabla = page.extract_table() or []

                for fila in tabla:
                    if not fila or not any(fila):
                        continue

                    tiene_saltos = any('\n' in str(c) for c in fila if c)

                    if tiene_saltos:
                        lineas = [str(c).split('\n') if c else [""] for c in fila]
                        max_len = max(len(x) for x in lineas)
                        for i in range(max_len):
                            nueva = [x[i].strip() if i < len(x) else "" for x in lineas]
                            if any(nueva):
                                all_data.append(nueva)
                    else:
                        all_data.append([c if c is not None else "" for c in fila])

    except Exception as e:
        st.error(f"Error leyendo el PDF: {e}")
        st.stop()

    if not all_data:
        st.error("No se detectó información procesable en el PDF.")
        st.stop()

    # Homogeneizar longitud de filas
    max_cols = max(len(f) for f in all_data)
    all_data = [f + [""] * (max_cols - len(f)) for f in all_data]

    df = pd.DataFrame(all_data)

    if len(df) <= 1:
        st.error("El PDF no tiene estructura de tabla válida.")
        st.stop()

    # --- Cabecera ---
    df.columns = df.iloc[0].astype(str).str.strip()
    df = df[1:].reset_index(drop=True)

    # Evitar columnas duplicadas
    df.columns = deduplicar_columnas(list(df.columns))

    col_id = df.columns[0]

    # --- Limpieza de filas vacías y totales ---
    df = df[df[col_id].astype(str).str.strip() != ""]
    df = df[~df[col_id].astype(str).str.contains(
        r"Total|Cuenta|Cód|Página", na=False, case=False
    )].reset_index(drop=True)

    if df.empty:
        st.error("No quedaron filas tras el filtrado. Revisa el formato del PDF.")
        st.stop()

    # --- Detectar columnas numéricas ANTES de eliminar col_id ---
    # (excluir col_id que es texto identificador)
    cols_restantes = [c for c in df.columns if c != col_id]
    cols_numericas = [c for c in cols_restantes if es_columna_numerica(df[c])]
    cols_texto_extra = [c for c in cols_restantes if c not in cols_numericas]

    # --- Asignar Sucursal buscando en toda la fila ---
    df["Sucursal"] = df.apply(
        lambda row: identificar_centro(row.tolist()), axis=1
    )
    df["Sucursal"] = df["Sucursal"].ffill().fillna("OTRO CENTRO")

    # --- Eliminar columnas de texto que no aportan datos numéricos ---
    cols_a_eliminar = [col_id] + cols_texto_extra
    df_final = df.drop(columns=[c for c in cols_a_eliminar if c in df.columns])

    # --- Convertir columnas numéricas a float ---
    for col in cols_numericas:
        if col in df_final.columns:
            df_final[col] = df_final[col].apply(limpiar_monto)

    # --- Filtrar empleados con al menos un valor distinto de cero ---
    cols_num_final = [c for c in df_final.columns if c != "Sucursal"]

    if not cols_num_final:
        st.error("No se encontraron columnas numéricas en el documento.")
        st.stop()

    df_empleados = df_final[
        df_final[cols_num_final].abs().sum(axis=1) > 0
    ].copy()

    if df_empleados.empty:
        st.error("No se detectaron empleados con datos numéricos.")
        st.stop()

    # --- Resumen por sucursal ---
    resumen = df_empleados.groupby("Sucursal")[cols_num_final].sum()
    resumen.insert(0, "Nº Empleados", df_empleados.groupby("Sucursal").size())

# -------------------------
# RESULTADOS
# -------------------------

st.success("✅ Procesamiento completado")

c1, c2 = st.columns(2)
c1.metric("Total Empleados", int(resumen["Nº Empleados"].sum()))

# Buscar columna de líquido a pagar
col_liq = next(
    (c for c in resumen.columns if isinstance(c, str) and "LIQUIDO" in c.upper()),
    None
)
if col_liq:
    total_liq = resumen[col_liq].sum()
    c2.metric("Total Líquido", f"{total_liq:,.2f} €")

st.subheader("📋 Totales Agregados por Sucursal")

# Formatear solo columnas monetarias (float), no "Nº Empleados" (int)
cols_moneda = [c for c in resumen.columns if c != "Nº Empleados"]

# Aplicar formato: moneda para floats, entero para Nº Empleados
fmt = {c: "{:,.2f} €" for c in cols_moneda}
fmt["Nº Empleados"] = "{:,.0f}"

st.dataframe(resumen.style.format(fmt))

# Descargar CSV
csv = resumen.to_csv(index=True, sep=";", decimal=",").encode("utf-8-sig")
st.download_button(
    label="📥 Descargar CSV",
    data=csv,
    file_name="resumen_nominas.csv",
    mime="text/csv"
)

# Detalle por sucursal (expandible)
with st.expander("🔍 Ver detalle de empleados por sucursal"):
    for sucursal in df_empleados["Sucursal"].unique():
        st.markdown(f"**{sucursal}**")
        subset = df_empleados[df_empleados["Sucursal"] == sucursal][cols_num_final]
        st.dataframe(subset.style.format("{:,.2f} €"))
