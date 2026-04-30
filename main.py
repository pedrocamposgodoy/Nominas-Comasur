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
    if not valor or str(valor).strip() == "": return 0.0
    # Reemplazar puntos de miles y comas por formato decimal de Python
    s = str(valor).replace('.', '').replace(',', '.')
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else 0.0

archivo_pdf = st.file_uploader("Sube el PDF de Resumen Contable", type="pdf")

if archivo_pdf:
    with st.spinner('Desempaquetando la estructura interna del documento...'):
        all_data = []
        with pdfplumber.open(archivo_pdf) as pdf:
            for page in pdf.pages:
                tabla = page.extract_table()
                if tabla:
                    # Aplanar celdas con saltos de línea (\n)
                    for fila in tabla:
                        tiene_saltos = any('\n' in str(celda) for celda in fila if celda)
                        if tiene_saltos:
                            lineas_por_celda = [str(celda).split('\n') if celda else [] for celda in fila]
                            max_lineas = max((len(lineas) for lineas in lineas_por_celda), default=0)
                            for i in range(max_lineas):
                                nueva_fila = [lineas[i].strip() if i < len(lineas) else "" for lineas in lineas_por_celda]
                                if any(nueva_fila):
                                    all_data.append(nueva_fila)
                        else:
                            if any(fila):
                                all_data.append(fila)

        if all_data:
            # 1. Convertir a DataFrame y configurar cabeceras
            df = pd.DataFrame(all_data)
            df.columns = df.iloc[0].astype(str)
            df = df[1:]
            
            col_id = df.columns[0] # Corresponde a "Cód. Nombre / Centro"

            # 2. Eliminar basura técnica del PDF
            df = df[df[col_id].astype(str).str.strip() != ""]
            df = df[~df[col_id].astype(str).str.contains("Total|Cuenta|Cód|Página", na=False, case=False)]

            # 3. Detectar la sucursal y propagarla hacia abajo
            def identificar_centro(texto):
                if "MOTRIL" in str(texto).upper(): return "COMASUR MOTRIL"
                return None

            df['Sucursal'] = df[col_id].apply(identificar_centro)
            df['Sucursal'] = df['Sucursal'].ffill().fillna("OTRO CENTRO")

            # 4. ANONIMIZACIÓN: Eliminamos los nombres e IDs
            df_final = df.drop(columns=[col_id])

            # 5. Limpieza de datos numéricos
            for col in df_final.columns:
                if col != 'Sucursal':
                    df_final[col] = df_final[col].apply(limpiar_monto)

            # 6. Agrupación y Suma de Totales
            cols_numericas = [c for c in df_final.columns if c != 'Sucursal']
            df_empleados = df_final[(df_final[cols_numericas] > 0).any(axis=1)].copy()

            resumen = df_empleados.groupby('Sucursal').agg('sum')
            resumen['Nº Empleados'] = df_empleados.groupby('Sucursal').size()

            # --- VISUALIZACIÓN ---
            st.success("✅ Procesamiento completado con éxito")
            
            c1, c2 = st.columns(2)
            c1.metric("Total Empleados", int(resumen['Nº Empleados'].sum()))
            
            # SOLUCIÓN APLICADA AQUÍ: str(c) asegura que no dé error si la columna no tiene nombre de texto
            col_liq = [c for c in resumen.columns if 'LÍQUIDO' in str(c).upper() or 'LIQUIDO' in str(c).upper()]
            if col_liq:
                c2.metric("Total Líquido", f"{resumen[col_liq[0]].sum():,.2f} €")

            st.subheader("📋 Totales Agregados")
            cols_moneda = [c for c in resumen.columns if c != 'Nº Empleados']
            st.dataframe(resumen.style.format("{:,.2f} €", subset=cols_moneda))

            # Descarga de resultados
            csv = resumen.to_csv(index=True, sep=';', decimal=',').encode('utf-8-sig')
            st.download_button("📥 Descargar Excel Agrupado", csv, "resumen_corregido.csv", "text/csv")
        else:
            st.error("No se detectó información procesable. Revisa el documento.")
            
