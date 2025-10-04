import json
import math
import pandas as pd
import streamlit as st

# ====== Configuración de la página ======
st.set_page_config(page_title="Paletización Fachada", page_icon="📦", layout="wide")

# ====== Carga de reglas desde JSON ======
@st.cache_data
def cargar_reglas(path="reglas_fachada.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

try:
    reglas = cargar_reglas("reglas_fachada.json")
except FileNotFoundError:
    st.error("No se encontró el archivo 'reglas_fachada.json' en la misma carpeta que app.py.")
    st.stop()

UMBRAL = int(reglas.get("threshold_mm", 3000))  # 3000 mm por defecto
LE = {int(k): int(v) for k, v in reglas["fachada"]["le"].items()}  # ≤ umbral
GT = {int(k): int(v) for k, v in reglas["fachada"]["gt"].items()}  # > umbral

# ====== Encabezado ======
st.title("📦 Paletización de Paneles — Fachada (PRT/PRO)")
st.caption("Introduce las líneas del pedido. Si rellenas **Unidades por paquete (opcional)**, "
           "se usarán para **todos los paquetes** (el último puede quedar incompleto).")

# ====== Barra lateral (solo info de reglas) ======
with st.sidebar:
    st.header("Reglas de empaquetado")
    st.write(f"**Umbral de longitud:** {UMBRAL} mm")
    st.write("**Máximos permitidos (≤ umbral):**")
    st.json(LE, expanded=False)
    st.write("**Máximos permitidos (> umbral):**")
    st.json(GT, expanded=False)

# ====== Datos de ejemplo ======
ejemplo = pd.DataFrame([
    {"Referencia": "FACH-001", "Ancho (mm)": 1000, "Largo (mm)": 2950, "Espesor (mm)": 40,  "Cantidad total": 120, "Unidades por paquete (opcional)": None},
    {"Referencia": "FACH-002", "Ancho (mm)": 1000, "Largo (mm)": 3200, "Espesor (mm)": 100, "Cantidad total": 100, "Unidades por paquete (opcional)": 12},
])

# ====== Botones de utilidad ======
c1, c2, c3, c4 = st.columns([1,1,1,3])
if "tabla" not in st.session_state:
    st.session_state.tabla = ejemplo.copy()

with c1:
    if st.button("➕ Añadir fila"):
        st.session_state.tabla.loc[len(st.session_state.tabla)] = {col: None for col in st.session_state.tabla.columns}
with c2:
    if st.button("🧹 Reiniciar tabla"):
        st.session_state.tabla = ejemplo.copy()
with c3:
    if st.button("💾 Guardar como CSV"):
        st.download_button(
            "Descargar CSV (datos de entrada)",
            st.session_state.tabla.to_csv(index=False).encode("utf-8"),
            file_name="pedido_entrada.csv",
            mime="text/csv",
            use_container_width=True
        )

st.markdown("### 📝 Líneas del pedido")
df = st.data_editor(
    st.session_state.tabla,
    num_rows="dynamic",
    use_container_width=True,
    key="editor",
    column_config={
        "Referencia": st.column_config.TextColumn("Referencia", help="Código o nombre del pedido"),
        "Ancho (mm)": st.column_config.NumberColumn("Ancho (mm)", step=1),
        "Largo (mm)": st.column_config.NumberColumn("Largo (mm)", step=1, help=f"Decide si usa ≤ {UMBRAL} mm o > {UMBRAL} mm"),
        "Espesor (mm)": st.column_config.NumberColumn("Espesor (mm)", step=1, help="Debe existir en la tabla de reglas"),
        "Cantidad total": st.column_config.NumberColumn("Cantidad total", step=1),
        "Unidades por paquete (opcional)": st.column_config.NumberColumn("Unidades por paquete (opcional)", step=1, help="Si lo rellenas, se usa para todos los paquetes"),
    }
)

# Mantener sincronizada la tabla en sesión
st.session_state.tabla = df.copy()

# ====== Funciones de cálculo ======
def max_permitido_por_linea(espesor: int, largo: int):
    if pd.isna(espesor) or pd.isna(largo):
        return None
    tabla = LE if int(largo) <= UMBRAL else GT
    return tabla.get(int(espesor))

def calcular(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame()

    df = df_in.copy()
    # Calcular máximos y usados
    df["Máx. permitido"] = df.apply(lambda r: max_permitido_por_linea(r["Espesor (mm)"], r["Largo (mm)"]), axis=1)

    def usado(r):
        override = r["Unidades por paquete (opcional)"]
        if pd.notna(override) and str(override).strip() != "":
            return int(override)
        return r["Máx. permitido"]

    df["Unidades usadas"] = df.apply(usado, axis=1)

    # Validaciones simples
    def estado(r):
        if pd.isna(r["Máx. permitido"]) and pd.isna(r["Unidades por paquete (opcional)"]):
            return "⚠️ Falta espesor/largo válido o espesor no está en la tabla."
        if pd.notna(r["Unidades por paquete (opcional)"]) and pd.notna(r["Máx. permitido"]):
            if int(r["Unidades por paquete (opcional)"]) > int(r["Máx. permitido"]):
                return "🟠 Por petición del cliente (fuera de estándar)."
            else:
                return "🟢 Forzado dentro de estándar."
        if pd.notna(r["Máx. permitido"]):
            return "🟢 Dentro de estándar."
        return "⚠️ Revisar datos."

    df["Estado"] = df.apply(estado, axis=1)

    # Paquetes y último paquete (último puede ser incompleto → Opción 1)
    def paquetes(cant, usado):
        if pd.isna(cant) or pd.isna(usado) or not usado:
            return 0
        return math.ceil(int(cant) / int(usado))

    def ultimo(cant, usado, p):
        if p == 0 or pd.isna(cant) or pd.isna(usado) or not usado:
            return None
        resto = int(cant) % int(usado)
        return int(usado) if resto == 0 else resto

    df["Paquetes necesarios"] = df.apply(lambda r: paquetes(r["Cantidad total"], r["Unidades usadas"]), axis=1)
    df["Unidades último paquete"] = df.apply(lambda r: ultimo(r["Cantidad total"], r["Unidades usadas"], r["Paquetes necesarios"]), axis=1)

    # Reordenar columnas para mostrar
    orden = [
        "Referencia", "Ancho (mm)", "Largo (mm)", "Espesor (mm)", "Cantidad total",
        "Unidades por paquete (opcional)", "Máx. permitido", "Unidades usadas",
        "Paquetes necesarios", "Unidades último paquete", "Estado"
    ]
    return df[orden]

def desglose_por_paquetes(res: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for _, r in res.iterrows():
        if pd.isna(r["Unidades usadas"]) or r["Paquetes necesarios"] == 0:
            continue
        n = int(r["Paquetes necesarios"])
        m = int(r["Unidades usadas"])
        q = int(r["Cantidad total"])
        for i in range(1, n + 1):
            unidades = m if i < n else (m if q % m == 0 else (q % m))
            filas.append({
                "Referencia": r["Referencia"],
                "Espesor (mm)": int(r["Espesor (mm)"]) if pd.notna(r["Espesor (mm)"]) else None,
                "Largo (mm)": int(r["Largo (mm)"]) if pd.notna(r["Largo (mm)"]) else None,
                "Paquete #": i,
                "Unidades del paquete": int(unidades)
            })
    return pd.DataFrame(filas)

# ====== Cálculo automático ======
resultado = calcular(df)

st.markdown("### 📊 Resultado")
st.dataframe(resultado, use_container_width=True)

# Resumen global (opcional)
if not resultado.empty:
    total_paquetes = int(resultado["Paquetes necesarios"].sum())
    total_paneles = int(resultado["Cantidad total"].fillna(0).sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Total paneles", f"{total_paneles}")
    c2.metric("Total paquetes", f"{total_paquetes}")
    c3.metric("Líneas válidas", f"{(resultado['Paquetes necesarios']>0).sum()}")

# ====== Desglose por paquetes ======
st.markdown("### 📦 Desglose por paquete")
desglose = desglose_por_paquetes(resultado)
st.dataframe(desglose, use_container_width=True)

# ====== Descargas ======
col_a, col_b = st.columns(2)
with col_a:
    if not resultado.empty:
        st.download_button(
            "⬇️ Descargar resultados (CSV)",
            resultado.to_csv(index=False).encode("utf-8"),
            file_name="paletizacion_resultados.csv",
            mime="text/csv",
            use_container_width=True
        )
with col_b:
    if not desglose.empty:
        st.download_button(
            "⬇️ Descargar desglose (CSV)",
            desglose.to_csv(index=False).encode("utf-8"),
            file_name="paletizacion_desglose.csv",
            mime="text/csv",
            use_container_width=True
        )

st.info("Consejo: si cambian los máximos permitidos o el umbral, edita el archivo 'reglas_fachada.json' y recarga la página.")
