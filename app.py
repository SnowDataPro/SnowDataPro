import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import textwrap
import base64
from datetime import datetime, date

# ============================================================
# CONFIGURAZIONE
# ============================================================

st.set_page_config(
    page_title="SnowDataPro",
    page_icon="🎿",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ski_material_lab.db")
VERSIONE_DATABASE_APP = 2


# ============================================================
# DATABASE: TURSO ONLINE + SQLITE LOCALE
# ============================================================

def _leggi_impostazione_privata(nome):
    try:
        valore = str(st.secrets.get(nome, "") or "").strip()
        if valore:
            return valore
    except Exception:
        pass
    return str(os.environ.get(nome, "") or "").strip()


TURSO_DATABASE_URL = _leggi_impostazione_privata("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = _leggi_impostazione_privata("TURSO_AUTH_TOKEN")

if bool(TURSO_DATABASE_URL) != bool(TURSO_AUTH_TOKEN):
    st.error(
        "Configurazione database incompleta: inserisci sia "
        "TURSO_DATABASE_URL sia TURSO_AUTH_TOKEN nei Secrets dell'app."
    )
    st.stop()

USA_DATABASE_TURSO = bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)


def apri_connessione_database():
    if USA_DATABASE_TURSO:
        try:
            import libsql
        except ImportError as exc:
            raise RuntimeError(
                "Manca il pacchetto 'libsql'. Controlla requirements.txt."
            ) from exc

        return libsql.connect(
            database=TURSO_DATABASE_URL,
            auth_token=TURSO_AUTH_TOKEN,
        )

    return sqlite3.connect(DB_PATH)


def inizializza_database():
    conn = apri_connessione_database()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_schema_meta (
            chiave TEXT PRIMARY KEY,
            valore TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            ora TEXT,
            luogo TEXT NOT NULL,
            temperatura_aria REAL,
            temperatura_neve REAL,
            umidita REAL,
            tipo_neve TEXT,
            condizione_pista TEXT,
            note TEXT,
            creato_il TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sci (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codice TEXT NOT NULL UNIQUE,
            marca TEXT,
            modello TEXT,
            tecnica TEXT,
            note TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS zero_test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessione_id INTEGER NOT NULL,
            sci_id INTEGER NOT NULL,
            prova_numero INTEGER NOT NULL,
            tempo_sec REAL NOT NULL,
            note TEXT,
            FOREIGN KEY(sessione_id) REFERENCES sessioni(id),
            FOREIGN KEY(sci_id) REFERENCES sci(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_materiali (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessione_id INTEGER NOT NULL,
            categoria TEXT NOT NULL,
            metodo TEXT NOT NULL,
            titolo TEXT,
            sci_a_id INTEGER,
            preparazione_a TEXT,
            sci_b_id INTEGER,
            preparazione_b TEXT,
            vincitore TEXT,
            vantaggio_aste REAL,
            tempo_a REAL,
            tempo_b REAL,
            valutazione INTEGER,
            note TEXT,
            creato_il TEXT NOT NULL,
            FOREIGN KEY(sessione_id) REFERENCES sessioni(id),
            FOREIGN KEY(sci_a_id) REFERENCES sci(id),
            FOREIGN KEY(sci_b_id) REFERENCES sci(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_tenuta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessione_id INTEGER NOT NULL,
            sci_id INTEGER,
            preparazione TEXT NOT NULL,
            tenuta INTEGER NOT NULL,
            scorrevolezza INTEGER,
            facilita_calcio INTEGER,
            durata INTEGER,
            note TEXT,
            creato_il TEXT NOT NULL,
            FOREIGN KEY(sessione_id) REFERENCES sessioni(id),
            FOREIGN KEY(sci_id) REFERENCES sci(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_prodotti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            nome TEXT NOT NULL,
            marca TEXT,
            tipo TEXT,
            condizioni TEXT,
            descrizione TEXT,
            note TEXT,
            creato_il TEXT NOT NULL
        )
    """)

    conn.execute("""
        INSERT INTO app_schema_meta (chiave, valore)
        VALUES ('versione_database_app', ?)
        ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore
    """, (str(VERSIONE_DATABASE_APP),))

    conn.commit()
    conn.close()


inizializza_database()


# ============================================================
# STILE
# ============================================================

st.markdown(textwrap.dedent("""
<style>
    :root {
        color-scheme: light;
    }

    html, body, .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"] {
        background: #f5f7fa !important;
        color: #1f2937 !important;
    }

    /* ======================================================
       PAGINA / STREAMLIT - STESSA LOGICA DI SECTOR G2 LAB
       ====================================================== */

    .stApp {
        background:
            linear-gradient(
                180deg,
                #f7f9fa 0px,
                #f4f6f8 260px,
                #f4f6f8 100%
            );
        color: #1f2937;
    }

    .block-container {
        max-width: 1380px;
        padding-top: 2rem;
        padding-bottom: 4rem;
        padding-left: 2.4rem;
        padding-right: 2.4rem;
    }

    /* Il contenitore del banner resta fermo in alto.
       Tutto il resto della pagina usa lo scroll nativo Streamlit. */
    div[data-testid="stElementContainer"]:has(.snowdata-sticky-banner) {
        position: sticky !important;
        top: 0 !important;
        z-index: 1 !important;
        margin-bottom: 0 !important;
    }

    div[data-testid="stElementContainer"]:has(.snowdata-sticky-banner)
    [data-testid="stMarkdownContainer"] {
        margin-bottom: 0 !important;
    }

    /* Il contenuto ha z-index superiore e scorrendo copre il banner. */
    div[class*="st-key-snowdata_page_content"] {
        position: relative !important;
        z-index: 5 !important;
        background:
            linear-gradient(
                180deg,
                #f7f9fa 0px,
                #f4f6f8 260px,
                #f4f6f8 100%
            ) !important;

        width: calc(100% + 6rem) !important;
        max-width: none !important;
        box-sizing: border-box !important;
        margin-left: -3rem !important;
        margin-right: -3rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
        padding-top: 22px !important;
        padding-bottom: 4rem !important;
        min-height: calc(100vh - 145px);
    }

    div[class*="st-key-snowdata_page_content"] > div {
        width: 100% !important;
        max-width: none !important;
        box-sizing: border-box !important;
    }

    /* In Sector l'header non viene rimosso: è trasparente.
       Il banner viene spinto sotto di lui con margin-top negativo. */
    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    header[data-testid="stHeader"] {
        background-color: transparent !important;
    }

    @media (max-width: 900px) {
        .block-container {
            padding-left: 1.2rem;
            padding-right: 1.2rem;
        }

        div[class*="st-key-snowdata_page_content"] {
            width: calc(100% + 3.6rem) !important;
            margin-left: -1.8rem !important;
            margin-right: -1.8rem !important;
            padding-left: 1.8rem !important;
            padding-right: 1.8rem !important;
        }
    }

    /* ---------------- SIDEBAR · STILE SECTOR G2 LAB ---------------- */
    [data-testid="stSidebar"] {
        background: #191d1f !important;
        border-right: 1px solid #22282b !important;
    }

    [data-testid="stSidebar"] > div:first-child {
        background: #191d1f !important;
    }

    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] summary {
        color: #eef3f6 !important;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #eef3f6 !important;
    }

    /* Pulsanti di navigazione */
    [data-testid="stSidebar"] button {
        background: transparent !important;
        color: #eef3f6 !important;
        border: 0 !important;
        border-radius: 2px !important;
        box-shadow: none !important;
        min-height: 52px;
        justify-content: flex-start !important;
        text-align: left !important;
        padding-left: 16px !important;
    }

    [data-testid="stSidebar"] button:hover {
        background: #252a2d !important;
        color: #ffffff !important;
    }

    [data-testid="stSidebar"] button[kind="primary"] {
        background: #252a2d !important;
        color: #ffffff !important;
        border-left: 4px solid #00a7e1 !important;
        padding-left: 12px !important;
    }

    [data-testid="stSidebar"] button p,
    [data-testid="stSidebar"] button span {
        color: inherit !important;
        font-size: 1rem !important;
    }

    /* Expander come intestazioni di sezione, senza riquadro */
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        border: 0 !important;
        background: transparent !important;
    }

    [data-testid="stSidebar"] [data-testid="stExpander"] details,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        border: 0 !important;
        background: transparent !important;
        box-shadow: none !important;
    }

    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        min-height: 60px !important;
        padding-left: 6px !important;
    }

    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
        background: #202528 !important;
    }

    [data-testid="stSidebar"] hr {
        border-color: #2b3135 !important;
    }

    /* ---------------- TESTI GENERALI ---------------- */
    h1, h2, h3, h4, h5, h6 {
        color: #16324f !important;
    }

    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        color: #26384a;
    }

    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {
        color: #66788a !important;
    }

    /* ---------------- ETICHETTE WIDGET ---------------- */
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] span,
    label[data-baseweb="checkbox"],
    label[data-baseweb="radio"] {
        color: #243447 !important;
        font-weight: 600;
    }

    /* ---------------- INPUT LIGHT ---------------- */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stTimeInput"] input,
    [data-testid="stTextArea"] textarea {
        background: #ffffff !important;
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        border-color: #cbd5e1 !important;
    }

    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stTextArea"] textarea::placeholder {
        color: #8795a5 !important;
        -webkit-text-fill-color: #8795a5 !important;
        opacity: 1 !important;
    }

    [data-baseweb="select"] > div,
    [data-baseweb="base-input"],
    [data-baseweb="input"],
    [data-baseweb="textarea"] {
        background: #ffffff !important;
        color: #111827 !important;
        border-color: #cbd5e1 !important;
    }

    [data-baseweb="select"] span,
    [data-baseweb="select"] div {
        color: #111827 !important;
    }

    /* Mantiene ben visibili i +/- dei number input */
    [data-testid="stNumberInput"] button,
    [data-testid="stNumberInput"] button svg {
        color: #243447 !important;
        fill: #243447 !important;
    }

    /* ---------------- EXPANDER ---------------- */
    [data-testid="stExpander"] {
        background: transparent;
    }

    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span {
        color: #243447 !important;
    }

    /* ---------------- TITOLI PAGINA ---------------- */
    .ski-banner {
        background: transparent;
        border-radius: 0;
        padding: 0 0 1.2rem 0;
        color: #16324f;
        margin: 0 0 1.4rem 0;
        box-shadow: none;
        border-bottom: 1px solid #d8e0e7;
        position: relative;
    }

    .ski-banner::after {
        content: "";
        position: absolute;
        left: 0;
        bottom: -1px;
        width: 54px;
        height: 3px;
        background: #00a7e1;
    }

    .ski-banner h1 {
        color: #15283d !important;
        margin: 0;
        font-size: 1.75rem;
        line-height: 1.2;
        font-weight: 760;
    }

    .ski-banner p {
        color: #66788a !important;
        margin: 0.85rem 0 0 0;
        font-size: 1rem;
    }

    /* ---------------- CARD ---------------- */
    .metric-card {
        background: white;
        border: 1px solid #e0e6ed;
        border-radius: 12px;
        padding: 16px;
        min-height: 105px;
        box-shadow: 0 4px 16px rgba(0,0,0,.04);
    }

    .metric-label {
        font-size: .85rem;
        color: #6c7785;
        margin-bottom: 5px;
    }

    .metric-value {
        font-size: 1.7rem;
        font-weight: 700;
        color: #16324f;
    }

    /* ---------------- TABELLE ---------------- */
    div[data-testid="stDataFrame"] {
        background: white;
        border-radius: 10px;
    }

    /* ---------------- MESSAGGI ---------------- */
    [data-testid="stAlert"] p {
        color: inherit !important;
    }
</style>
""").strip(), unsafe_allow_html=True)


def mostra_banner_fotografico():
    """Banner panoramico sticky: il contenuto della pagina gli scorre sopra."""
    percorso = os.path.join(BASE_DIR, "banner snowdatapro.jpg")
    if not os.path.exists(percorso):
        return

    with open(percorso, "rb") as file:
        contenuto_base64 = base64.b64encode(file.read()).decode()

    banner_html = (
        '<div class="snowdata-sticky-banner" '
        'style="width:auto;height:240px;margin-left:-3rem;'
        'margin-right:-3rem;border-radius:0;overflow:hidden;'
        'margin-bottom:0;margin-top:-50px;position:relative;'
        'z-index:1;background:#dce7ef;">'
        '<img '
        f'src="data:image/jpeg;base64,{contenuto_base64}" '
        'alt="Paesaggio innevato SnowDataPro" '
        'style="width:100%;height:100%;object-fit:cover;'
        'object-position:center 58%;display:block;">'
        '<div aria-hidden="true" style="position:absolute;inset:0;'
        'background:linear-gradient(180deg,rgba(7,28,45,.02) 0%,'
        'rgba(7,28,45,.04) 65%,rgba(7,28,45,.10) 100%);'
        'pointer-events:none;"></div>'
        '</div>'
    )
    st.markdown(banner_html, unsafe_allow_html=True)


def mostra_banner(titolo, sottotitolo):
    st.markdown(
        textwrap.dedent(f"""
        <div class="ski-banner">
            <h1>{titolo}</h1>
            <p>{sottotitolo}</p>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )


def metric_card(label, value):
    st.markdown(
        textwrap.dedent(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """).strip(),
        unsafe_allow_html=True,
    )


# ============================================================
# FUNZIONI DATI
# ============================================================

def leggi_df(query, params=()):
    conn = apri_connessione_database()
    try:
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def esegui(query, params=()):
    conn = apri_connessione_database()
    try:
        conn.execute(query, params)
        conn.commit()
    finally:
        conn.close()


def sessioni_df():
    return leggi_df("""
        SELECT *
        FROM sessioni
        ORDER BY data DESC, id DESC
    """)


def sci_df():
    return leggi_df("""
        SELECT *
        FROM sci
        ORDER BY codice COLLATE NOCASE
    """)


def dizionario_sessioni():
    df = sessioni_df()
    return {
        f"{r['data']} · {r['luogo']} · #{int(r['id'])}": int(r["id"])
        for _, r in df.iterrows()
    }


def dizionario_sci():
    df = sci_df()
    return {
        f"{r['codice']}" + (f" · {r['marca']}" if r.get("marca") else ""): int(r["id"])
        for _, r in df.iterrows()
    }


def zero_test_sessione(sessione_id):
    return leggi_df("""
        SELECT
            z.id,
            z.sessione_id,
            z.sci_id,
            s.codice AS sci,
            s.marca,
            s.modello,
            z.prova_numero,
            z.tempo_sec,
            z.note
        FROM zero_test z
        JOIN sci s ON s.id = z.sci_id
        WHERE z.sessione_id = ?
        ORDER BY s.codice, z.prova_numero
    """, (int(sessione_id),))


def riepilogo_zero_test(sessione_id):
    df = zero_test_sessione(sessione_id)
    if df.empty:
        return pd.DataFrame()

    riepilogo = (
        df.groupby(["sci_id", "sci"], as_index=False)
        .agg(
            prove=("tempo_sec", "count"),
            tempo_medio=("tempo_sec", "mean"),
            deviazione_standard=("tempo_sec", "std"),
            miglior_tempo=("tempo_sec", "min"),
        )
        .sort_values("tempo_medio")
        .reset_index(drop=True)
    )
    riepilogo["deviazione_standard"] = riepilogo["deviazione_standard"].fillna(0.0)
    migliore = float(riepilogo["tempo_medio"].min())
    riepilogo["delta_migliore"] = riepilogo["tempo_medio"] - migliore
    return riepilogo


def coppie_simili_zero_test(sessione_id, tolleranza):
    riepilogo = riepilogo_zero_test(sessione_id)
    if len(riepilogo) < 2:
        return pd.DataFrame()

    coppie = []
    righe = riepilogo.to_dict("records")
    for i in range(len(righe)):
        for j in range(i + 1, len(righe)):
            delta = abs(float(righe[i]["tempo_medio"]) - float(righe[j]["tempo_medio"]))
            if delta <= tolleranza:
                coppie.append({
                    "Sci A": righe[i]["sci"],
                    "Sci B": righe[j]["sci"],
                    "Tempo A": righe[i]["tempo_medio"],
                    "Tempo B": righe[j]["tempo_medio"],
                    "Δ medio (s)": delta,
                })

    if not coppie:
        return pd.DataFrame()

    return pd.DataFrame(coppie).sort_values("Δ medio (s)").reset_index(drop=True)



def pagina_catalogo_prodotti(categoria, titolo, sottotitolo, tipi):
    mostra_banner(titolo, sottotitolo)

    with st.form(f"catalogo_{categoria}_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            nome = st.text_input("Nome / codice *")
        with c2:
            marca = st.text_input("Marca")
        with c3:
            tipo = st.selectbox("Tipo", tipi)

        condizioni = st.text_input(
            "Condizioni / range di utilizzo",
            placeholder="es. -5 / -10 °C, neve nuova, umidità elevata..."
        )
        descrizione = st.text_area(
            "Descrizione",
            placeholder="Caratteristiche del prodotto, applicazione, struttura, geometria..."
        )
        note = st.text_area("Note")

        salva = st.form_submit_button(
            "Aggiungi al catalogo",
            type="primary",
            use_container_width=True,
        )

        if salva:
            if not nome.strip():
                st.error("Inserisci il nome o codice.")
            else:
                esegui("""
                    INSERT INTO catalogo_prodotti (
                        categoria, nome, marca, tipo, condizioni,
                        descrizione, note, creato_il
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    categoria,
                    nome.strip(),
                    marca.strip(),
                    tipo,
                    condizioni.strip(),
                    descrizione.strip(),
                    note.strip(),
                    datetime.now().isoformat(timespec="seconds"),
                ))
                st.success("Prodotto aggiunto al catalogo.")
                st.rerun()

    st.markdown("### Catalogo")
    df = leggi_df("""
        SELECT id, nome, marca, tipo, condizioni, descrizione, note
        FROM catalogo_prodotti
        WHERE categoria = ?
        ORDER BY nome COLLATE NOCASE
    """, (categoria,))

    if df.empty:
        st.info("Nessun elemento ancora inserito in questo catalogo.")
    else:
        df = df.rename(columns={
            "id": "ID",
            "nome": "Nome / codice",
            "marca": "Marca",
            "tipo": "Tipo",
            "condizioni": "Condizioni",
            "descrizione": "Descrizione",
            "note": "Note",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================
# MENU LATERALE - SNOWDATAPRO / STILE SECTOR G2 LAB
# ============================================================

if "pagina" not in st.session_state:
    st.session_state["pagina"] = "Dashboard"

pagina = st.session_state["pagina"]


def cambia_pagina(nome):
    st.session_state["pagina"] = nome
    st.rerun()


logo_sidebar_path = os.path.join(BASE_DIR, "snowdatapro_logo_transparent.png")
if os.path.exists(logo_sidebar_path):
    with open(logo_sidebar_path, "rb") as file:
        logo_sidebar_b64 = base64.b64encode(file.read()).decode()

    st.sidebar.markdown(
        f"""
        <div style="
            padding:24px 18px 24px 18px;
            text-align:center;
        ">
            <img
                src="data:image/png;base64,{logo_sidebar_b64}"
                alt="SnowDataPro"
                style="
                    width:min(100%, 250px);
                    height:auto;
                    display:block;
                    margin:0 auto;
                    filter: drop-shadow(0 3px 10px rgba(0,0,0,.18));
                "
            >
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.sidebar.markdown(
        "<div style='height:32px;'></div>",
        unsafe_allow_html=True,
    )

if st.sidebar.button(
    "Dashboard",
    icon=":material/home:",
    key="menu_dashboard",
    use_container_width=True,
    type="primary" if pagina == "Dashboard" else "secondary",
):
    cambia_pagina("Dashboard")


with st.sidebar.expander(
    "Test",
    icon=":material/science:",
    expanded=pagina in [
        "Zero test",
        "Test prodotti scorrimento",
        "Test scioline di tenuta",
        "Test rigature manuali",
    ],
):
    if st.button(
        "Zero test",
        key="menu_zero_test",
        use_container_width=True,
        type="primary" if pagina == "Zero test" else "secondary",
    ):
        cambia_pagina("Zero test")

    if st.button(
        "Test prodotti scorrimento",
        key="menu_test_scorrimento",
        use_container_width=True,
        type="primary" if pagina == "Test prodotti scorrimento" else "secondary",
    ):
        cambia_pagina("Test prodotti scorrimento")

    if st.button(
        "Test scioline di tenuta",
        key="menu_test_tenuta",
        use_container_width=True,
        type="primary" if pagina == "Test scioline di tenuta" else "secondary",
    ):
        cambia_pagina("Test scioline di tenuta")

    if st.button(
        "Test rigature manuali",
        key="menu_test_rigature",
        use_container_width=True,
        type="primary" if pagina == "Test rigature manuali" else "secondary",
    ):
        cambia_pagina("Test rigature manuali")


with st.sidebar.expander(
    "Prodotti",
    icon=":material/inventory_2:",
    expanded=pagina in [
        "Prodotti di scorrimento",
        "Scioline di tenuta",
        "Rigature manuali",
    ],
):
    if st.button(
        "Prodotti di scorrimento",
        key="menu_prodotti_scorrimento",
        use_container_width=True,
        type="primary" if pagina == "Prodotti di scorrimento" else "secondary",
    ):
        cambia_pagina("Prodotti di scorrimento")

    if st.button(
        "Scioline di tenuta",
        key="menu_prodotti_tenuta",
        use_container_width=True,
        type="primary" if pagina == "Scioline di tenuta" else "secondary",
    ):
        cambia_pagina("Scioline di tenuta")

    if st.button(
        "Rigature manuali",
        key="menu_prodotti_rigature",
        use_container_width=True,
        type="primary" if pagina == "Rigature manuali" else "secondary",
    ):
        cambia_pagina("Rigature manuali")


# ============================================================
# PAGINE
# ============================================================

mostra_banner_fotografico()

with st.container(key="snowdata_page_content"):

    if pagina == "Dashboard":
        mostra_banner(
            "SnowDataPro",
            "Material testing, snow data, zero test, scorrimento, rigature e tenuta.",
        )

        sessioni = sessioni_df()
        sci = sci_df()
        zero = leggi_df("SELECT COUNT(*) AS n FROM zero_test")
        materiali = leggi_df("SELECT COUNT(*) AS n FROM test_materiali")
        tenuta = leggi_df("SELECT COUNT(*) AS n FROM test_tenuta")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            metric_card("Sessioni", int(len(sessioni)))
        with c2:
            metric_card("Sci catalogati", int(len(sci)))
        with c3:
            metric_card("Prove zero test", int(zero.iloc[0]["n"]))
        with c4:
            metric_card(
                "Test materiali",
                int(materiali.iloc[0]["n"]) + int(tenuta.iloc[0]["n"]),
            )

        st.markdown("### Gestione")
        c_g1, c_g2, c_g3 = st.columns(3)
        with c_g1:
            if st.button("Nuova sessione", use_container_width=True):
                cambia_pagina("Nuova sessione")
        with c_g2:
            if st.button("Catalogo sci", use_container_width=True):
                cambia_pagina("Catalogo sci")
        with c_g3:
            if st.button("Storico test", use_container_width=True):
                cambia_pagina("Storico")

        st.markdown("### Ultime sessioni")
        if sessioni.empty:
            st.info("Nessuna sessione registrata. Crea la prima sessione dal menu laterale.")
        else:
            mostra = sessioni[
                ["data", "ora", "luogo", "temperatura_aria", "temperatura_neve",
                 "tipo_neve", "condizione_pista"]
            ].head(10).copy()
            mostra.columns = [
                "Data", "Ora", "Luogo", "T aria °C", "T neve °C",
                "Tipo neve", "Pista"
            ]
            st.dataframe(mostra, use_container_width=True, hide_index=True)


    elif pagina == "Nuova sessione":
        mostra_banner(
            "Sessioni di test",
            "Registra una giornata e le condizioni ambientali una sola volta.",
        )

        with st.form("form_sessione", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                data_sessione = st.date_input("Data", value=date.today())
                ora_sessione = st.time_input("Ora")
                luogo = st.text_input("Luogo *")
            with c2:
                temperatura_aria = st.number_input(
                    "Temperatura aria (°C)", value=0.0, step=0.5
                )
                temperatura_neve = st.number_input(
                    "Temperatura neve (°C)", value=0.0, step=0.5
                )
                umidita = st.number_input(
                    "Umidità relativa (%)", min_value=0.0, max_value=100.0,
                    value=70.0, step=1.0
                )
            with c3:
                tipo_neve = st.selectbox(
                    "Tipo neve",
                    [
                        "Nuova", "Vecchia", "Trasformata", "Artificiale",
                        "Mista", "Bagnata", "Ghiacciata", "Altro"
                    ],
                )
                condizione_pista = st.selectbox(
                    "Condizione pista",
                    [
                        "Compatta", "Morbida", "Dura", "Ghiacciata",
                        "Lucida", "Sporca", "Variabile", "Altro"
                    ],
                )

            note = st.text_area("Note")
            salva = st.form_submit_button(
                "Salva sessione", type="primary", use_container_width=True
            )

            if salva:
                if not luogo.strip():
                    st.error("Inserisci il luogo.")
                else:
                    esegui("""
                        INSERT INTO sessioni (
                            data, ora, luogo, temperatura_aria, temperatura_neve,
                            umidita, tipo_neve, condizione_pista, note, creato_il
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data_sessione.isoformat(),
                        ora_sessione.strftime("%H:%M"),
                        luogo.strip(),
                        float(temperatura_aria),
                        float(temperatura_neve),
                        float(umidita),
                        tipo_neve,
                        condizione_pista,
                        note.strip(),
                        datetime.now().isoformat(timespec="seconds"),
                    ))
                    st.success("Sessione salvata.")
                    st.rerun()

        st.markdown("### Sessioni registrate")
        df = sessioni_df()
        if not df.empty:
            st.dataframe(
                df[[
                    "id", "data", "ora", "luogo", "temperatura_aria",
                    "temperatura_neve", "umidita", "tipo_neve",
                    "condizione_pista", "note"
                ]],
                use_container_width=True,
                hide_index=True,
            )


    elif pagina == "Catalogo sci":
        mostra_banner(
            "Catalogo sci",
            "Codifica gli sci una volta sola per riutilizzarli in tutti i test.",
        )

        with st.form("form_sci", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                codice = st.text_input("Codice sci *", placeholder="es. C01")
            with c2:
                marca = st.text_input("Marca")
            with c3:
                modello = st.text_input("Modello")
            with c4:
                tecnica = st.selectbox("Tecnica", ["Skating", "Classico", "Entrambi"])

            note = st.text_input("Note")
            salva_sci = st.form_submit_button(
                "Aggiungi sci", type="primary", use_container_width=True
            )

            if salva_sci:
                if not codice.strip():
                    st.error("Inserisci il codice dello sci.")
                else:
                    try:
                        esegui("""
                            INSERT INTO sci (codice, marca, modello, tecnica, note)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            codice.strip(), marca.strip(), modello.strip(),
                            tecnica, note.strip()
                        ))
                        st.success("Sci aggiunto.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Impossibile salvare: {exc}")

        df = sci_df()
        if df.empty:
            st.info("Il catalogo sci è vuoto.")
        else:
            st.dataframe(
                df[["id", "codice", "marca", "modello", "tecnica", "note"]],
                use_container_width=True,
                hide_index=True,
            )


    elif pagina == "Zero test":
        mostra_banner(
            "Zero test",
            "Fotocellule: individua gli sci più simili prima dei test di prodotti o rigature.",
        )

        sessioni = dizionario_sessioni()
        sci = dizionario_sci()

        if not sessioni:
            st.warning("Crea prima una sessione dalla Dashboard.")
            if st.button("Vai a Nuova sessione", type="primary"):
                cambia_pagina("Nuova sessione")
            st.stop()

        if len(sci) < 2:
            st.warning("Inserisci almeno due sci nel catalogo.")
            if st.button("Vai al Catalogo sci", type="primary"):
                cambia_pagina("Catalogo sci")
            st.stop()

        sessione_label = st.selectbox("Sessione", list(sessioni.keys()))
        sessione_id = sessioni[sessione_label]

        with st.form("form_zero_test", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                sci_label = st.selectbox("Sci", list(sci.keys()))
            with c2:
                prova_numero = st.number_input(
                    "Numero prova", min_value=1, value=1, step=1
                )
            with c3:
                tempo_sec = st.number_input(
                    "Tempo (s)", min_value=0.001, value=20.000,
                    step=0.001, format="%.3f"
                )

            note = st.text_input("Note")
            salva_zero = st.form_submit_button(
                "Salva prova", type="primary", use_container_width=True
            )

            if salva_zero:
                esegui("""
                    INSERT INTO zero_test (
                        sessione_id, sci_id, prova_numero, tempo_sec, note
                    )
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    int(sessione_id),
                    int(sci[sci_label]),
                    int(prova_numero),
                    float(tempo_sec),
                    note.strip(),
                ))
                st.success("Prova zero test salvata.")
                st.rerun()

        st.markdown("### Risultati")
        risultati = zero_test_sessione(sessione_id)
        if risultati.empty:
            st.info("Non ci sono ancora prove per questa sessione.")
        else:
            st.dataframe(
                risultati[["sci", "prova_numero", "tempo_sec", "note"]],
                use_container_width=True,
                hide_index=True,
            )

            riepilogo = riepilogo_zero_test(sessione_id)
            mostra = riepilogo.copy()
            mostra["tempo_medio"] = mostra["tempo_medio"].map(lambda x: f"{x:.3f}")
            mostra["deviazione_standard"] = mostra["deviazione_standard"].map(lambda x: f"{x:.3f}")
            mostra["miglior_tempo"] = mostra["miglior_tempo"].map(lambda x: f"{x:.3f}")
            mostra["delta_migliore"] = mostra["delta_migliore"].map(lambda x: f"{x:.3f}")
            mostra = mostra.rename(columns={
                "sci": "Sci",
                "prove": "N prove",
                "tempo_medio": "Tempo medio (s)",
                "deviazione_standard": "SD (s)",
                "miglior_tempo": "Miglior tempo (s)",
                "delta_migliore": "Δ migliore (s)",
            })

            st.markdown("### Riepilogo sci")
            st.dataframe(
                mostra[[
                    "Sci", "N prove", "Tempo medio (s)", "SD (s)",
                    "Miglior tempo (s)", "Δ migliore (s)"
                ]],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("### Sci più simili")
            tolleranza = st.number_input(
                "Tolleranza massima tra i tempi medi (s)",
                min_value=0.001,
                value=0.100,
                step=0.010,
                format="%.3f",
            )

            coppie = coppie_simili_zero_test(sessione_id, float(tolleranza))
            if coppie.empty:
                st.warning("Nessuna coppia rientra nella tolleranza selezionata.")
            else:
                coppie_mostra = coppie.copy()
                for col in ["Tempo A", "Tempo B", "Δ medio (s)"]:
                    coppie_mostra[col] = coppie_mostra[col].map(lambda x: f"{x:.3f}")
                st.dataframe(
                    coppie_mostra,
                    use_container_width=True,
                    hide_index=True,
                )


    elif pagina in ["Test prodotti scorrimento", "Test rigature manuali"]:
        categoria = "Scorrimento" if pagina == "Test prodotti scorrimento" else "Rigatura"
        titolo_pagina = (
            "Test prodotti scorrimento"
            if categoria == "Scorrimento"
            else "Test rigature manuali"
        )
        mostra_banner(
            titolo_pagina,
            "Registra confronti ad aste, parallel o fotocellule.",
        )

        sessioni = dizionario_sessioni()
        sci = dizionario_sci()

        if not sessioni:
            st.warning("Crea prima una sessione.")
            st.stop()
        if len(sci) < 2:
            st.warning("Inserisci almeno due sci nel catalogo.")
            st.stop()

        sessione_label = st.selectbox("Sessione", list(sessioni.keys()))
        sessione_id = sessioni[sessione_label]

        metodo = st.radio(
            "Metodo",
            ["Aste", "Parallel", "Fotocellule"],
            horizontal=True,
        )

        with st.form("form_materiali", clear_on_submit=True):
            titolo = st.text_input(
                "Titolo / identificativo test",
                placeholder="es. Paraffina A vs B oppure rigatura R1 vs R2"
            )

            c1, c2 = st.columns(2)

            with c1:
                st.markdown("#### Preparazione A")
                sci_a_label = st.selectbox("Sci A", list(sci.keys()))
                label_a = "Prodotto A" if categoria == "Scorrimento" else "Rigatura A"
                placeholder_a = "es. Paraffina X" if categoria == "Scorrimento" else "es. R1 / 1 mm lineare"
                preparazione_a = st.text_input(label_a, placeholder=placeholder_a)

            with c2:
                st.markdown("#### Preparazione B")
                sci_b_label = st.selectbox(
                    "Sci B",
                    list(sci.keys()),
                    index=1 if len(sci) > 1 else 0,
                )
                label_b = "Prodotto B" if categoria == "Scorrimento" else "Rigatura B"
                placeholder_b = "es. Paraffina Y" if categoria == "Scorrimento" else "es. R2 / 2 mm lineare"
                preparazione_b = st.text_input(label_b, placeholder=placeholder_b)

            vincitore = None
            vantaggio_aste = None
            tempo_a = None
            tempo_b = None
            valutazione = None

            if metodo == "Aste":
                c3, c4 = st.columns(2)
                with c3:
                    vincitore = st.selectbox("Risultato", ["Pari", "A", "B"])
                with c4:
                    vantaggio_aste = st.number_input(
                        "Vantaggio (aste)", min_value=0.0, value=0.0, step=0.25
                    )
                valutazione = st.slider(
                    "Chiarezza del confronto",
                    min_value=1, max_value=5, value=3,
                    help="1 = differenza quasi impercettibile, 5 = differenza molto netta"
                )

            elif metodo == "Parallel":
                vincitore = st.selectbox(
                    "Risultato parallel",
                    ["Pari", "A", "B"]
                )
                valutazione = st.slider(
                    "Chiarezza del confronto",
                    min_value=1, max_value=5, value=3
                )

            else:
                c3, c4 = st.columns(2)
                with c3:
                    tempo_a = st.number_input(
                        "Tempo A (s)", min_value=0.001,
                        value=20.000, step=0.001, format="%.3f"
                    )
                with c4:
                    tempo_b = st.number_input(
                        "Tempo B (s)", min_value=0.001,
                        value=20.000, step=0.001, format="%.3f"
                    )
                if tempo_a < tempo_b:
                    vincitore = "A"
                elif tempo_b < tempo_a:
                    vincitore = "B"
                else:
                    vincitore = "Pari"
                st.caption(f"Vincitore calcolato: **{vincitore}**")

            note = st.text_area(
                "Note",
                placeholder="Sensazioni, tratto di pista, velocità, eventuali anomalie..."
            )

            salva_test = st.form_submit_button(
                "Salva confronto", type="primary", use_container_width=True
            )

            if salva_test:
                if sci[sci_a_label] == sci[sci_b_label]:
                    st.error("Seleziona due sci diversi.")
                else:
                    esegui("""
                        INSERT INTO test_materiali (
                            sessione_id, categoria, metodo, titolo,
                            sci_a_id, preparazione_a,
                            sci_b_id, preparazione_b,
                            vincitore, vantaggio_aste,
                            tempo_a, tempo_b,
                            valutazione, note, creato_il
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(sessione_id),
                        categoria,
                        metodo,
                        titolo.strip(),
                        int(sci[sci_a_label]),
                        preparazione_a.strip(),
                        int(sci[sci_b_label]),
                        preparazione_b.strip(),
                        vincitore,
                        float(vantaggio_aste) if vantaggio_aste is not None else None,
                        float(tempo_a) if tempo_a is not None else None,
                        float(tempo_b) if tempo_b is not None else None,
                        int(valutazione) if valutazione is not None else None,
                        note.strip(),
                        datetime.now().isoformat(timespec="seconds"),
                    ))
                    st.success("Confronto salvato.")
                    st.rerun()

        st.markdown("### Test della sessione")
        df = leggi_df("""
            SELECT
                t.id,
                t.categoria,
                t.metodo,
                t.titolo,
                sa.codice AS sci_a,
                t.preparazione_a,
                sb.codice AS sci_b,
                t.preparazione_b,
                t.vincitore,
                t.vantaggio_aste,
                t.tempo_a,
                t.tempo_b,
                t.valutazione,
                t.note
            FROM test_materiali t
            LEFT JOIN sci sa ON sa.id = t.sci_a_id
            LEFT JOIN sci sb ON sb.id = t.sci_b_id
            WHERE t.sessione_id = ?
            ORDER BY t.id DESC
        """, (int(sessione_id),))

        if df.empty:
            st.info("Nessun confronto registrato.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)


    elif pagina == "Test scioline di tenuta":
        mostra_banner(
            "Scioline di tenuta",
            "Valutazione a sensazione: tenuta, scorrevolezza, facilità di calcio e durata.",
        )

        sessioni = dizionario_sessioni()
        sci = dizionario_sci()

        if not sessioni:
            st.warning("Crea prima una sessione.")
            st.stop()

        sessione_label = st.selectbox("Sessione", list(sessioni.keys()))
        sessione_id = sessioni[sessione_label]

        with st.form("form_tenuta", clear_on_submit=True):
            c1, c2 = st.columns(2)

            with c1:
                sci_label = st.selectbox(
                    "Sci",
                    ["—"] + list(sci.keys())
                )
                preparazione = st.text_area(
                    "Preparazione / sciolina *",
                    placeholder="es. 2 mani stick X + copertura Y"
                )

            with c2:
                tenuta = st.slider("Tenuta", 1, 5, 3)
                scorrevolezza = st.slider("Scorrevolezza", 1, 5, 3)
                facilita_calcio = st.slider("Facilità di calcio", 1, 5, 3)
                durata = st.slider("Durata / stabilità", 1, 5, 3)

            note = st.text_area(
                "Note",
                placeholder="Sensazione in salita, binario, neve, eventuale zoccolo..."
            )

            salva_tenuta = st.form_submit_button(
                "Salva test tenuta", type="primary", use_container_width=True
            )

            if salva_tenuta:
                if not preparazione.strip():
                    st.error("Inserisci la preparazione.")
                else:
                    sci_id = None if sci_label == "—" else int(sci[sci_label])
                    esegui("""
                        INSERT INTO test_tenuta (
                            sessione_id, sci_id, preparazione,
                            tenuta, scorrevolezza, facilita_calcio, durata,
                            note, creato_il
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(sessione_id),
                        sci_id,
                        preparazione.strip(),
                        int(tenuta),
                        int(scorrevolezza),
                        int(facilita_calcio),
                        int(durata),
                        note.strip(),
                        datetime.now().isoformat(timespec="seconds"),
                    ))
                    st.success("Test tenuta salvato.")
                    st.rerun()

        df = leggi_df("""
            SELECT
                t.id,
                COALESCE(s.codice, '—') AS sci,
                t.preparazione,
                t.tenuta,
                t.scorrevolezza,
                t.facilita_calcio,
                t.durata,
                t.note
            FROM test_tenuta t
            LEFT JOIN sci s ON s.id = t.sci_id
            WHERE t.sessione_id = ?
            ORDER BY t.id DESC
        """, (int(sessione_id),))

        st.markdown("### Test della sessione")
        if df.empty:
            st.info("Nessun test di tenuta registrato.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)


    elif pagina == "Prodotti di scorrimento":
        pagina_catalogo_prodotti(
            "scorrimento",
            "Prodotti di scorrimento",
            "Catalogo di paraffine, liquidi, polveri e altri prodotti da scorrimento.",
            ["Paraffina", "Liquido", "Polvere", "Top finish", "Additivo", "Altro"],
        )


    elif pagina == "Scioline di tenuta":
        pagina_catalogo_prodotti(
            "tenuta",
            "Scioline di tenuta",
            "Catalogo di stick, klister, coperture e prodotti per la tenuta.",
            ["Stick", "Klister", "Copertura", "Base", "Spray", "Altro"],
        )


    elif pagina == "Rigature manuali":
        pagina_catalogo_prodotti(
            "rigatura",
            "Rigature manuali",
            "Catalogo degli utensili e delle configurazioni di rigatura manuale.",
            ["Lineare", "Incrociata", "V", "Rullo", "Utensile", "Altro"],
        )


    elif pagina == "Storico":
        mostra_banner(
            "Storico test",
            "Consulta in un unico punto zero test, scorrimento, rigature e tenuta.",
        )

        tab1, tab2, tab3 = st.tabs(
            ["Zero test", "Scorrimento / Rigature", "Tenuta"]
        )

        with tab1:
            df = leggi_df("""
                SELECT
                    se.data,
                    se.luogo,
                    s.codice AS sci,
                    z.prova_numero,
                    z.tempo_sec,
                    se.temperatura_aria,
                    se.temperatura_neve,
                    se.tipo_neve,
                    se.condizione_pista,
                    z.note
                FROM zero_test z
                JOIN sessioni se ON se.id = z.sessione_id
                JOIN sci s ON s.id = z.sci_id
                ORDER BY se.data DESC, z.id DESC
            """)
            if df.empty:
                st.info("Archivio vuoto.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)

        with tab2:
            df = leggi_df("""
                SELECT
                    se.data,
                    se.luogo,
                    t.categoria,
                    t.metodo,
                    t.titolo,
                    sa.codice AS sci_a,
                    t.preparazione_a,
                    sb.codice AS sci_b,
                    t.preparazione_b,
                    t.vincitore,
                    t.vantaggio_aste,
                    t.tempo_a,
                    t.tempo_b,
                    t.valutazione,
                    se.temperatura_aria,
                    se.temperatura_neve,
                    se.tipo_neve,
                    se.condizione_pista,
                    t.note
                FROM test_materiali t
                JOIN sessioni se ON se.id = t.sessione_id
                LEFT JOIN sci sa ON sa.id = t.sci_a_id
                LEFT JOIN sci sb ON sb.id = t.sci_b_id
                ORDER BY se.data DESC, t.id DESC
            """)
            if df.empty:
                st.info("Archivio vuoto.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)

        with tab3:
            df = leggi_df("""
                SELECT
                    se.data,
                    se.luogo,
                    COALESCE(s.codice, '—') AS sci,
                    t.preparazione,
                    t.tenuta,
                    t.scorrevolezza,
                    t.facilita_calcio,
                    t.durata,
                    se.temperatura_aria,
                    se.temperatura_neve,
                    se.tipo_neve,
                    se.condizione_pista,
                    t.note
                FROM test_tenuta t
                JOIN sessioni se ON se.id = t.sessione_id
                LEFT JOIN sci s ON s.id = t.sci_id
                ORDER BY se.data DESC, t.id DESC
            """)
            if df.empty:
                st.info("Archivio vuoto.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)


    elif pagina == "Backup":
        mostra_banner(
            "Backup",
            "Esporta l'intero archivio in JSON.",
        )

        dati = {}
        for tabella in ["sessioni", "sci", "zero_test", "test_materiali", "test_tenuta", "catalogo_prodotti"]:
            dati[tabella] = leggi_df(f"SELECT * FROM {tabella}").to_dict("records")

        payload = json.dumps(
            {
                "app": "SnowDataPro",
                "versione_database": VERSIONE_DATABASE_APP,
                "esportato_il": datetime.now().isoformat(timespec="seconds"),
                "dati": dati,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        st.download_button(
            "Scarica backup JSON",
            data=payload,
            file_name=f"snowdatapro_backup_{date.today().isoformat()}.json",
            mime="application/json",
            type="primary",
            use_container_width=True,
        )

        st.info(
            "In questa prima versione il backup è solo in esportazione. "
            "L'importazione verrà aggiunta dopo aver stabilizzato la struttura del database."
        )
