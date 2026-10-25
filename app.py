import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import textwrap
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
VERSIONE_DATABASE_APP = 1


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

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 3rem;
    }

    /* ---------------- SIDEBAR ---------------- */
    [data-testid="stSidebar"] {
        background: #eef2f6 !important;
        border-right: 1px solid #d7dee7;
    }

    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] summary {
        color: #243447;
    }

    [data-testid="stSidebar"] button p,
    [data-testid="stSidebar"] button span {
        color: inherit !important;
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

    /* ---------------- BANNER ---------------- */
    .ski-banner {
        background: linear-gradient(90deg, #003a70 0%, #005ba8 55%, #0b72c5 100%);
        border-radius: 14px;
        padding: 20px 24px;
        color: white;
        margin-bottom: 20px;
        box-shadow: 0 8px 24px rgba(0,0,0,.08);
    }

    .ski-banner h1,
    .ski-banner p {
        color: white !important;
    }

    .ski-banner h1 {
        margin: 0;
        font-size: 2rem;
        line-height: 1.1;
    }

    .ski-banner p {
        margin: 7px 0 0 0;
        opacity: .9;
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


# ============================================================
# MENU LATERALE
# ============================================================

if "pagina" not in st.session_state:
    st.session_state["pagina"] = "Dashboard"

pagina = st.session_state["pagina"]


def cambia_pagina(nome):
    st.session_state["pagina"] = nome
    st.rerun()


st.sidebar.markdown(
    textwrap.dedent("""
    <div style="padding: 12px 8px 22px 8px;">
        <div style="font-size:1.45rem;font-weight:800;color:#12385d;">SNOWDATAPRO</div>
        <div style="font-size:.85rem;color:#6c7785;margin-top:2px;">Material Testing & Snow Data</div>
    </div>
    """).strip(),
    unsafe_allow_html=True,
)

if st.sidebar.button(
    "Dashboard",
    use_container_width=True,
    type="primary" if pagina == "Dashboard" else "secondary",
):
    cambia_pagina("Dashboard")

with st.sidebar.expander(
    "Sessioni",
    expanded=pagina in ["Nuova sessione", "Zero test"],
):
    if st.button(
        "Nuova sessione",
        use_container_width=True,
        type="primary" if pagina == "Nuova sessione" else "secondary",
    ):
        cambia_pagina("Nuova sessione")

    if st.button(
        "Zero test",
        use_container_width=True,
        type="primary" if pagina == "Zero test" else "secondary",
    ):
        cambia_pagina("Zero test")

with st.sidebar.expander(
    "Test materiali",
    expanded=pagina in ["Scorrimento e rigature", "Tenuta"],
):
    if st.button(
        "Scorrimento e rigature",
        use_container_width=True,
        type="primary" if pagina == "Scorrimento e rigature" else "secondary",
    ):
        cambia_pagina("Scorrimento e rigature")

    if st.button(
        "Scioline di tenuta",
        use_container_width=True,
        type="primary" if pagina == "Tenuta" else "secondary",
    ):
        cambia_pagina("Tenuta")

with st.sidebar.expander(
    "Archivio",
    expanded=pagina in ["Catalogo sci", "Storico", "Backup"],
):
    if st.button(
        "Catalogo sci",
        use_container_width=True,
        type="primary" if pagina == "Catalogo sci" else "secondary",
    ):
        cambia_pagina("Catalogo sci")

    if st.button(
        "Storico test",
        use_container_width=True,
        type="primary" if pagina == "Storico" else "secondary",
    ):
        cambia_pagina("Storico")

    if st.button(
        "Backup",
        use_container_width=True,
        type="primary" if pagina == "Backup" else "secondary",
    ):
        cambia_pagina("Backup")


# ============================================================
# PAGINE
# ============================================================

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
        st.warning("Crea prima una sessione.")
        st.stop()

    if len(sci) < 2:
        st.warning("Inserisci almeno due sci nel catalogo.")
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


elif pagina == "Scorrimento e rigature":
    mostra_banner(
        "Scorrimento e rigature",
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

    categoria = st.radio(
        "Categoria",
        ["Scorrimento", "Rigatura"],
        horizontal=True,
    )
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
            preparazione_a = st.text_input(
                "Prodotto / rigatura A",
                placeholder="es. Paraffina X / rigatura 1 mm"
            )

        with c2:
            st.markdown("#### Preparazione B")
            sci_b_label = st.selectbox(
                "Sci B",
                list(sci.keys()),
                index=1 if len(sci) > 1 else 0,
            )
            preparazione_b = st.text_input(
                "Prodotto / rigatura B",
                placeholder="es. Paraffina Y / rigatura 2 mm"
            )

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


elif pagina == "Tenuta":
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
    for tabella in ["sessioni", "sci", "zero_test", "test_materiali", "test_tenuta"]:
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
