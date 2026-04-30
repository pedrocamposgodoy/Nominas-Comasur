import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# Configuración de la página
st.set_page_config(page_title="Extractor Comasur", page_icon="📊", layout="wide")

st.title("🚀 Extractor de Datos: Resumen Contable")
st.markdown("""
Esta herramienta extrae los datos de los empleados, **elimina sus nombres por privacidad** y suma los totales agrupados por cada sucursal detectada en el PDF.
""")

def limpiar_monto(valor):
    """Convierte importes formato europeo '4.916,43' a float 4916.43"""
    if not valor or valor == "None" or str(valor).strip() == "": 
        return 0.0
    # Quitamos puntos de miles y cambiamos coma decimal por punto
    s = str(valor).replace('.', '').replace(',', '.')
    # Extraemos solo los números y el punto decimal
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else 0.0

def extraer_sucursal(texto):
    """Limpia el texto de la celda para extraer el nombre de la sucursal/centro"""
    lineas = [l.strip() for l in str(texto).split('\n') if l.strip()]
    # Si detecta palabras clave, asumimos que esa línea es la sucursal
    for l in lineas:
        if any(keyword in l.upper() for keyword in ["MOTRIL", "COMASUR", "CENTRO"]):
            return l
    return "CENTRO GENERAL"

archivo_pdf = st.file_uploader("Arrastra aquí el archivo PDF de Comasur", type="pdf")

if archivo_pdf:
    with st.spinner('Procesando y anonimizando datos...'):
        all_rows = []
        try:
            with pdfplumber.open(archivo_pdf) as pdf:
                for page in pdf.pages:
                    table = page.extract_table()
                    if table:
                        all_rows.extend(table)
        except Exception as e:
            st.error(f"Error al leer el PDF: {e}")

        if all_rows:
            # Creamos el DataFrame usando la primera fila como cabecera
            df = pd.DataFrame(all_rows[1:], columns=all_rows[0])
            
            # 1. Identificar la columna principal (Nombres y Centro)
            col_principal = df.columns[0]
            
            # 2. Limpieza: Eliminar filas de totales acumulados del PDF y vacíos
            df = df.dropna(subset=[col_principal])
            df = df[~df[col_principal].str.contains("Total|Cuenta|Cód|Página", na=False, case=False)]

            # 3. Anonimización y extracción de Centro
            # Creamos la columna Sucursal y ELIMINAMOS la columna original con los nombres
            df['Sucursal'] = df[col_principal].apply(extraer_sucursal)
            df_anonimo = df.drop(columns=[col_principal])

            # 4. Limpieza de números en todas las columnas excepto la nueva 'Sucursal'
            for col in df_anonimo.columns:
                if col != 'Sucursal':
                    df_anonimo[col] = df_anonimo[col].apply(limpiar_monto)

            # 5. Configurar la Agrupación (Detección inteligente de columnas)
            # Queremos contar empleados y sumar valores económicos
            dict_agregacion = {'Sucursal': 'count'} 
            
            for col in df_anonimo.columns:
                c_up = col.upper()
                # Sumamos cualquier columna que parezca económica o de días
                if any(k in c_up for k in ['LÍQUIDO', 'LIQUIDO', 'BASE', 'IRPF', 'DÍAS', 'DIAS', 'TOTAL']):
                    dict_agregacion[col] = 'sum'

            # Ejecutar la suma por sucursal
            resumen = df_anonimo.groupby('Sucursal').agg(dict_agregacion)
            
            # Renombrar para que sea más claro
            resumen = resumen.rename(columns={'Sucursal': 'Nº Empleados'})

            # --- INTERFAZ DE RESULTADOS ---
            st.success("¡Análisis completado con éxito!")
            
            # Métricas rápidas
            col1, col2 = st.columns(2)
            col1.metric("Total Empleados", int(resumen['Nº Empleados'].sum()))
            
            col_liquido = [c for c in resumen.columns if 'LIQUIDO' in c.upper()]
            if col_liquido:
                total_dinero = resumen[col_liquido[0]].sum()
                col2.metric("Total Líquido", f"{total_dinero:,.2f} €")

            # Mostrar la tabla final
            st.subheader("📊 Totales Agregados por Sucursal")
            # Aplicamos formato moneda a las columnas numéricas
            cols_dinero = [c for c in resumen.columns if c != 'Nº Empleados']
            st.dataframe(resumen.style.format("{:,.2f} €", subset=cols_dinero))

            # Botón de descarga para Excel/CSV
            csv = resumen.to_csv(index=True, sep=';', decimal=',').encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte Agrupado (Excel)",
                data=csv,
                file_name="resumen_contable_agrupado.csv",
                mime="text/csv"
            )
        else:
            st.warning("No se detectaron tablas en el PDF. Asegúrate de que no es un PDF escaneado como imagen.")
