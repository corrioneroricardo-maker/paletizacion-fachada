import json
import math
import pandas as pd
import streamlit as st

# ===== CONFIGURACIÓN DE PÁGINA =====
st.set_page_config(page_title="Paletización Fachada", page_icon="📦", layout="wide")

# ===== ESTILOS CSS RESPONSIVOS =====
st.markdown("""
    <style>
    /* General */
    body {
        font-family: 'Segoe UI', sans-serif;
    }
    h1, h2, h3 {
        text-align: center;
        color: #2c3e50;
    }
    /* Ajustes para móviles */
    @media (max-width: 768px) {
        .block-container {
            padding: 1rem !important;
        }
        table {
            font-size: 14px !important;
        }
        label, input, textarea {
            font-size: 16px !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 20px !important;
        }
        button[kind="primary"] {
            width: 100% !important;
            height: 50px !important;
            font-size: 18px !important;
        }
    }
    /* Botones principales */
    .stButton>button {
        background-color: #1e88e5;
        color: white;
        border-radius: 10px;
        height: 45px;
        border: none;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #1565c0;
        color: #fff;
        transform: scale(1.03);
    }
    /* Mensajes visuales */
    .estado-ok {color: #2ecc71; font-weight: bold;}
    .estado-cliente {color: #e67e22; font-weight: bold;}
    .estado-error {color: #c0392b; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

# ===== CARGAR REGLAS =====
@st.cache_data
def cargar_reglas(path="reglas_fachada.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

try:
    reglas = cargar_reglas("reglas_fachada.json")
except FileNotFoundError:
    st.error("⚠️ No se encontró el archivo 'reglas_fachada.json' en la misma carpeta que app.py.")
    st.stop()

UMBRAL = int(reglas.get("threshold_mm", 3000))
LE = {int(k): int(v) for k, v in reglas["fachada"]["le"].items()}
GT = {int(k): int(v) for k, v in reglas["fachada"]["gt"].items()}

# ===== ENCABEZADO =====
st.title("📦 Paletización de Paneles — Fachada (PRT/PRO)")
st.caption("Adaptado para ordenador, tablet o móvil. Si rellenas 'Unidades por paquete (opcional)', se usarán para **todos los paquetes** (el último puede quedar incompleto).")

# ===== REGLAS EN SIDEBAR =====
with st.sidebar:
    st.header("📏 Reglas de empaquetado")
    st.write(f"**Umbral de longitud:** {UMBRAL} mm")
    st.write("**Máximos permitidos (≤ umbral):**")
    st.json(LE, expanded=False)
    st.write("**Máximos permitidos (> umbral):**")
    st.json(GT, expanded=False)

# ===== DATOS DE EJEMPLO =====
ejemplo = pd.DataFrame([
    {"Referencia": "FACH-001", "Ancho (mm)": 1000, "Largo (mm)": 2950, "Espesor (mm)": 40,  "Cantidad total": 120, "Unidades por paquete (opcional)": None},
    {"Referencia": "FACH-002", "Ancho (mm)": 1000, "Largo (mm)": 3200, "Espesor (mm)": 100, "Cantidad total": 100, "Unidades por paquete (opcional)": 12},
])

# ===== ENTRADA DE DATOS =====
st.markdown("### 📝 Pedido de paneles")

df = st.data_editor(
    ejemplo,
    num_rows="dynamic",
    use_container_width=True,
    key="editor",
    column_config={
        "Referencia": st.column_config.TextColumn("Referencia"),
        "Ancho (mm)": st.column_config.NumberColumn("Ancho (mm)", step=1),
        "Largo (mm)": st.column_config.NumberColumn("Largo (mm)", step=1, help=f"Determina si usa ≤ {UMBRAL} mm o > {UMBRAL} mm"),
        "Espesor (mm)": st.column_config.NumberColumn("Espesor (mm)", step=1),
        "Cantidad total": st.column_config.NumberColumn("Cantidad total", step=1),
        "Unidades por paquete (opcional)": st.column_config.NumberColumn("Unidades por paquete (opcional)", step=1),
    }
)

# ===== FUNCIONES DE CÁLCULO =====
def max_permitido(espesor, largo):
    if pd.isna(espesor) or pd.isna(largo):
        return None
    tabla = LE if int(largo) <= UMBRAL else GT
    return tabla.get(int(espesor))

def calcular(df_in):
    df = df_in.copy()
    df["Máx. permitido"] = df.apply(lambda r: max_permitido(r["Espesor (mm)"], r["Largo (mm)"]), axis=1)
    df["Unidades usadas"] = df.apply(
        lambda r: int(r["Unidades por paquete (opcional)"]) if pd.notna(r["Unidades por paquete (opcional)"]) else r["Máx. permitido"], axis=1
    )
    df["Paquetes necesarios"] = df.apply(lambda r: math.ceil(r["Cantidad total"] / r["Unidades usadas"]) if pd.notna(r["Unidades usadas"]) and r["Unidades usadas"] > 0 else 0, axis=1)
    df["Unidades último paquete"] = df.apply(
        lambda r: int(r["Cantidad total"] % r["Unidades usadas"]) if (r["Paquetes necesarios"] > 0 and r["Cantidad total"] % r["Unidades usadas"] != 0) else r["Unidades usadas"], axis=1
    )

    def estado(r):
        if pd.isna(r["Máx. permitido"]) or pd.isna(r["Espesor (mm)"]):
            return "<span class='estado-error'>⚠️ Faltan datos válidos.</span>"
        if pd.notna(r["Unidades por paquete (opcional)"]) and r["Unidades por paquete (opcional)"] > r["Máx. permitido"]:
            return "<span class='estado-cliente'>🟠 Por petición del cliente (fuera de estándar)</span>"
        return "<span class='estado-ok'>🟢 Dentro de estándar</span>"

    df["Estado"] = df.apply(estado, axis=1)
    return df

# ===== RESULTADOS =====
res = calcular(df)

st.markdown("### 📊 Resultado")
st.dataframe(res, use_container_width=True)

if not res.empty:
    total_paneles = int(res["Cantidad total"].fillna(0).sum())
    total_paquetes = int(res["Paquetes necesarios"].fillna(0).sum())
    c1, c2 = st.columns(2)
    c1.metric("Total de paneles", total_paneles)
    c2.metric("Total de paquetes", total_paquetes)

# ===== DESCARGAS =====
col1, col2 = st.columns(2)
with col1:
    if not res.empty:
        st.download_button(
            "⬇️ Descargar resultados (CSV)",
            res.to_csv(index=False).encode("utf-8"),
            file_name="paletizacion_resultados.csv",
            mime="text/csv",
            use_container_width=True
        )
with col2:
    if not res.empty:
        filas = []
        for _, r in res.iterrows():
            for i in range(1, int(r["Paquetes necesarios"]) + 1):
                unidades = r["Unidades usadas"] if i < r["Paquetes necesarios"] else r["Unidades último paquete"]
                filas.append({"Referencia": r["Referencia"], "Paquete #": i, "Unidades": unidades})
        desglose = pd.DataFrame(filas)
        st.download_button(
            "⬇️ Descargar desglose (CSV)",
            desglose.to_csv(index=False).encode("utf-8"),
            file_name="paletizacion_desglose.csv",
            mime="text/csv",
            use_container_width=True
        )

st.markdown("<br><hr><center><small>Versión optimizada para móvil 📱 — Paletización Fachada PRT/PRO</small></center>", unsafe_allow_html=True)
