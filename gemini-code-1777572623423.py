import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

st.set_page_config(page_title="Extractor Comasur", page_icon="📊")

st.title("🚀 Extractor de Datos: Resumen Contable")
st.markdown("Sube el PDF para obtener el conteo de empleados e importes totales por sucursal.")

def limpiar_monto(valor):
    """Convierte importes formato '4.916,43' a float 4916.43"""
    if not valor or valor == "None": return 0.0
    s = str(valor).replace('.', '').replace(',', '.')
    # Extraer solo el número por si hay texto pegado
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else 0.0

archivo_pdf = st.file_uploader("Arrastra aquí el archivo PDF", type="pdf")

if archivo_pdf:
    with st.spinner('Procesando datos...'):
        all_rows = []
        with pdfplumber.open(archivo_pdf) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    # En tu PDF, los datos reales empiezan después de la cabecera
                    all_rows.extend(table)

        if all_rows:
            # Creamos el DataFrame. Usamos la primera fila como cabecera.
            df = pd.DataFrame(all_rows[1:], columns=all_rows[0])
            
            # 1. Identificar la columna de Nombres/Centro (la primera)
            col_principal = df.columns[0]
            
            # 2. Limpieza de datos: Eliminar filas vacías o de "Total de la Cuenta"
            df = df.dropna(subset=[col_principal])
            df = df[~df[col_principal].str.contains("Total|Cuenta|Cód", na=False, case=False)]

            # 3. Extraer Sucursal y ANONIMIZAR (borrar nombres)
            # El PDF tiene el centro arriba (ej: COMASUR MOTRIL). Lo extraemos.
            def extraer_sucursal(texto):
                lineas = [l.strip() for l in str(texto).split('\n') if l.strip()]
                for l in lineas:
                    if "MOTRIL" in l.upper() or "COMASUR" in l.upper():
                        return l
                return "CENTRO GENERAL"

            df['Sucursal'] = df[col_principal].apply(extraer_sucursal)
            
            # Borramos la columna original que contiene los nombres de los empleados
            df_anonimo = df.drop(columns=[col_principal])

            # 4. Convertir columnas numéricas (Líquido, Bases, IRPF)
            # Buscamos columnas que contengan estas palabras
            for col in df_anonimo.columns:
                if any(x in col for x in ['Líquido', 'Base', 'IRPF', 'Días']):
                    df_anonimo[col] = df_anonimo[col].apply(limpiar_monto)

            # 5. Agrupación Final
            resumen = df_anonimo.groupby('Sucursal').agg({
                'Sucursal': 'count', # Esto cuenta cuántos empleados hay
                'Líquido': 'sum',
                'Base C.C.': 'sum' if 'Base C.C.' in df_anonimo.columns else df_anonimo.columns[1]: 'sum' 
            }).rename(columns={'Sucursal': 'Nº Empleados'})

            st.success("¡Procesado correctamente!")
            
            # Mostrar tabla en la web
            st.subheader("📊 Resumen por Sucursal")
            st.dataframe(resumen.style.format("{:,.2f} €", subset=['Líquido']))

            # Descarga Excel
            csv = resumen.to_csv(index=True, sep=';', decimal=',').encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte para Excel",
                data=csv,
                file_name="resumen_empleados_sucursal.csv",
                mime="text/csv"
            )