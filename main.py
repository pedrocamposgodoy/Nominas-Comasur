import streamlit as st
import pandas as pd
import pdfplumber
import re

# Configuración de la interfaz
st.set_page_config(page_title="Extractor Comasur", page_icon="📊", layout="wide")

st.title("📊 Extractor de Nóminas: Comasur SA")
st.markdown("Esta aplicación extrae datos del resumen contable, **anonimiza los nombres** y agrupa los totales por sucursal.")

def limpiar_monto(valor):
    """Convierte texto como '4.916,43' en número 4916.43"""
    if not valor or str(valor).strip() == "": return 0.0
    # Quitamos puntos de miles y cambiamos coma por punto decimal
    s = str(valor).replace('.', '').replace(',', '.')
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else 0.0

def extraer_sucursal(texto):
    """Detecta la sucursal ignorando los nombres de los empleados"""
    lineas = [l.strip() for l in str(texto).split('\n') if l.strip()]
    for l in lineas:
        if any(centro in l.upper() for centro in ["MOTRIL", "COMASUR", "CENTRO"]):
            return l
    return "CENTRO GENERAL"

archivo_pdf = st.file_uploader("Sube el PDF de Resumen Contable", type="pdf")

if archivo_pdf:
    with st.spinner('Analizando documento y anonimizando...'):
        all_data = []
        with pdfplumber.open(archivo_pdf) as pdf:
            for page in pdf.pages:
                tabla = page.extract_table()
                if tabla:
                    all_data.extend(tabla)

    if all_data:
        # Creamos la tabla inicial
        df = pd.DataFrame(all_data[1:], columns=all_data[0])
        col_id = df.columns[0] # Es la columna "Cód. Nombre / Centro"

        # 1. Limpieza de filas innecesarias (totales del PDF, vacíos, cabeceras)
        df = df.dropna(subset=[col_id])
        df = df[~df[col_id].str.contains("Total|Cuenta|Cód|Página", na=False, case=False)]

        # 2. Anonimización: Extraemos la sucursal y borramos la columna de nombres
        df['Sucursal'] = df[col_id].apply(extraer_sucursal)
        df_final = df.drop(columns=[col_id])

        # 3. Conversión de todas las columnas numéricas
        for col in df_final.columns:
            if col != 'Sucursal':
                df_final[col] = df_final[col].apply(limpiar_monto)

        # 4. Agrupación por Sucursal (Suma totales y cuenta empleados)
        dict_agg = {'Sucursal': 'count'}
        for col in df_final.columns:
            if col != 'Sucursal':
                dict_agg[col] = 'sum'
        
        resumen = df_final.groupby('Sucursal').agg(dict_agg).rename(columns={'Sucursal': 'Nº Empleados'})

        # --- MOSTRAR RESULTADOS ---
        st.success("✅ Procesamiento completado")
        
        # Métricas principales
        c1, c2 = st.columns(2)
        c1.metric("Total Empleados", int(resumen['Nº Empleados'].sum()))
        
        # Buscar columna de líquido para la métrica
        col_liq = [c for c in resumen.columns if 'LÍQUIDO' in c.upper() or 'LIQUIDO' in c.upper()]
        if col_liq:
            c2.metric("Total Líquido", f"{resumen[col_liq[0]].sum():,.2f} €")

        # Tabla resumen
        st.subheader("📋 Totales Agregados por Centro")
        cols_moneda = [c for c in resumen.columns if c != 'Nº Empleados']
        st.dataframe(resumen.style.format("{:,.2f} €", subset=cols_moneda))

        # Botón de descarga para Excel
        csv = resumen.to_csv(index=True, sep=';', decimal=',').encode('utf-8-sig')
        st.download_button("📥 Descargar Reporte para Excel", csv, "resumen_comasur.csv", "text/csv")
