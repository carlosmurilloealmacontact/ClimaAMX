"""Visor de resultados para la encuesta Diagnóstico de clima AMX."""
import io
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError

import pandas as pd
import plotly.express as px
import streamlit as st

SHEET_ID = "1qypijvCeKctQdt68Cd3-bjmVCR1xUm-wz8a370wsb5k"
SHEET_NAME = "Respuestas de formulario 1"
SCALE = {"Nunca": 1, "Casi nunca": 2, "Casi Nunca": 2, "A veces": 3,
         "Casi siempre": 4, "Siempre": 5}
COLORS = {"Nunca": "#D94A3D", "Casi nunca": "#F2A509", "Casi Nunca": "#F2A509",
          "A veces": "#ABAF1A", "Casi siempre": "#72B043", "Siempre": "#2CA148"}


def read_sheet():
    url = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq"
           f"?tqx=out:csv&sheet={urllib.parse.quote(SHEET_NAME)}&_={int(time.time())}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return pd.read_csv(io.BytesIO(response.read()))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(
                "La hoja de Google Sheets requiere autenticación. "
                "Publícala en Archivo > Compartir > Publicar en la web, "
                "o cambia el acceso general a 'Cualquiera con el enlace: Lector'."
            ) from exc
        raise


@st.cache_data(ttl=300)
def load_data():
    df = read_sheet()
    question_cols = [c for c in df.columns if c.startswith("Preguntas [")]
    comment_cols = [c for c in df.columns if c.lower() == "comentarios"]
    role_col = "¿Cuál es tu rol?"
    leader_col = next((c for c in ("Lider", "Líder", "Líder directo") if c in df.columns), None)
    # Un mismo formulario puede traer una columna de servicio parcialmente
    # diligenciada. Consolidamos ambas fuentes para evitar mostrar NaN.
    if "¿Cuál es tu servicio?" in df.columns and "Area" in df.columns:
        df["Servicio visor"] = df["¿Cuál es tu servicio?"].fillna(df["Area"])
        df["Servicio visor"] = df["Servicio visor"].replace(r"^\s*$", pd.NA, regex=True).fillna("Sin servicio identificado")
        service_col = "Servicio visor"
    elif "¿Cuál es tu servicio?" in df.columns:
        service_col = "¿Cuál es tu servicio?"
    else:
        service_col = "Area"
    for col in question_cols:
        df[col] = df[col].astype("string").str.strip()
    return df, question_cols, comment_cols[0] if comment_cols else None, role_col, service_col, leader_col


def label_question(col):
    return col.split("[", 1)[1].rstrip("]") if "[" in col else col


def score(df, cols):
    values = df[cols].stack().map(SCALE).dropna()
    return round(values.mean() / 5 * 100, 1) if len(values) else 0


def favorability(df, cols):
    values = df[cols].stack().dropna()
    return round(values.isin(["Siempre", "Casi siempre"]).mean() * 100, 1) if len(values) else 0


def classify_comment(text):
    """Clasificación transparente y reproducible para comentarios en español."""
    text = str(text).lower()
    positive = ["excelente", "bueno", "bien", "chévere", "genial", "feliz", "motivad", "agradable", "mejor"]
    negative = ["mal", "malo", "mala", "problema", "difícil", "dificil", "falta", "faltan", "pésim", "pesim", "no hay", "nunca"]
    pos = sum(word in text for word in positive)
    neg = sum(word in text for word in negative)
    sentiment = "Positivo" if pos > neg else "Negativo" if neg > pos else "Neutro"
    topics = []
    topic_words = {
        "Clima laboral": ["clima", "ambiente", "respeto"],
        "Motivación": ["motiv", "incentivo", "monetari", "reconocimiento"],
        "Bienestar": ["bienestar", "comodidad", "salud"],
        "Liderazgo": ["líder", "lider", "jefe", "lideres"],
        "Desarrollo": ["aprender", "capacitación", "crecer", "desarrollo"],
        "Condiciones de trabajo": ["trabajo", "horario", "recursos", "herramienta"],
    }
    for topic, words in topic_words.items():
        if any(word in text for word in words): topics.append(topic)
    return pd.Series({"Sentimiento": sentiment, "Temas": ", ".join(topics) or "Sin tema identificado"})


st.set_page_config(page_title="Diagnóstico de clima | AMX", page_icon="📊", layout="wide")
st.markdown("""<style>
.stApp{background:#F2F2F2} h1,h2,h3{color:#3D008C!important}
div[data-testid="stMetric"]{background:#0F034E;border-radius:18px;padding:14px;text-align:center}
[data-testid="stMetricValue"],[data-testid="stMetricLabel"]{color:white!important}
</style>""", unsafe_allow_html=True)

try:
    dashboard_password = st.secrets.get("DASHBOARD_PASSWORD")
except Exception:
    # En desarrollo local puede no existir .streamlit/secrets.toml.
    dashboard_password = None

if dashboard_password:
    pwd = st.text_input("Contraseña de acceso", type="password")
    if pwd != dashboard_password:
        st.info("Ingresa la contraseña para consultar el visor.")
        st.stop()

with st.spinner("Cargando respuestas..."):
    try:
        data, question_cols, comment_col, role_col, service_col, leader_col = load_data()
    except RuntimeError as exc:
        st.error("No se pudieron cargar los datos desde Google Sheets.")
        st.warning(str(exc))
        st.markdown("""**Después de cambiar el acceso, pulsa `🔄 Recargar datos` en la barra lateral.**

La hoja contiene resultados de encuesta; verifica que la política de tu organización permita publicar estos datos antes de hacerla accesible por enlace.
""")
        st.stop()

st.title("Diagnóstico de clima | AMX")
st.caption("Resultados de la encuesta · conectado en vivo a Google Sheets")

with st.sidebar:
    st.header("Filtros")
    roles = sorted(data[role_col].dropna().unique())
    services = sorted(data[service_col].dropna().unique())
    leaders = sorted(data[leader_col].dropna().unique()) if leader_col else []
    role = st.multiselect("Rol", roles)
    leader = st.multiselect("Líder", leaders) if leader_col else []
    service = st.multiselect("Servicio", services)
    if st.button("🔄 Recargar datos"):
        load_data.clear(); st.rerun()

df = data.copy()
if role: df = df[df[role_col].isin(role)]
if leader_col and leader: df = df[df[leader_col].isin(leader)]
if service: df = df[df[service_col].isin(service)]
if df.empty:
    st.warning("No hay respuestas para los filtros seleccionados."); st.stop()

fav = favorability(df, question_cols)
avg = score(df, question_cols)
offer_col = question_cols[-1]
offer_fav = favorability(df, [offer_col])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Respuestas", len(df)); c2.metric("Favorabilidad general", f"{fav}%")
c3.metric("Promedio normalizado", f"{avg}%"); c4.metric("Aceptaría otra oferta", f"{offer_fav}%")
st.caption("Favorabilidad = respuestas “Siempre” o “Casi siempre”. El promedio normalizado convierte la escala 1–5 a 0–100; no es comparable con el resultado ponderado del Barómetro.")

st.markdown("---")
qdf = pd.DataFrame({"Pregunta": [f"P{i+1}" for i in range(len(question_cols))],
                    "Favorabilidad": [favorability(df, [c]) for c in question_cols],
                    "Texto": [label_question(c) for c in question_cols]})
st.subheader("Favorabilidad por pregunta")
fig = px.bar(qdf, x="Pregunta", y="Favorabilidad", text="Favorabilidad", color="Favorabilidad",
             range_y=[0, 100], color_continuous_scale=["#D94A3D", "#F2A509", "#2CA148"], custom_data=["Texto"])
fig.update_traces(texttemplate="%{text}%", hovertemplate="<b>%{x}</b><br>%{customdata[0]}<br>Favorabilidad: %{y}%<extra></extra>")
fig.update_layout(height=390, plot_bgcolor="white", paper_bgcolor="white", coloraxis_showscale=False)
st.plotly_chart(fig, use_container_width=True)
st.dataframe(qdf[["Pregunta", "Texto", "Favorabilidad"]], use_container_width=True, hide_index=True,
             column_config={"Favorabilidad": st.column_config.ProgressColumn("Favorabilidad", min_value=0, max_value=100, format="%.1f%%")})
with st.expander("Ver texto completo de las preguntas"):
    for _, row in qdf.iterrows(): st.markdown(f"**{row.Pregunta}** · {row.Favorabilidad}% — {row.Texto}")

st.subheader("Distribución de respuestas")
long = df[question_cols].rename(columns={c: f"P{i+1}" for i, c in enumerate(question_cols)}).melt(var_name="Pregunta", value_name="Respuesta").dropna()
counts = long.groupby(["Pregunta", "Respuesta"]).size().reset_index(name="Respuestas")
fig2 = px.bar(counts, x="Pregunta", y="Respuestas", color="Respuesta", text="Respuestas", barmode="stack", color_discrete_map=COLORS)
fig2.update_layout(height=370, plot_bgcolor="white", paper_bgcolor="white")
st.plotly_chart(fig2, use_container_width=True)

if comment_col:
    st.subheader("Comentarios abiertos")
    comments = df[[role_col, service_col, comment_col]].dropna(subset=[comment_col])
    comments = comments[comments[comment_col].astype(str).str.strip().str.len() > 1]
    if not comments.empty:
        classified = comments[comment_col].apply(classify_comment)
        comments = pd.concat([comments.reset_index(drop=True), classified.reset_index(drop=True)], axis=1)
    st.caption(f"{len(comments)} comentarios con contenido para el filtro actual.")
    if not comments.empty:
        sent_counts = comments["Sentimiento"].value_counts().reindex(["Positivo", "Neutro", "Negativo"], fill_value=0)
        ca, cb = st.columns([1, 1.5])
        with ca:
            fig_sent = px.pie(names=sent_counts.index, values=sent_counts.values, hole=.45,
                              color=sent_counts.index,
                              color_discrete_map={"Positivo": "#2CA148", "Neutro": "#ABAF1A", "Negativo": "#D94A3D"})
            fig_sent.update_layout(height=300, margin=dict(l=5, r=5, t=5, b=5))
            st.plotly_chart(fig_sent, use_container_width=True)
        with cb:
            topic_counts = (comments["Temas"].str.split(", ").explode().value_counts().head(10).sort_values())
            fig_topics = px.bar(topic_counts, x=topic_counts.values, y=topic_counts.index, orientation="h",
                                labels={"x": "Comentarios", "y": "Tema"}, color_discrete_sequence=["#3D008C"])
            fig_topics.update_layout(height=300, margin=dict(l=5, r=5, t=5, b=5))
            st.plotly_chart(fig_topics, use_container_width=True)
        selected_sent = st.multiselect("Filtrar comentarios por sentimiento", ["Positivo", "Neutro", "Negativo"],
                                       default=["Positivo", "Neutro", "Negativo"])
        comments = comments[comments["Sentimiento"].isin(selected_sent)]
    for _, row in comments.iterrows():
        icon = {"Positivo": "🟢", "Neutro": "🟡", "Negativo": "🔴"}.get(row.get("Sentimiento"), "💬")
        topic = f" · _{row['Temas']}_" if row.get("Temas") else ""
        st.markdown(f"{icon} **{row[role_col]} · {row[service_col]}** — {row[comment_col]}{topic}")

st.markdown("---")
st.caption(f"Datos en vivo desde la hoja “{SHEET_NAME}” · {len(df)} respuestas visibles")
