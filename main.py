import streamlit as st
import pandas as pd
import pdfplumber
import re

# Configuración de la interfaz
st.set_page_config(page_title="Extractor Comasur", page_icon="📊", layout="wide")

st.title("📊 Extractor de Nóminas: Comasur SA")
st.markdown("Procesa el resumen contable, anonimiza nombres y agrupa totales.")

def limpiar_monto(valor):
    """Limpia los números, incluyendo posibles errores de OCR en el PDF."""
    if not valor or str(valor).strip() == "":
        return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else 0.0

archivo_pdf = st.file_uploader("Sube el PDF de Resumen Contable", type="pdf")

if archivo_pdf:
    with st.spinner('Procesando documento...'):
        all_data = []

        try:
            with pdfplumber.open(archivo_pdf) as pdf:
                for page in pdf.pages:
                    tabla = page.extract_table() or []

                    for fila in tabla:
                        if any(fila):
                            # Separar celdas con saltos de línea
                            tiene_saltos = any('\n' in str(c) for c in fila if c)

                            if tiene_saltos:
                                lineas = [str(c).split('\n') if c else [""] for c in fila]
                                max_len = max(len(x) for x in lineas)

                                for i in range(max_len):
                                    nueva = [x[i].strip() if i < len(x) else "" for x in lineas]
                                    if any(nueva):
                                        all_data.append(nueva)
                            else:
                                all_data.append(fila)

        except Exception as e:
            st.error(f"Error leyendo el PDF: {e}")
            st.stop()

        if not all_data:
            st.error("No se detectó información procesable. Revisa el documento.")
            st.stop()

        # DataFrame
        df = pd.DataFrame(all_data)

        if len(df) <= 1:
            st.error("El PDF no tiene estructura válida.")
            st.stop()

        # Cabecera
        df.columns = df.iloc[0].astype(str)
        df = df[1:]

        # Evitar columnas duplicadas
        df.columns = pd.io.parsers.ParserBase({'names': df.columns})._maybe_dedup_names(df.columns)

        col_id = df.columns[0]

        # Limpieza
        df = df[df[col_id].astype(str).str.strip() != ""]
        df = df[~df[col_id].astype(str).str.contains(r"Total|Cuenta|Cód|Página", na=False, case=False)]

        # Detectar sucursal
        def identificar_centro(texto):
            texto = str(texto).upper()
            if "MOTRIL" in texto:
                return "COMASUR MOTRIL"
            return None

        df['Sucursal'] = df[col_id].apply(identificar_centro)
        df['Sucursal'] = df['Sucursal'].ffill().fillna("OTRO CENTRO")

        # Quitar datos personales
        df_final = df.drop(columns=[col_id])

        # Limpiar números
        for col in df_final.columns:
            if col != 'Sucursal':
                df_final[col] = df_final[col].apply(limpiar_monto)

        cols_numericas = [c for c in df_final.columns if c != 'Sucursal']

        # Detectar empleados correctamente
        df_empleados = df_final[(df_final[cols_numericas].abs().sum(axis=1) > 0)].copy()

        if df_empleados.empty:
            st.error("No se han detectado empleados correctamente.")
            st.stop()

        resumen = df_empleados.groupby('Sucursal').agg('sum')
        resumen['Nº Empleados'] = df_empleados.groupby('Sucursal').size()

        # UI
        st.success("✅ Procesamiento completado")

        c1, c2 = st.columns(2)
        c1.metric("Total Empleados", int(resumen['Nº Empleados'].sum()))

        col_liq = [c for c in resumen.columns if isinstance(c, str) and 'LIQUIDO' in c.upper()]
        if col_liq:
            total_liq = resumen[col_liq[0]].sum()
            c2.metric("Total Líquido", f"{total_liq:,.2f} €")

        st.subheader("📋 Totales Agregados")

        cols_moneda = [c for c in resumen.columns if c != 'Nº Empleados']
        st.dataframe(resumen.style.format("{:,.2f} €", subset=cols_moneda))

        # Descargar
        csv = resumen.to_csv(index=True, sep=';', decimal=',').encode('utf-8-sig')
        st.download_button("📥 Descargar CSV", csv, "resumen_corregido.csv", "text/csv")
