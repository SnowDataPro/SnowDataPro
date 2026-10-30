import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import textwrap
import base64
from datetime import datetime, date
import math
from html import escape as html_escape

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
VERSIONE_DATABASE_APP = 8


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
            import libsql_experimental as libsql
        except ImportError as exc:
            raise RuntimeError(
                "Manca il pacchetto 'libsql-experimental'. Controlla requirements.txt."
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
            creato_il TEXT NOT NULL,
            codice TEXT,
            foto_url TEXT,
            foto_file TEXT,
            foto_data TEXT,
            foto_mime TEXT,
            foto_nome TEXT,
            temp_min REAL,
            temp_max REAL,
            tipo_temperatura TEXT,
            tipo_neve TEXT,
            snow_origine TEXT,
            snow_consistenza TEXT,
            snow_umidita TEXT,
            snow_forma_grano TEXT,
            snow_granulometria TEXT,
            snow_caratteristiche TEXT,
            umidita_min REAL,
            umidita_max REAL,
            temp_applicazione REAL,
            tipo_applicazione TEXT,
            temp_nuova_min REAL,
            temp_nuova_max REAL,
            temp_trasformata_min REAL,
            temp_trasformata_max REAL,
            url_fonte TEXT
        )
    """)

    # Migrazione non distruttiva per database SnowDataPro già esistenti.
    colonne_catalogo = {
        r[1] for r in conn.execute("PRAGMA table_info(catalogo_prodotti)").fetchall()
    }
    nuove_colonne_catalogo = {
        "codice": "TEXT",
        "foto_url": "TEXT",
        "foto_file": "TEXT",
        "foto_data": "TEXT",
        "foto_mime": "TEXT",
        "foto_nome": "TEXT",
        "temp_min": "REAL",
        "temp_max": "REAL",
        "tipo_temperatura": "TEXT",
        "tipo_neve": "TEXT",
        "snow_origine": "TEXT",
        "snow_consistenza": "TEXT",
        "snow_umidita": "TEXT",
        "snow_forma_grano": "TEXT",
        "snow_granulometria": "TEXT",
        "snow_caratteristiche": "TEXT",
        "umidita_min": "REAL",
        "umidita_max": "REAL",
        "temp_applicazione": "REAL",
        "tipo_applicazione": "TEXT",
        "temp_nuova_min": "REAL",
        "temp_nuova_max": "REAL",
        "temp_trasformata_min": "REAL",
        "temp_trasformata_max": "REAL",
        "url_fonte": "TEXT",
    }
    for nome_colonna, tipo_colonna in nuove_colonne_catalogo.items():
        if nome_colonna not in colonne_catalogo:
            conn.execute(
                f"ALTER TABLE catalogo_prodotti ADD COLUMN {nome_colonna} {tipo_colonna}"
            )

    # Normalizzazione non distruttiva delle categorie storiche.
    conn.execute("""
        UPDATE catalogo_prodotti
        SET tipo = 'Solida'
        WHERE categoria = 'scorrimento'
          AND LOWER(TRIM(COALESCE(tipo, ''))) = 'paraffina'
    """)
    conn.execute("""
        UPDATE catalogo_prodotti
        SET tipo = 'Liquido tampone'
        WHERE categoria = 'scorrimento'
          AND LOWER(TRIM(COALESCE(tipo, ''))) = 'liquido'
    """)

    # Aggiornamento nomenclatura consistenza neve.
    conn.execute("""
        UPDATE catalogo_prodotti
        SET snow_consistenza = REPLACE(
            snow_consistenza,
            'Soffice su superficie dura',
            'Soffice su fondo ghiacciato'
        )
        WHERE INSTR(COALESCE(snow_consistenza, ''), 'Soffice su superficie dura') > 0
    """)
    conn.execute("""
        UPDATE catalogo_prodotti
        SET tipo_neve = REPLACE(
            tipo_neve,
            'Soffice su superficie dura',
            'Soffice su fondo ghiacciato'
        )
        WHERE INSTR(COALESCE(tipo_neve, ''), 'Soffice su superficie dura') > 0
    """)

    # I prodotti già dotati di temperatura ferro vengono interpretati
    # come applicazione a caldo.
    conn.execute("""
        UPDATE catalogo_prodotti
        SET tipo_applicazione = 'A caldo'
        WHERE categoria = 'scorrimento'
          AND temp_applicazione IS NOT NULL
          AND TRIM(COALESCE(tipo_applicazione, '')) = ''
    """)

    # Backward compatibility: i vecchi intervalli tenuta vengono riportati
    # nel campo "neve nuova / cadente" se i nuovi campi dedicati sono ancora vuoti.
    conn.execute("""
        UPDATE catalogo_prodotti
        SET temp_nuova_min = temp_min,
            temp_nuova_max = temp_max
        WHERE categoria = 'tenuta'
          AND temp_nuova_min IS NULL
          AND temp_nuova_max IS NULL
          AND (temp_min IS NOT NULL OR temp_max IS NOT NULL)
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

st.markdown(
    """
    <style>

    /* ======================================================
       SECTOR G2 LAB - DESIGN SYSTEM
       ====================================================== */

    :root {
        --bg-main: #f4f6f8;
        --bg-sidebar: #eef1f4;
        --surface: #ffffff;
        --surface-soft: #f8fafb;

        --text-main: #1f2933;
        --text-secondary: #66737f;
        --text-light: #8a96a0;

        --border: #dce2e7;
        --border-strong: #c8d0d7;

        --accent: #395b68;
        --accent-dark: #294651;
        --accent-soft: #e9f0f3;

        --radius-small: 8px;
        --radius-medium: 12px;
        --radius-large: 16px;

        --shadow-soft: 0 2px 8px rgba(31, 41, 51, 0.05);
        --shadow-card: 0 4px 16px rgba(31, 41, 51, 0.06);
    }

    /* ======================================================
       INDICATORE DI CARICAMENTO STREAMLIT
       ====================================================== */

    @keyframes sector-loading-spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }

    [data-testid="stStatusWidgetRunningIcon"] > * {
        display: none !important;
    }

    [data-testid="stStatusWidgetRunningIcon"] {
        width: 22px !important;
        height: 22px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    [data-testid="stStatusWidgetRunningIcon"]::after {
        content: "";
        display: block;
        width: 17px;
        height: 17px;
        box-sizing: border-box;
        border: 3px solid rgba(0, 167, 225, 0.24);
        border-top-color: #00a7e1;
        border-right-color: #1677d2;
        border-radius: 50%;
        animation: sector-loading-spin 0.75s linear infinite;
    }


    /* ======================================================
       PAGINA
       ====================================================== */

    .stApp {
        background:
            linear-gradient(
                180deg,
                #f7f9fa 0px,
                #f4f6f8 260px,
                #f4f6f8 100%
            );
        color: var(--text-main);
    }

    .block-container {
        max-width: 1380px;
        padding-top: 2rem;
        padding-bottom: 4rem;
        padding-left: 2.4rem;
        padding-right: 2.4rem;
    }

    /* ======================================================
       BANNER STICKY / CONTENUTO CHE SCORRE SOPRA
       ====================================================== */

    /* Il contenitore Streamlit del banner resta fermo in alto.
       Il contenuto della pagina ha uno z-index superiore e,
       scorrendo, copre progressivamente il banner. */
    div[data-testid="stElementContainer"]:has(.sector-sticky-banner) {
        position: sticky !important;
        top: 0 !important;
        z-index: 1 !important;
        margin-bottom: 0 !important;
    }

    div[data-testid="stElementContainer"]:has(.sector-sticky-banner)
    [data-testid="stMarkdownContainer"] {
        margin-bottom: 0 !important;
    }

    div[class*="st-key-sector_page_content"] {
        position: relative !important;
        z-index: 5 !important;
        background:
            linear-gradient(
                180deg,
                #f7f9fa 0px,
                #f4f6f8 260px,
                #f4f6f8 100%
            ) !important;

        /* Full-bleed reale: il contenitore mantiene il contenuto allineato
           alla pagina, ma lo sfondo si estende per tutta la larghezza
           disponibile. In questo modo, scorrendo, copre il banner senza
           lasciare colonne laterali visibili. */
        width: calc(100% + 6rem) !important;
        max-width: none !important;
        box-sizing: border-box !important;
        margin-left: -3rem !important;
        margin-right: -3rem !important;
        padding-left: 3rem !important;
        padding-right: 3rem !important;
        padding-top: 22px !important;
        min-height: calc(100vh - 145px);
    }

    div[class*="st-key-sector_page_content"] > div {
        width: 100% !important;
        max-width: none !important;
        box-sizing: border-box !important;
    }

    @media (max-width: 900px) {
        div[class*="st-key-sector_page_content"] {
            width: calc(100% + 3.6rem) !important;
            margin-left: -1.8rem !important;
            margin-right: -1.8rem !important;
            padding-left: 1.8rem !important;
            padding-right: 1.8rem !important;
        }
    }


    /* ======================================================
       FONT E TESTI
       ====================================================== */

    html,
    body,
    [class*="css"],
    p,
    div,
    label,
    span,
    button,
    input,
    textarea,
    select {
        font-family:
            Inter,
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            Arial,
            sans-serif;
    }

    h1,
    h2,
    h3 {
        color: var(--text-main) !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
    }

    p {
        color: var(--text-secondary);
    }


    /* ======================================================
       SIDEBAR
       ====================================================== */

    section[data-testid="stSidebar"] {
        background-color: var(--bg-sidebar);
        border-right: 1px solid var(--border);
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 2rem;
    }

    section[data-testid="stSidebar"] label {
        color: var(--text-secondary);
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] {
        gap: 0.25rem;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        padding: 0.55rem 0.75rem;
        border-radius: var(--radius-small);
        transition: all 0.15s ease;
    }

    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        background-color: rgba(255,255,255,0.65);
    }


    /* ======================================================
       LOGO
       ====================================================== */

    .logo-container {
        display: flex;
        justify-content: center;
        align-items: center;
        width: 100%;
        padding: 0.5rem 0 1.5rem 0;
    }

    .logo-container img {
        display: block;
        max-width: 430px;
        width: 55%;
        height: auto;
        margin-left: auto;
        margin-right: auto;
    }


    /* ======================================================
       TITOLI
       ====================================================== */

    .main-title {
        text-align: center;
        color: var(--text-main);
        font-size: 1.8rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        margin-bottom: 2.4rem;
    }

    .section-title {
    color: #202529;
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: -0.02em;

    margin-top: 1.6rem;
    margin-bottom: 1.25rem;

    padding-bottom: 0.70rem;

    border-bottom: 1px solid #d8dde1;

    position: relative;
}

.section-title::after {
    content: "";

    position: absolute;

    bottom: -1px;
    left: 0;

    width: 42px;
    height: 2px;

    background: #00a7e1;
}

    /* ======================================================
       CARD METRICHE
       ====================================================== */

    .metric-card {
    position: relative;

    background: #ffffff;

    border: 1px solid #d9dee2;
    border-radius: 5px;

    padding: 1.25rem 1.35rem 1.15rem 1.35rem;

    min-height: 125px;

    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 3px 8px rgba(0,0,0,0.03);

    overflow: hidden;

    transition:
        border-color 0.15s ease,
        box-shadow 0.15s ease,
        transform 0.15s ease;
}


/* Riga azzurra superiore */
.metric-card::before {
    content: "";

    position: absolute;

    top: 0;
    left: 0;

    width: 100%;
    height: 3px;

    background: #00a7e1;
}


/* Effetto passaggio mouse */
.metric-card:hover {
    transform: translateY(-1px);

    border-color: #c4ccd1;

    box-shadow:
        0 2px 4px rgba(0,0,0,0.05),
        0 6px 14px rgba(0,0,0,0.05);
}


/* Nome parametro */
.metric-label {
    color: #68757d;

    font-size: 0.73rem;
    font-weight: 600;

    text-transform: uppercase;
    letter-spacing: 0.075em;

    margin-bottom: 0.75rem;
}


/* Valore principale */
.metric-value {
    color: #202529;

    font-size: 2rem;
    font-weight: 600;

    letter-spacing: -0.035em;
    line-height: 1.05;
}


/* Unità */
.metric-unit {
    color: #8b969c;

    font-size: 0.80rem;
    font-weight: 400;

    margin-top: 0.40rem;
}
    /* ======================================================
       BOX INFORMATIVI
       ====================================================== */

    .info-box {
        background-color: var(--accent-soft);

        border: 1px solid #d5e1e6;
        border-radius: var(--radius-small);

        padding: 1rem 1.1rem;

        color: #405864;

        margin: 1rem 0;
    }

    .warning-box {
        background-color: #fff9ec;

        border: 1px solid #eadcb6;
        border-radius: var(--radius-small);

        padding: 1rem 1.1rem;

        color: #6f5a25;

        margin: 1rem 0;
    }

    .success-box {
        background-color: #eff7f2;

        border: 1px solid #d0e2d5;
        border-radius: var(--radius-small);

        padding: 1rem 1.1rem;

        color: #355b42;

        margin: 1rem 0;
    }


    /* ======================================================
       PULSANTI
       ====================================================== */

    .stButton > button {
        min-height: 40px;

        border-radius: var(--radius-small);
        border: 1px solid var(--border-strong);

        background-color: var(--surface);
        color: var(--text-main);

        font-weight: 500;

        padding-left: 1rem;
        padding-right: 1rem;

        box-shadow: none;

        transition: all 0.15s ease;
    }

    .stButton > button:hover {
        border-color: var(--accent);
        color: var(--accent-dark);

        background-color: #f9fbfc;
    }

    .stButton > button[kind="primary"] {
        background-color: var(--accent);
        border-color: var(--accent);

        color: white;
    }

    .stButton > button[kind="primary"]:hover {
        background-color: var(--accent-dark);
        border-color: var(--accent-dark);

        color: white;
    }


    /* ======================================================
       INPUT
       ====================================================== */

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    div[data-baseweb="base-input"] {
        border-radius: var(--radius-small) !important;
        border-color: var(--border) !important;

        background-color: var(--surface) !important;
    }

    input,
    textarea {
        color: var(--text-main) !important;
    }

    textarea {
        border-radius: var(--radius-small) !important;
    }


    /* ======================================================
       DATAFRAME E TABELLE
       ====================================================== */

    div[data-testid="stDataFrame"] {
        background-color: var(--surface);

        border: 1px solid var(--border);
        border-radius: var(--radius-medium);

        /* La tabella Streamlit possiede già la propria barra orizzontale. */
        overflow: hidden !important;

        box-shadow: var(--shadow-soft);

        /* Nasconde la scrollbar del contenitore esterno, non quella interna. */
        scrollbar-width: none !important;
        -ms-overflow-style: none !important;
    }

    div[data-testid="stDataFrame"]::-webkit-scrollbar {
        width: 0 !important;
        height: 0 !important;
        display: none !important;
    }

    table {
        border-radius: var(--radius-small);
    }


    /* ======================================================
       DIVIDER
       ====================================================== */

    hr {
        border: none !important;
        border-top: 1px solid var(--border) !important;

        margin-top: 2rem !important;
        margin-bottom: 2rem !important;
    }


    /* ======================================================
       STREAMLIT
       ====================================================== */

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    header[data-testid="stHeader"] {
        background-color: transparent;
    }


    /* ======================================================
       RESPONSIVE
       ====================================================== */

    @media (max-width: 900px) {

        .block-container {
            padding-left: 1.2rem;
            padding-right: 1.2rem;
        }

        .metric-value {
            font-size: 1.65rem;
        }

    }

/* ======================================================
   SECTOR G2 LAB - DARK NAVIGATION
   ====================================================== */

/* Sidebar principale */
section[data-testid="stSidebar"] {
    background: #191c1e !important;
    border-right: 1px solid #2b3033 !important;
}

/* Spaziatura interna */
section[data-testid="stSidebar"] > div {
    padding-top: 1.8rem;
}


/* ======================================================
   BRAND
   ====================================================== */

.sidebar-brand {
    padding: 0.4rem 0.25rem 1.5rem 0.25rem;
}

.sidebar-brand-main {
    color: #ffffff;
    font-size: 1.05rem;
    font-weight: 600;
    letter-spacing: 0.08em;
}

.sidebar-brand-sub {
    color: #8f9ba2;
    font-size: 0.82rem;
    margin-top: 0.25rem;
}


/* ======================================================
   PULSANTI MENU
   ====================================================== */

section[data-testid="stSidebar"] .stButton > button {
    width: 100%;

    min-height: 44px;

    justify-content: flex-start;

    background: transparent !important;

    color: #c9d0d4 !important;

    border: none !important;
    border-radius: 3px !important;

    padding-left: 1rem !important;

    font-weight: 400;

    box-shadow: none !important;

    transition:
        background-color 0.15s ease,
        color 0.15s ease;
}


/* Hover */
section[data-testid="stSidebar"] .stButton > button:hover {
    background-color: #252a2d !important;

    color: #ffffff !important;

    border: none !important;
}


/* Voce attiva */
section[data-testid="stSidebar"]
.stButton > button[kind="primary"] {

    background-color: #252a2d !important;

    color: #ffffff !important;

    border-left: 4px solid #00a7e1 !important;

    border-radius: 2px !important;

    font-weight: 500;
}


/* ======================================================
   EXPANDER
   ====================================================== */

section[data-testid="stSidebar"]
[data-testid="stExpander"] {

    background: transparent !important;

    border: none !important;

    border-radius: 3px !important;

    margin-top: 0.35rem;
}


/* Riga principale expander */
section[data-testid="stSidebar"]
[data-testid="stExpander"] summary {

    background: transparent !important;

    color: #c9d0d4 !important;

    border-radius: 3px !important;

    min-height: 44px;

    padding-left: 0.4rem;

    transition:
        background-color 0.15s ease,
        color 0.15s ease;
}


/* Hover expander */
section[data-testid="stSidebar"]
[data-testid="stExpander"] summary:hover {

    background-color: #252a2d !important;

    color: #ffffff !important;
}


/* Testo expander */
section[data-testid="stSidebar"]
[data-testid="stExpander"] summary p {

    color: inherit !important;

    font-weight: 400 !important;
}


/* Freccia */
section[data-testid="stSidebar"]
[data-testid="stExpander"] svg {

    fill: #9ba6ac !important;
}


/* Contenuto sotto l'expander */
section[data-testid="stSidebar"]
[data-testid="stExpander"] > details > div {

    padding-left: 0.65rem;
}


/* Pulsanti interni leggermente più piccoli */
section[data-testid="stSidebar"]
[data-testid="stExpander"]
.stButton > button {

    min-height: 39px;

    font-size: 0.90rem;

    padding-left: 1.25rem !important;
}


/* ======================================================
   TESTI SIDEBAR
   ====================================================== */

section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label {

    color: #c9d0d4;
}


/* ======================================================
   SCROLLBAR SIDEBAR
   ====================================================== */

section[data-testid="stSidebar"] ::-webkit-scrollbar {
    width: 6px;
}

section[data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
    background: #41484c;
    border-radius: 10px;
}


/* ======================================================
   CONTROLLI STREAMLIT
   ====================================================== */

/* Nasconde solo gli elementi non necessari, senza nascondere
   il comando che permette di riaprire la sidebar. */
[data-testid="stDecoration"] {
    display: none !important;
}

.stDeployButton,
[data-testid="stDeployButton"] {
    display: none !important;
    visibility: hidden !important;
}

/* Il pulsante di riapertura deve restare sempre disponibile. Nelle versioni
   recenti di Streamlit vive dentro l'header/toolbar, che quindi non va nascosto. */
header[data-testid="stHeader"] {
    display: flex !important;
    visibility: visible !important;
    pointer-events: auto !important;
    z-index: 999998 !important;
}

[data-testid="stSidebarCollapsedControl"],
button[aria-label="Open sidebar"],
button[title="Open sidebar"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999999 !important;
}

/* Mantiene visibile anche il normale comando di chiusura/apertura. */
[data-testid="stSidebarCollapseButton"],
button[aria-label="Collapse sidebar"],
button[title="Collapse sidebar"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
}

[data-testid="stSidebarCollapsedControl"] button,
button[aria-label="Open sidebar"],
button[title="Open sidebar"] {
    background: #ffffff !important;
    color: #1f2933 !important;
    border: 1px solid #c8d0d7 !important;
    border-radius: 6px !important;
    box-shadow: 0 2px 8px rgba(31, 41, 51, 0.12) !important;
}

[data-testid="stSidebarCollapsedControl"] svg,
button[aria-label="Open sidebar"] svg,
button[title="Open sidebar"] svg {
    color: #1f2933 !important;
    fill: #1f2933 !important;
}

/* Allinea le voci del menu a sinistra */
section[data-testid="stSidebar"] .stButton > button {
    justify-content: flex-start !important;
    text-align: left !important;
}

section[data-testid="stSidebar"]
.stButton > button [data-testid="stMarkdownContainer"] {
    width: 100%;
    text-align: left !important;
}
/* Porta Dashboard sulla stessa linea delle altre voci */
section[data-testid="stSidebar"] > div
[data-testid="stSidebarContent"]
.stButton > button {
    padding-left: 0.65rem !important;
}
/* Centra il logo nella sidebar */
section[data-testid="stSidebar"] [data-testid="stImage"] {
    display: flex;
    justify-content: center;
    width: 100%;
}

section[data-testid="stSidebar"] [data-testid="stImage"] img {
    margin-left: auto;
    margin-right: auto;
}
/* Dashboard: icona e testo realmente a sinistra */
section[data-testid="stSidebar"] .stButton button {
    justify-content: flex-start !important;
    text-align: left !important;
    padding-left: 0.65rem !important;
}

section[data-testid="stSidebar"] .stButton button > div {
    justify-content: flex-start !important;
    width: 100% !important;
}

section[data-testid="stSidebar"] .stButton button p {
    text-align: left !important;
}

    /* Dashboard: icona e testo realmente a sinistra */
    section[data-testid="stSidebar"] .stButton button p {
        text-align: left !important;
    }

/* ======================================================
   ANALISI - SELETTORE TECNICHE
   ====================================================== */

[data-testid="stMultiSelect"] [data-baseweb="tag"] {
    background-color: #e9eef1 !important;
    border: 1px solid #cbd5da !important;
    border-radius: 5px !important;
    box-shadow: none !important;
}

[data-testid="stMultiSelect"] [data-baseweb="tag"] * {
    color: #34444d !important;
}

[data-testid="stMultiSelect"] [data-baseweb="tag"] svg {
    fill: #718088 !important;
    color: #718088 !important;
}

[data-testid="stMultiSelect"] [data-baseweb="tag"]:hover {
    background-color: #dde7eb !important;
    border-color: #00a7e1 !important;
}

/* ======================================================
   ANALISI - PULSANTI TECNICHE
   ====================================================== */

/* Struttura generale V1 / V2 / DP / DS */
div[class*="st-key-filtro_tecnica_"] button {
    min-height: 44px !important;

    border-radius: 5px !important;

    font-weight: 600 !important;

    box-shadow: none !important;

    transition:
        background-color 0.15s ease,
        border-color 0.15s ease,
        color 0.15s ease !important;
}


/* TECNICA SELEZIONATA */
div[class*="st-key-filtro_tecnica_"] button[kind="primary"],
div[class*="st-key-filtro_tecnica_"] button[data-testid="stBaseButton-primary"] {

    background: #eaf7fc !important;

    border: 1px solid #00a7e1 !important;

    color: #26353d !important;
}


/* Testo tecnica selezionata */
div[class*="st-key-filtro_tecnica_"] button[kind="primary"] p,
div[class*="st-key-filtro_tecnica_"] button[data-testid="stBaseButton-primary"] p {

    color: #26353d !important;

    font-weight: 600 !important;
}


/* TECNICA NON SELEZIONATA */
div[class*="st-key-filtro_tecnica_"] button[kind="secondary"],
div[class*="st-key-filtro_tecnica_"] button[data-testid="stBaseButton-secondary"] {

    background: #ffffff !important;

    border: 1px solid #d5dce0 !important;

    color: #7a858c !important;
}

/* Testo tecnica non selezionata */
div[class*="st-key-filtro_tecnica_"] button[kind="secondary"] p,
div[class*="st-key-filtro_tecnica_"] button[data-testid="stBaseButton-secondary"] p {

    color: #7a858c !important;
}


/* Hover */
div[class*="st-key-filtro_tecnica_"] button:hover {

    background: #f1f8fa !important;

    border-color: #00a7e1 !important;

    color: #26353d !important;
}
/* ======================================================
   PULSANTE SALVA ALLENAMENTO
   ====================================================== */

div[class*="st-key-salva_allenamento"] button {
    min-width: 190px !important;
    height: 48px !important;
    background: #00a7e1 !important;
    border: 1px solid #00a7e1 !important;
    border-radius: 5px !important;
    box-shadow: none !important;
    font-weight: 600 !important;
    transition:
        background-color 0.15s ease,
        border-color 0.15s ease !important;
}

div[class*="st-key-salva_allenamento"] button p {
    color: #ffffff !important;
    font-weight: 600 !important;
}

div[class*="st-key-salva_allenamento"] button:hover {
    background: #0095c9 !important;
    border-color: #0095c9 !important;
}

div[class*="st-key-salva_allenamento"] button:hover p {
    color: #ffffff !important;
}

/* ======================================================
   AMTP - CARD PERCENTUALE
   ====================================================== */

div[class*="st-key-percentuale_amtp_card"] {
    position: relative;

    background: #ffffff;

    border: 1px solid #d9dee2;
    border-radius: 5px;

    padding: 1.25rem 1.35rem 1.15rem 1.35rem;

    height: 165px !important;
    min-height: 165px !important;
    box-sizing: border-box !important;

    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 3px 8px rgba(0,0,0,0.03);

    overflow: hidden;

    transition:
        border-color 0.15s ease,
        box-shadow 0.15s ease,
        transform 0.15s ease;
}

/* Elimina il gap verticale automatico di Streamlit dentro la card */
div[class*="st-key-percentuale_amtp_card"] [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}

/* La card W/kg della stessa sezione ha esattamente la stessa altezza */
div[class*="st-key-wkg_percentuale_card"] .metric-card {
    height: 165px !important;
    min-height: 165px !important;
    box-sizing: border-box !important;
}

div[class*="st-key-percentuale_amtp_card"]::before {
    content: "";

    position: absolute;

    top: 0;
    left: 0;

    width: 100%;
    height: 3px;

    background: #00a7e1;
}

div[class*="st-key-percentuale_amtp_card"]:hover {
    transform: translateY(-1px);

    border-color: #c4ccd1;

    box-shadow:
        0 2px 4px rgba(0,0,0,0.05),
        0 6px 14px rgba(0,0,0,0.05);
}

/* Toglie lo spazio standard sopra/sotto al number input */
div[class*="st-key-percentuale_amtp_card"] [data-testid="stNumberInput"] {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

/* Corpo del controllo: bianco, pulito, senza il classico box grigio Streamlit */
div[class*="st-key-percentuale_amtp_card"] [data-testid="stNumberInput"] div[data-baseweb="input"],
div[class*="st-key-percentuale_amtp_card"] [data-testid="stNumberInput"] div[data-baseweb="input"] > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* Valore numerico grande, coerente con le metric card */
div[class*="st-key-percentuale_amtp_card"] [data-testid="stNumberInput"] input {
    background: transparent !important;

    border: none !important;

    color: #202529 !important;

    font-size: 2rem !important;
    font-weight: 600 !important;

    letter-spacing: -0.035em !important;

    padding-left: 0 !important;

    min-height: 42px !important;
}

/* Pulsanti - / + più discreti */
div[class*="st-key-percentuale_amtp_card"] [data-testid="stNumberInput"] button {
    width: 34px !important;
    min-width: 34px !important;
    height: 34px !important;
    min-height: 34px !important;

    margin-left: 5px !important;

    background: #f8fafb !important;

    border: 1px solid #d9dee2 !important;
    border-radius: 5px !important;

    color: #65727a !important;

    box-shadow: none !important;
}

div[class*="st-key-percentuale_amtp_card"] [data-testid="stNumberInput"] button:hover {
    background: #eef7fa !important;

    border-color: #00a7e1 !important;

    color: #26353d !important;
}

/* Evita che eventuali contenitori interni aggiungano bordi */
div[class*="st-key-percentuale_amtp_card"] [data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
}

/* Posizione dell'unità identica alla metric-unit standard */
div[class*="st-key-percentuale_amtp_card"] .percentuale-unit {
    margin-top: 0.40rem !important;
    margin-bottom: 0 !important;
}

div[class*="st-key-percentuale_amtp_card"] [data-testid="stMarkdown"] {
    margin-bottom: 0 !important;
}


/* ======================================================
   CALCOLO POTENZA - CARD POTENZA TARGET
   Stessa grafica della card Percentuale AMTP
   ====================================================== */

div[class*="st-key-potenza_target_card"] {
    position: relative;

    background: #ffffff;

    border: 1px solid #d9dee2;
    border-radius: 5px;

    padding: 1.25rem 1.35rem 1.15rem 1.35rem;

    height: 165px !important;
    min-height: 165px !important;
    box-sizing: border-box !important;

    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 3px 8px rgba(0,0,0,0.03);

    overflow: hidden;

    transition:
        border-color 0.15s ease,
        box-shadow 0.15s ease,
        transform 0.15s ease;
}

div[class*="st-key-potenza_target_card"] [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}

div[class*="st-key-potenza_target_card"]::before {
    content: "";

    position: absolute;

    top: 0;
    left: 0;

    width: 100%;
    height: 3px;

    background: #00a7e1;
}

div[class*="st-key-potenza_target_card"]:hover {
    transform: translateY(-1px);

    border-color: #c4ccd1;

    box-shadow:
        0 2px 4px rgba(0,0,0,0.05),
        0 6px 14px rgba(0,0,0,0.05);
}

div[class*="st-key-potenza_target_card"] [data-testid="stNumberInput"] {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stNumberInput"] div[data-baseweb="input"],
div[class*="st-key-potenza_target_card"] [data-testid="stNumberInput"] div[data-baseweb="input"] > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stNumberInput"] input {
    background: transparent !important;

    border: none !important;

    color: #202529 !important;

    font-size: 2rem !important;
    font-weight: 600 !important;

    letter-spacing: -0.035em !important;

    padding-left: 0 !important;

    min-height: 42px !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stNumberInput"] button {
    width: 34px !important;
    min-width: 34px !important;
    height: 34px !important;
    min-height: 34px !important;

    margin-left: 5px !important;

    background: #f8fafb !important;

    border: 1px solid #d9dee2 !important;
    border-radius: 5px !important;

    color: #65727a !important;

    box-shadow: none !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stNumberInput"] button:hover {
    background: #eef7fa !important;

    border-color: #00a7e1 !important;

    color: #26353d !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
}

div[class*="st-key-potenza_target_card"] .potenza-target-unit {
    margin-top: 0.40rem !important;
    margin-bottom: 0 !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stMarkdown"] {
    margin-bottom: 0 !important;
}

/* ======================================================
   CALCOLO POTENZA - CARD PENDENZA TARGET
   Stessa grafica della card Potenza target / Percentuale AMTP
   ====================================================== */

div[class*="st-key-pendenza_target_card"] {
    position: relative;

    background: #ffffff;

    border: 1px solid #d9dee2;
    border-radius: 5px;

    padding: 1.25rem 1.35rem 1.15rem 1.35rem;

    height: 165px !important;
    min-height: 165px !important;
    box-sizing: border-box !important;

    box-shadow:
        0 1px 2px rgba(0,0,0,0.04),
        0 3px 8px rgba(0,0,0,0.03);

    overflow: hidden;

    transition:
        border-color 0.15s ease,
        box-shadow 0.15s ease,
        transform 0.15s ease;
}

div[class*="st-key-pendenza_target_card"] [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}

div[class*="st-key-pendenza_target_card"]::before {
    content: "";

    position: absolute;

    top: 0;
    left: 0;

    width: 100%;
    height: 3px;

    background: #00a7e1;
}

div[class*="st-key-pendenza_target_card"]:hover {
    transform: translateY(-1px);

    border-color: #c4ccd1;

    box-shadow:
        0 2px 4px rgba(0,0,0,0.05),
        0 6px 14px rgba(0,0,0,0.05);
}

div[class*="st-key-pendenza_target_card"] [data-testid="stNumberInput"] {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

div[class*="st-key-pendenza_target_card"] [data-testid="stNumberInput"] div[data-baseweb="input"],
div[class*="st-key-pendenza_target_card"] [data-testid="stNumberInput"] div[data-baseweb="input"] > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

div[class*="st-key-pendenza_target_card"] [data-testid="stNumberInput"] input {
    background: transparent !important;

    border: none !important;

    color: #202529 !important;

    font-size: 2rem !important;
    font-weight: 600 !important;

    letter-spacing: -0.035em !important;

    padding-left: 0 !important;

    min-height: 42px !important;
}

div[class*="st-key-pendenza_target_card"] [data-testid="stNumberInput"] button {
    width: 34px !important;
    min-width: 34px !important;
    height: 34px !important;
    min-height: 34px !important;

    margin-left: 5px !important;

    background: #f8fafb !important;

    border: 1px solid #d9dee2 !important;
    border-radius: 5px !important;

    color: #65727a !important;

    box-shadow: none !important;
}

div[class*="st-key-pendenza_target_card"] [data-testid="stNumberInput"] button:hover {
    background: #eef7fa !important;

    border-color: #00a7e1 !important;

    color: #26353d !important;
}

div[class*="st-key-pendenza_target_card"] [data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
}

div[class*="st-key-pendenza_target_card"] .pendenza-target-unit {
    margin-top: 0.40rem !important;
    margin-bottom: 0 !important;
}

div[class*="st-key-pendenza_target_card"] [data-testid="stMarkdown"] {
    margin-bottom: 0 !important;
}

/* Stepper decimali: stesso aspetto del controllo Percentuale AMTP. */
div[class*="st-key-potenza_target_card"] [data-testid="stHorizontalBlock"],
div[class*="st-key-pendenza_target_card"] [data-testid="stHorizontalBlock"] {
    gap: 0.45rem !important;
    align-items: center !important;
    min-height: 52px !important;
    padding: 0 0.25rem 0 0 !important;
    background: #f1f3f5 !important;
    border-radius: 5px !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stTextInput"],
div[class*="st-key-pendenza_target_card"] [data-testid="stTextInput"] {
    margin: 0 !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stTextInput"] div[data-baseweb="input"],
div[class*="st-key-pendenza_target_card"] [data-testid="stTextInput"] div[data-baseweb="input"] {
    min-height: 52px !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

div[class*="st-key-potenza_target_card"] [data-testid="stTextInput"] input,
div[class*="st-key-pendenza_target_card"] [data-testid="stTextInput"] input {
    min-height: 52px !important;
    padding: 0 0 0 0.2rem !important;
    background: transparent !important;
    border: none !important;
    color: #202529 !important;
    font-size: 2rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.035em !important;
}

div[class*="st-key-potenza_target_riferimento_input_velocita_step_meno"] button,
div[class*="st-key-potenza_target_riferimento_input_velocita_step_piu"] button,
div[class*="st-key-pendenza_target_input_velocita_step_meno"] button,
div[class*="st-key-pendenza_target_input_velocita_step_piu"] button {
    width: 34px !important;
    min-width: 34px !important;
    height: 34px !important;
    min-height: 34px !important;
    padding: 0 !important;
    background: #f8fafb !important;
    border: 1px solid #d9dee2 !important;
    border-radius: 5px !important;
    color: #65727a !important;
    box-shadow: none !important;
}

div[class*="st-key-potenza_target_riferimento_input_velocita_step_meno"] button p,
div[class*="st-key-potenza_target_riferimento_input_velocita_step_piu"] button p,
div[class*="st-key-pendenza_target_input_velocita_step_meno"] button p,
div[class*="st-key-pendenza_target_input_velocita_step_piu"] button p {
    margin: 0 !important;
    color: #65727a !important;
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    line-height: 1 !important;
}

div[class*="st-key-potenza_target_riferimento_input_velocita_step_meno"] button:hover,
div[class*="st-key-potenza_target_riferimento_input_velocita_step_piu"] button:hover,
div[class*="st-key-pendenza_target_input_velocita_step_meno"] button:hover,
div[class*="st-key-pendenza_target_input_velocita_step_piu"] button:hover {
    background: #eef7fa !important;
    border-color: #00a7e1 !important;
    color: #26353d !important;
}

div[class*="st-key-potenza_target_riferimento_input_velocita_step_meno"] button:hover p,
div[class*="st-key-potenza_target_riferimento_input_velocita_step_piu"] button:hover p,
div[class*="st-key-pendenza_target_input_velocita_step_meno"] button:hover p,
div[class*="st-key-pendenza_target_input_velocita_step_piu"] button:hover p {
    color: #26353d !important;
}

/* ======================================================
   PULSANTI TEST DI RIFERIMENTO
   Stessa grafica di "Salva allenamento"
   ====================================================== */

div[class*="st-key-salva_test_riferimento"] button,
div[class*="st-key-salva_modifiche_test_riferimento"] button,
div[class*="st-key-apri_modifica_test_riferimento"] button {
    min-width: 190px !important;
    height: 48px !important;
    background: #00a7e1 !important;
    border: 1px solid #00a7e1 !important;
    border-radius: 5px !important;
    box-shadow: none !important;
    font-weight: 600 !important;
    transition:
        background-color 0.15s ease,
        border-color 0.15s ease !important;
}

div[class*="st-key-salva_test_riferimento"] button p,
div[class*="st-key-salva_modifiche_test_riferimento"] button p,
div[class*="st-key-apri_modifica_test_riferimento"] button p {
    color: #ffffff !important;
    font-weight: 600 !important;
}

div[class*="st-key-salva_test_riferimento"] button:hover,
div[class*="st-key-salva_modifiche_test_riferimento"] button:hover,
div[class*="st-key-apri_modifica_test_riferimento"] button:hover {
    background: #0095c9 !important;
    border-color: #0095c9 !important;
}

div[class*="st-key-salva_test_riferimento"] button:hover p,
div[class*="st-key-salva_modifiche_test_riferimento"] button:hover p,
div[class*="st-key-apri_modifica_test_riferimento"] button:hover p {
    color: #ffffff !important;
}

/* Elimina test: stessa grafica di "Elimina allenamento" */
div[class*="st-key-elimina_test_riferimento"] button:not(:disabled) {
    min-width: 205px !important;
    height: 48px !important;
    background: #ffffff !important;
    border: 1px solid #d9534f !important;
    border-radius: 5px !important;
    box-shadow: none !important;
    font-weight: 600 !important;
    transition:
        background-color 0.15s ease,
        border-color 0.15s ease,
        color 0.15s ease !important;
}

div[class*="st-key-elimina_test_riferimento"] button:not(:disabled) p {
    color: #d9534f !important;
    font-weight: 600 !important;
}

div[class*="st-key-elimina_test_riferimento"] button:not(:disabled):hover {
    background: #d9534f !important;
    border-color: #d9534f !important;
}

div[class*="st-key-elimina_test_riferimento"] button:not(:disabled):hover p {
    color: #ffffff !important;
}

/* ======================================================
   CAMPI DI INSERIMENTO CHIARI
   Compatibile con i componenti BaseWeb usati da Streamlit Cloud.
   ====================================================== */

[data-testid="stTextInput"] div[data-baseweb="input"],
[data-testid="stNumberInput"] div[data-baseweb="input"],
[data-testid="stDateInput"] div[data-baseweb="input"],
[data-testid="stTimeInput"] div[data-baseweb="input"],
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stMultiSelect"] div[data-baseweb="select"] > div,
div[data-baseweb="input"],
div[data-baseweb="base-input"],
div[data-baseweb="select"] > div,
[data-testid="stTextArea"] textarea {
    background-color: #eef1f4 !important;
    color: #1f2933 !important;
    border-color: #c8d0d7 !important;
    box-shadow: none !important;
}

input,
textarea,
div[data-baseweb="input"] input,
div[data-baseweb="base-input"] input,
div[data-baseweb="select"] input {
    background-color: transparent !important;
    color: #1f2933 !important;
    -webkit-text-fill-color: #1f2933 !important;
    caret-color: #1f2933 !important;
}

input::placeholder,
textarea::placeholder {
    color: #78848d !important;
    -webkit-text-fill-color: #78848d !important;
    opacity: 1 !important;
}

div[data-baseweb="select"] span,
div[data-baseweb="select"] [role="button"],
div[data-baseweb="input"] span {
    color: #1f2933 !important;
    -webkit-text-fill-color: #1f2933 !important;
}

div[data-baseweb="select"] svg,
[data-testid="stDateInput"] svg,
[data-testid="stTimeInput"] svg,
[data-testid="stNumberInput"] svg {
    color: #4d5961 !important;
    fill: #4d5961 !important;
}

[data-testid="stNumberInput"] button {
    background-color: #e2e7eb !important;
    color: #1f2933 !important;
    border-color: #c8d0d7 !important;
}

[data-testid="stFileUploaderDropzone"] {
    background-color: #eef1f4 !important;
    color: #1f2933 !important;
    border-color: #c8d0d7 !important;
}

div[data-baseweb="popover"] ul,
div[role="listbox"] {
    background-color: #ffffff !important;
    color: #1f2933 !important;
}

div[role="option"] {
    background-color: #ffffff !important;
    color: #1f2933 !important;
}

div[role="option"]:hover,
div[role="option"][aria-selected="true"] {
    background-color: #e7edf1 !important;
}
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <style>

    /* ======================================================
       SNOWDATAPRO - SOLO LAYOUT CATALOGO
       I colori e i widget vengono dal design system Sector G2 Lab.
       ====================================================== */

    div[class*="st-key-catalog_form_panel_"] {
        background: #ffffff !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-medium) !important;
        padding: 1.15rem 1.25rem 1.25rem 1.25rem !important;
        box-shadow: var(--shadow-soft) !important;
        margin-bottom: 1.25rem !important;
    }

    div[class*="st-key-catalog_filter_panel_"] {
        background: #ffffff !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-medium) !important;
        padding: 1.05rem 1.15rem 1rem 1.15rem !important;
        box-shadow: var(--shadow-soft) !important;
        margin-bottom: 1.05rem !important;
    }

    .catalog-filter-title {
        color: var(--text-primary);
        font-size: 1.02rem;
        font-weight: 700;
        line-height: 1.15;
        margin: 0;
    }

    .catalog-filter-subtitle {
        color: var(--text-light);
        font-size: 0.78rem;
        line-height: 1.25;
        margin-top: 0.16rem;
        margin-bottom: 0.10rem;
    }

    .catalog-filter-section-title {
        color: var(--text-secondary);
        font-size: 0.78rem;
        font-weight: 700;
        line-height: 1.2;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        margin: 0 0 0.45rem 0;
    }

.snow-reference-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-large);
    box-shadow: var(--shadow-soft);
    overflow: hidden;
    margin-top: 0.35rem;
    margin-bottom: 0.9rem;
}

.snow-reference-header {
    padding: 1rem 1.15rem 0.25rem 1.15rem;
}

.snow-reference-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.8rem;
    margin-top: 0.2rem;
}

.snow-reference-mini {
    background: var(--surface-soft);
    border: 1px solid var(--border);
    border-radius: var(--radius-medium);
    padding: 0.9rem 1rem;
}

.snow-reference-mini-title {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-bottom: 0.25rem;
}

.snow-reference-mini-text {
    font-size: 0.95rem;
    line-height: 1.45;
    color: var(--text-main);
}

.snow-reference-table-wrap {
    width: 100%;
    overflow-x: auto;
    padding: 0 1.15rem 1.05rem 1.15rem;
}

.snow-reference-table {
    width: 100%;
    min-width: 1080px;
    border-collapse: collapse;
    table-layout: auto;
}

.snow-reference-table th,
.snow-reference-table td {
    border: 1px solid var(--border);
    padding: 0.72rem 0.78rem;
    vertical-align: top;
    text-align: left;
    white-space: normal !important;
    word-break: normal;
    overflow-wrap: anywhere;
    line-height: 1.4;
    font-size: 0.95rem;
}

.snow-reference-table th {
    background: #f1f5f7;
    font-weight: 700;
    color: var(--text-main);
}

.snow-reference-note {
    padding: 0 1.15rem 1rem 1.15rem;
    color: var(--text-secondary);
    font-size: 0.95rem;
    line-height: 1.45;
}

.snow-classification-card {
    background: var(--surface-soft);
    border: 1px solid var(--border);
    border-radius: var(--radius-medium);
    padding: 0.9rem 1rem;
    margin-top: 0.25rem;
    margin-bottom: 0.35rem;
}

.snow-classification-title {
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--text-main);
    margin-bottom: 0.2rem;
}

.snow-classification-caption {
    font-size: 0.86rem;
    line-height: 1.45;
    color: var(--text-secondary);
    margin-bottom: 0.2rem;
}


.snow-detail-panel {
    background: #f7f9fa;
    border: 1px solid var(--border);
    border-radius: var(--radius-medium);
    padding: 0.72rem;
    margin: 0.55rem 0 0.80rem 0;
}

.snow-detail-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin-bottom: 0.58rem;
}

.snow-detail-title {
    font-size: 0.84rem;
    font-weight: 700;
    color: var(--text-main);
    letter-spacing: 0.01em;
}

.snow-detail-grid {
    display: flex;
    flex-direction: column;
    gap: 0.42rem;
}

.snow-detail-item {
    min-width: 0;
    background: #ffffff;
    border: 1px solid #dfe5e9;
    border-radius: 8px;
    padding: 0.58rem 0.62rem 0.62rem 0.62rem;
}

.snow-detail-label {
    margin-bottom: 0.34rem;
    color: var(--text-light);
    font-size: 0.66rem;
    font-weight: 700;
    line-height: 1.15;
    letter-spacing: 0.055em;
    text-transform: uppercase;
}

.snow-detail-values {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.28rem;
    min-width: 0;
}

.snow-detail-chip {
    display: inline-flex;
    align-items: center;
    max-width: 100%;
    padding: 0.23rem 0.46rem;
    border: 1px solid #d6e0e5;
    border-radius: 999px;
    background: #eef3f5;
    color: #33434d;
    font-size: 0.74rem;
    font-weight: 500;
    line-height: 1.25;
    white-space: normal;
    overflow-wrap: anywhere;
}

@media (max-width: 900px) {
    .snow-reference-grid {
        grid-template-columns: 1fr;
    }
}

    div[class*="st-key-filter_temp_aria_group_"],
    div[class*="st-key-filter_temp_neve_group_"],
    div[class*="st-key-filter_snow_group_"] {
        background: #f7f9fa !important;
        border: 1px solid #e1e6ea !important;
        border-radius: 10px !important;
        padding: 0.90rem 0.95rem 0.78rem 0.95rem !important;
        box-shadow: 0 1px 3px rgba(31, 41, 51, 0.025) !important;
    }

    div[class*="st-key-filter_temp_aria_group_"],
    div[class*="st-key-filter_temp_neve_group_"] {
        min-height: 178px !important;
    }

    div[class*="st-key-filter_snow_group_"] {
        min-height: 112px !important;
    }

    .catalog-temperature-card-title {
        color: var(--text-main);
        font-size: 0.93rem;
        font-weight: 700;
        line-height: 1.2;
        margin-bottom: 0.14rem;
    }

    .catalog-temperature-card-subtitle {
        color: var(--text-light);
        font-size: 0.76rem;
        line-height: 1.35;
        min-height: 2.1rem;
        margin-bottom: 0.28rem;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stSlider"],
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stSlider"],
    div[class*="st-key-filter_snow_group_"] [data-testid="stMultiSelect"] {
        margin-top: 0.18rem !important;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stToggle"],
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stToggle"] {
        margin-bottom: 0.20rem !important;
    }

    div[class*="st-key-filter_reset_"] button {
        min-height: 38px !important;
        height: 38px !important;
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
        border-radius: 6px !important;
        background: #ffffff !important;
        border: 1px solid var(--border-strong) !important;
        box-shadow: none !important;
    }

    div[class*="st-key-filter_reset_"] button p {
        color: var(--text-secondary) !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
    }

    div[class*="st-key-filter_reset_"] button:hover {
        background: #f5f7f8 !important;
        border-color: #aeb8bf !important;
    }

    /* Slider più sobrio e coerente con il design Sector. */
    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stSlider"],
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stSlider"] {
        padding-top: 0.05rem !important;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stSlider"] p,
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stSlider"] p {
        font-size: 0.82rem !important;
    }

    div[class*="st-key-catalog_card_"] {
        background: #ffffff !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-medium) !important;
        padding: 0.9rem 0.95rem 0.8rem 0.95rem !important;
        min-height: 335px !important;
        box-shadow: var(--shadow-soft) !important;
    }

    /* Dimensioni standard identiche tra i campi del form. */
    div[class*="st-key-catalog_form_panel_"]
    [data-testid="stTextInput"] div[data-baseweb="input"],

    div[class*="st-key-catalog_form_panel_"]
    [data-testid="stNumberInput"] div[data-baseweb="input"],

    div[class*="st-key-catalog_form_panel_"]
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,

    div[class*="st-key-catalog_form_panel_"]
    [data-testid="stMultiSelect"] div[data-baseweb="select"] > div,

    div[class*="st-key-catalog_filter_panel_"]
    [data-testid="stTextInput"] div[data-baseweb="input"],

    div[class*="st-key-catalog_filter_panel_"]
    [data-testid="stNumberInput"] div[data-baseweb="input"],

    div[class*="st-key-catalog_filter_panel_"]
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,

    div[class*="st-key-catalog_filter_panel_"]
    [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
        min-height: 48px !important;
        height: 48px !important;
    }

    /* Foto più compatta per guadagnare spazio. */
    div[class*="st-key-catalog_card_"] [data-testid="stImage"] {
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        min-height: 125px !important;
        max-height: 125px !important;
        overflow: hidden !important;
        margin-bottom: 0.35rem !important;
    }

    div[class*="st-key-catalog_card_"] [data-testid="stImage"] img {
        width: 100% !important;
        height: 125px !important;
        max-height: 125px !important;
        object-fit: contain !important;
    }

    .catalog-image-placeholder {
        height: 125px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: var(--surface-soft);
        border: 1px dashed var(--border-strong);
        border-radius: var(--radius-small);
        color: var(--text-light);
        font-size: 0.80rem;
        margin-bottom: 0.35rem;
    }


    .catalog-product-category {
        min-height: 24px;
        margin-bottom: 0.42rem;
        color: var(--text-secondary);
        font-size: 0.78rem;
        font-weight: 700;
        line-height: 1.2;
        letter-spacing: 0.035em;
        text-transform: uppercase;
    }

    div[class*="st-key-catalog_card_"] h3 {
        min-height: 2.55rem !important;
        display: flex !important;
        align-items: flex-start !important;
        font-size: 1.02rem !important;
        line-height: 1.25 !important;
        margin-top: 0.42rem !important;
        margin-bottom: 0.42rem !important;
    }

    div[class*="st-key-catalog_card_"] [data-testid="stExpander"] {
        margin-top: 0.55rem !important;
    }

    div[class*="st-key-catalog_card_"] h3 {
        font-size: 1.08rem !important;
        line-height: 1.22 !important;
        margin-top: 0.18rem !important;
        margin-bottom: 0.20rem !important;
    }

    div[class*="st-key-catalog_card_"]
    [data-testid="stCaptionContainer"] p {
        font-size: 0.77rem !important;
        margin-bottom: 0.30rem !important;
    }

    div[class*="st-key-catalog_card_"]
    [data-testid="stMarkdownContainer"] p {
        font-size: 0.84rem !important;
        line-height: 1.30 !important;
        margin-bottom: 0.30rem !important;
    }

    /* Upload più compatto, colori ereditati da Sector. */
    div[class*="st-key-catalog_form_panel_"]
    [data-testid="stFileUploaderDropzone"] {
        min-height: 88px !important;
        padding-top: 0.55rem !important;
        padding-bottom: 0.55rem !important;
    }

    /* Salva prodotto: stessa grafica di "Salva allenamento" in Sector. */
    div[class*="st-key-save_product_"] button {
        min-width: 190px !important;
        height: 48px !important;
        background: #00a7e1 !important;
        border: 1px solid #00a7e1 !important;
        border-radius: 5px !important;
        box-shadow: none !important;
        font-weight: 600 !important;
        transition:
            background-color 0.15s ease,
            border-color 0.15s ease !important;
    }

    div[class*="st-key-save_product_"] button p {
        color: #ffffff !important;
        font-weight: 600 !important;
    }

    div[class*="st-key-save_product_"] button:hover {
        background: #0095c9 !important;
        border-color: #0095c9 !important;
    }

    div[class*="st-key-save_product_"] button:hover p {
        color: #ffffff !important;
    }

    /* Elimina prodotto: stessa grafica di "Elimina allenamento" in Sector. */
    div[class*="st-key-delete_product_"] button,
    div[class*="st-key-confirm_delete_product_"] button {
        min-width: 180px !important;
        height: 44px !important;
        background: #ffffff !important;
        border: 1px solid #d9534f !important;
        border-radius: 5px !important;
        box-shadow: none !important;
        font-weight: 600 !important;
    }

    div[class*="st-key-delete_product_"] button p {
        color: #d9534f !important;
        font-weight: 600 !important;
    }

    div[class*="st-key-delete_product_"] button:hover,
    div[class*="st-key-confirm_delete_product_"] button {
        background: #d9534f !important;
        border-color: #d9534f !important;
    }

    div[class*="st-key-delete_product_"] button:hover p,
    div[class*="st-key-confirm_delete_product_"] button p {
        color: #ffffff !important;
        font-weight: 600 !important;
    }

    div[class*="st-key-cancel_delete_product_"] button {
        height: 44px !important;
        border-radius: 5px !important;
    }


    /* Modifica prodotto: azione secondaria chiara e professionale */
    div[class*="st-key-edit_product_"] {
        margin-top: 1.15rem !important;
        margin-bottom: 0.10rem !important;
    }

    div[class*="st-key-edit_product_"] button,
    div[class*="st-key-cancel_edit_product_"] button {
        width: 100% !important;
        min-height: 42px !important;
        border-radius: 5px !important;
        background: #ffffff !important;
        border: 1px solid #00a7e1 !important;
        box-shadow: none !important;
        font-weight: 600 !important;
    }

    div[class*="st-key-edit_product_"] button p,
    div[class*="st-key-cancel_edit_product_"] button p {
        color: #007fa8 !important;
        font-weight: 600 !important;
    }

    div[class*="st-key-edit_product_"] button:hover,
    div[class*="st-key-cancel_edit_product_"] button:hover {
        background: #eef8fc !important;
        border-color: #0095c9 !important;
    }

    /* Conferma eliminazione ordinata: pulsanti pieni, uno sotto l'altro */
    div[class*="st-key-confirm_delete_product_"] button,
    div[class*="st-key-cancel_delete_product_"] button {
        width: 100% !important;
        min-height: 42px !important;
        margin-top: 0.15rem !important;
    }

    div[class*="st-key-confirm_delete_product_"] button {
        background: #d9534f !important;
        border: 1px solid #d9534f !important;
    }

    div[class*="st-key-confirm_delete_product_"] button p {
        color: #ffffff !important;
        font-size: 0.86rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
    }

    div[class*="st-key-cancel_delete_product_"] button {
        background: #ffffff !important;
        border: 1px solid var(--border-strong) !important;
    }

    div[class*="st-key-cancel_delete_product_"] button p {
        color: var(--text-secondary) !important;
        font-size: 0.86rem !important;
        font-weight: 600 !important;
    }

    /* Inserimento prodotto a tendina: pulito e coerente con Sector */
    div[data-testid="stExpander"]:has(div[class*="st-key-catalog_form_panel_"]) {
        margin-bottom: 1.15rem !important;
    }

    div[data-testid="stExpander"]:has(div[class*="st-key-catalog_form_panel_"]) > details {
        background: #ffffff !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-medium) !important;
        box-shadow: var(--shadow-soft) !important;
    }

    .catalog-edit-notice {
        background: #eef8fc;
        border: 1px solid #b9e4f3;
        border-left: 4px solid #00a7e1;
        border-radius: 6px;
        padding: 0.72rem 0.85rem;
        margin-bottom: 0.9rem;
        color: #264653;
        font-size: 0.90rem;
    }

    .catalog-delete-warning {
        background: #fff8e1;
        border: 1px solid #f1df9c;
        border-radius: 6px;
        padding: 0.70rem 0.78rem;
        margin: 0.65rem 0 0.45rem 0;
        color: #5e542c;
        font-size: 0.84rem;
        line-height: 1.35;
    }

    </style>
    """,
    unsafe_allow_html=True
)




st.markdown(
    """
    <style>
    /* ======================================================
       SNOWDATAPRO — ALLINEAMENTO NATIVO AL TEMA SECTOR
       Ultimo livello della cascata: evita che il tema browser
       renda scuri i wrapper interni BaseWeb.
       ====================================================== */

    html,
    body,
    :root,
    [data-testid="stAppViewContainer"],
    [data-testid="stApp"] {
        --primary-color: #00a7e1 !important;
        --background-color: #f4f6f8 !important;
        --secondary-background-color: #eef1f4 !important;
        --text-color: #1f2933 !important;
        color-scheme: light !important;
    }

    /* Wrapper esterni dei widget */
    [data-testid="stTextInput"] [data-baseweb="input"],
    [data-testid="stNumberInput"] [data-baseweb="input"],
    [data-testid="stDateInput"] [data-baseweb="input"],
    [data-testid="stTimeInput"] [data-baseweb="input"],
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
    [data-testid="stTextArea"] textarea {
        background: #eef1f4 !important;
        background-color: #eef1f4 !important;
        color: #1f2933 !important;
        border-color: #c8d0d7 !important;
        box-shadow: none !important;
        color-scheme: light !important;
    }

    /* Gli strati interni devono essere trasparenti, così mostrano
       il grigio chiaro del wrapper invece del fondo scuro del tema. */
    [data-testid="stTextInput"] [data-baseweb="input"] > *,
    [data-testid="stNumberInput"] [data-baseweb="input"] > *,
    [data-testid="stDateInput"] [data-baseweb="input"] > *,
    [data-testid="stTimeInput"] [data-baseweb="input"] > *,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div > *,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div > * {
        background-color: transparent !important;
        background: transparent !important;
    }

    /* Valori digitati e valori selezionati */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stTimeInput"] input,
    [data-testid="stSelectbox"] input,
    [data-testid="stMultiSelect"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] [data-baseweb="select"] span,
    [data-testid="stMultiSelect"] [data-baseweb="select"] span {
        color: #1f2933 !important;
        -webkit-text-fill-color: #1f2933 !important;
        caret-color: #1f2933 !important;
        color-scheme: light !important;
    }

    /* Placeholder */
    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stNumberInput"] input::placeholder,
    [data-testid="stDateInput"] input::placeholder,
    [data-testid="stTimeInput"] input::placeholder,
    [data-testid="stSelectbox"] input::placeholder,
    [data-testid="stMultiSelect"] input::placeholder,
    [data-testid="stTextArea"] textarea::placeholder {
        color: #78848d !important;
        -webkit-text-fill-color: #78848d !important;
        opacity: 1 !important;
    }

    /* Frecce e icone dei controlli */
    [data-testid="stSelectbox"] svg,
    [data-testid="stMultiSelect"] svg,
    [data-testid="stDateInput"] svg,
    [data-testid="stTimeInput"] svg,
    [data-testid="stNumberInput"] svg {
        color: #4d5961 !important;
        fill: #4d5961 !important;
    }

    /* Popup dei select */
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    div[data-baseweb="popover"] ul,
    div[role="listbox"] {
        background: #ffffff !important;
        background-color: #ffffff !important;
        color: #1f2933 !important;
        color-scheme: light !important;
    }

    div[role="option"] {
        background: #ffffff !important;
        background-color: #ffffff !important;
        color: #1f2933 !important;
    }

    div[role="option"] * {
        color: #1f2933 !important;
        -webkit-text-fill-color: #1f2933 !important;
    }

    div[role="option"]:hover,
    div[role="option"][aria-selected="true"] {
        background: #e7edf1 !important;
        background-color: #e7edf1 !important;
    }

    /* Upload foto coerente con Sector */
    [data-testid="stFileUploaderDropzone"] {
        background: #eef1f4 !important;
        background-color: #eef1f4 !important;
        color: #1f2933 !important;
        border-color: #c8d0d7 !important;
        color-scheme: light !important;
    }

    [data-testid="stFileUploaderDropzone"] p,
    [data-testid="stFileUploaderDropzone"] small,
    [data-testid="stFileUploaderDropzone"] span {
        color: #1f2933 !important;
        -webkit-text-fill-color: #1f2933 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)



def mostra_banner_fotografico():
    """Banner panoramico sticky: il contenuto della pagina gli scorre sopra."""
    percorso = os.path.join(BASE_DIR, "banner snowdatapro.jpg")
    if not os.path.exists(percorso):
        return

    with open(percorso, "rb") as file:
        contenuto_base64 = base64.b64encode(file.read()).decode()

    banner_html = (
        '<div class="sector-sticky-banner" '
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



def _numero_opzionale(valore):
    valore = str(valore or "").strip().replace(",", ".")
    if not valore:
        return None
    return float(valore)


def _testo_range(minimo, massimo, unita="°C"):
    if pd.isna(minimo) and pd.isna(massimo):
        return "—"
    if pd.isna(minimo):
        return f"≤ {massimo:g} {unita}"
    if pd.isna(massimo):
        return f"≥ {minimo:g} {unita}"
    return f"{minimo:g} / {massimo:g} {unita}"


SNOW_ICON_NEW_SVG = """
<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"
     style="display:inline-block;vertical-align:-4px;color:#395b68;margin-right:6px;">
  <g fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2v20M3.34 7l17.32 10M3.34 17l17.32-10"/>
    <path d="M12 4.6l-2-1.3M12 4.6l2-1.3M12 19.4l-2 1.3M12 19.4l2 1.3"/>
    <path d="M5.6 8.3l-.2-2.4M5.6 8.3L3.4 9.4M18.4 15.7l.2 2.4M18.4 15.7l2.2-1.1"/>
    <path d="M5.6 15.7l-2.2-1.1M5.6 15.7l-.2 2.4M18.4 8.3l2.2 1.1M18.4 8.3l.2-2.4"/>
  </g>
</svg>
"""

SNOW_ICON_TRANSFORMED_SVG = """
<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"
     style="display:inline-block;vertical-align:-4px;color:#395b68;margin-right:6px;">
  <g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2.7l6.3 3.65v7.3L12 17.3l-6.3-3.65v-7.3Z"/>
    <path d="M12 5.35l4 2.3v4.7l-4 2.3-4-2.3v-4.7Z"/>
    <path d="M12 5.35V2.7M18.3 6.35l2.25-1.3M18.3 13.65l2.25 1.3M12 17.3v2.65M5.7 13.65l-2.25 1.3M5.7 6.35l-2.25-1.3"/>
    <path d="M12 8.4v5.2M9.75 9.7L14.25 12M14.25 9.7L9.75 12"/>
  </g>
</svg>
"""

def _intervallo_duale_summary(temp_nuova_min, temp_nuova_max, temp_trasf_min, temp_trasf_max):
    intervalli = []
    testo_nuova = _testo_range(temp_nuova_min, temp_nuova_max, "°C")
    testo_trasf = _testo_range(temp_trasf_min, temp_trasf_max, "°C")
    if testo_nuova != "—":
        intervalli.append(("❄️", "Neve nuova / cadente", testo_nuova))
    if testo_trasf != "—":
        intervalli.append(("✳️", "Neve trasformata", testo_trasf))
    return intervalli


def _range_overlap(min_prod, max_prod, sel_min, sel_max):
    min_eff = float('-inf') if pd.isna(min_prod) else float(min_prod)
    max_eff = float('inf') if pd.isna(max_prod) else float(max_prod)
    return min_eff <= float(sel_max) and max_eff >= float(sel_min)


MAX_FOTO_PRODOTTO_MB = 5
MIME_FOTO_AMMESSI = {"image/jpeg", "image/png", "image/webp"}


def _prepara_foto_upload(file_caricato):
    if file_caricato is None:
        return "", "", ""

    mime = str(getattr(file_caricato, "type", "") or "").lower()
    nome = str(getattr(file_caricato, "name", "") or "foto_prodotto").strip()
    dati = file_caricato.getvalue()

    if mime not in MIME_FOTO_AMMESSI:
        raise ValueError("Formato foto non supportato. Usa JPG, PNG oppure WEBP.")

    limite = MAX_FOTO_PRODOTTO_MB * 1024 * 1024
    if len(dati) > limite:
        raise ValueError(
            f"La foto è troppo grande. Dimensione massima: {MAX_FOTO_PRODOTTO_MB} MB."
        )

    return base64.b64encode(dati).decode("ascii"), mime, nome


def _mostra_foto_db(foto_data, use_container_width=True, width=None):
    valore = str(foto_data or "").strip()
    if not valore:
        return False
    try:
        dati = base64.b64decode(valore)
        if width is not None:
            st.image(dati, width=width)
        else:
            st.image(dati, use_container_width=use_container_width)
        return True
    except Exception:
        return False


def pagina_catalogo_prodotti(categoria, titolo, sottotitolo, tipi):
    mostra_banner(titolo, sottotitolo)
    usa_condizioni = categoria != "rigatura"
    categoria_tenuta = categoria == "tenuta"

    # --------------------------------------------------------
    # MODALITÀ MODIFICA
    # --------------------------------------------------------
    edit_state_key = f"edit_product_id_{categoria}"
    edit_id = st.session_state.get(edit_state_key)
    prodotto_edit = None

    if edit_id is not None:
        df_edit = leggi_df("""
            SELECT
                id, nome, marca, tipo,
                foto_data, foto_mime, foto_nome,
                temp_min, temp_max, tipo_temperatura, tipo_neve,
                snow_origine, snow_consistenza, snow_umidita,
                snow_forma_grano, snow_granulometria, snow_caratteristiche,
                umidita_min, umidita_max, temp_applicazione,
                tipo_applicazione, temp_nuova_min, temp_nuova_max,
                temp_trasformata_min, temp_trasformata_max,
                descrizione, note
            FROM catalogo_prodotti
            WHERE id = ? AND categoria = ?
            LIMIT 1
        """, (int(edit_id), categoria))

        if not df_edit.empty:
            prodotto_edit = df_edit.iloc[0].to_dict()
        else:
            st.session_state.pop(edit_state_key, None)
            edit_id = None

    modalita_modifica = prodotto_edit is not None
    usa_applicazione = categoria == "scorrimento"
    usa_temp_macchinetta = categoria == "tenuta"

    def _input_numero_da_db(valore):
        if valore is None or pd.isna(valore):
            return ""
        try:
            numero = float(valore)
            if numero.is_integer():
                return str(int(numero))
            return str(numero).rstrip("0").rstrip(".")
        except Exception:
            return str(valore)

    def _indice_opzione(opzioni, valore, fallback=0):
        valore = str(valore or "").strip()
        try:
            return opzioni.index(valore)
        except ValueError:
            return fallback

    snow_option_groups = {
        "Origine": ["Naturale", "Artificiale", "Mista"],
        "Consistenza": [
            "Compatta",
            "Sfarinata / Soffice",
            "Sgranata",
            "Ghiacciata",
            "Soffice su fondo ghiacciato",
            "Soffice su fondo compatto",
        ],
        "Umidità neve": ["Secca", "Umida", "Bagnata", "Molto bagnata"],
        "Forma grano": [
            "Nuova (cristalli esagonali)",
            "In trasformazione (forte gradiente)",
            "In trasformazione (basso gradiente)",
            "Trasformata (cristalli angolari)",
            "Trasformata (grani arrotondati)",
            "Mista nuova e trasformata",
        ],
        "Granulometria": ["Fine", "Media", "Grossa"],
        "Caratteristiche": ["Sporca", "Salata", "Ventata", "Lucida", "Cadente"],
    }

    def _split_multi_values(valore):
        return [voce.strip() for voce in str(valore or "").split(",") if voce.strip()]

    def _default_snow_values(nome_colonna, opzioni, eredita=None):
        eredita = eredita or []
        valori = []
        if modalita_modifica:
            valori_salvati = _split_multi_values(prodotto_edit.get(nome_colonna))
            if "Tutte" in valori_salvati:
                return list(opzioni)
            valori = [voce for voce in valori_salvati if voce in opzioni]
        if not valori:
            if "Tutte" in eredita:
                return list(opzioni)
            valori = [voce for voce in eredita if voce in opzioni]
        return valori

    def _snow_value_compact(nome_gruppo, selezioni):
        opzioni = snow_option_groups.get(nome_gruppo, [])
        valori = [voce for voce in selezioni if voce in opzioni]
        if opzioni and len(valori) == len(opzioni) and set(valori) == set(opzioni):
            return "Tutte"
        return ", ".join(valori)

    def _build_snow_summary(selezioni, tutte_condizioni=False):
        if tutte_condizioni:
            return "Tutte"
        valori = []
        for nome_gruppo in snow_option_groups:
            valori.extend(selezioni.get(nome_gruppo, []))
        visti = set()
        ordinati = []
        for voce in valori:
            if voce not in visti:
                ordinati.append(voce)
                visti.add(voce)
        return ", ".join(ordinati)

    if modalita_modifica:
        nome_exp = str(prodotto_edit.get("nome") or "").strip()
        marca_exp = str(prodotto_edit.get("marca") or "").strip()
        titolo_exp = f"{marca_exp} - {nome_exp}" if marca_exp else nome_exp
        expander_label = f"✏️ Modifica prodotto — {titolo_exp}"
    else:
        expander_label = "➕ Inserimento prodotto"

    app_widget_suffix = edit_id if modalita_modifica else "new"
    app_state_key = f"tipo_applicazione_ui_{categoria}_{app_widget_suffix}"
    expander_keep_key = f"mantieni_expander_app_{categoria}_{app_widget_suffix}"

    if usa_applicazione:
        tipo_app_db = (
            str(prodotto_edit.get("tipo_applicazione") or "").strip()
            if modalita_modifica else ""
        )
        if not tipo_app_db:
            if (
                modalita_modifica
                and prodotto_edit.get("temp_applicazione") is not None
                and not pd.isna(prodotto_edit.get("temp_applicazione"))
            ):
                tipo_app_db = "A caldo"
            else:
                tipo_app_db = "A freddo"

        if app_state_key not in st.session_state:
            st.session_state[app_state_key] = tipo_app_db

    temp_ref_state_key = f"tipo_temperatura_ui_{categoria}_{app_widget_suffix}"
    if categoria_tenuta:
        tipo_temp_db = (
            str(prodotto_edit.get("tipo_temperatura") or "").strip()
            if modalita_modifica else "Aria"
        )
        if tipo_temp_db not in ["Aria", "Neve", "Non specificato"]:
            tipo_temp_db = "Aria"
        if temp_ref_state_key not in st.session_state:
            st.session_state[temp_ref_state_key] = tipo_temp_db

    expander_aperto = modalita_modifica or bool(
        st.session_state.get(expander_keep_key, False)
    )

    with st.expander(expander_label, expanded=expander_aperto):
        if modalita_modifica:
            nome_corrente = str(prodotto_edit.get("nome") or "").strip()
            marca_corrente = str(prodotto_edit.get("marca") or "").strip()
            titolo_corrente = (
                f"{marca_corrente} - {nome_corrente}"
                if marca_corrente
                else nome_corrente
            )
            st.markdown(
                f'<div class="catalog-edit-notice">'
                f'Stai modificando <strong>{titolo_corrente}</strong>. '
                f'Se non carichi una nuova foto, quella attuale verrà mantenuta.'
                f'</div>',
                unsafe_allow_html=True,
            )

        tipo_applicazione = ""
        if usa_applicazione:
            st.markdown("#### Applicazione")

            def _mantieni_aperto_dopo_applicazione():
                st.session_state[expander_keep_key] = True

            tipo_applicazione = st.selectbox(
                "Tipo di applicazione",
                ["A freddo", "A caldo"],
                key=app_state_key,
                on_change=_mantieni_aperto_dopo_applicazione,
                help=(
                    "Con applicazione a caldo puoi indicare anche "
                    "la temperatura consigliata del ferro."
                ),
            )

        tipo_temperatura_dinamica = ""
        if categoria_tenuta:
            def _mantieni_aperto_dopo_tipo_temp():
                st.session_state[expander_keep_key] = True

            st.markdown("#### Impostazione temperatura")
            tipo_temperatura_dinamica = st.selectbox(
                "Temperatura riferita a",
                ["Aria", "Neve", "Non specificato"],
                key=temp_ref_state_key,
                on_change=_mantieni_aperto_dopo_tipo_temp,
                help=(
                    "Con 'Neve' puoi inserire due intervalli distinti: neve nuova/cadente "
                    "e neve trasformata. Con 'Aria' o 'Non specificato' viene usato un solo intervallo."
                ),
            )

        with st.container(key=f"catalog_form_panel_{categoria}"):
            with st.form(
                f"catalogo_{categoria}_form_{edit_id if modalita_modifica else 'new'}",
                clear_on_submit=not modalita_modifica,
            ):
                valore_nome = (
                    str(prodotto_edit.get("nome") or "")
                    if modalita_modifica else ""
                )
                valore_marca = (
                    str(prodotto_edit.get("marca") or "")
                    if modalita_modifica else ""
                )
                valore_tipo = (
                    str(prodotto_edit.get("tipo") or "")
                    if modalita_modifica else ""
                )

                c_nome, c_marca, c_tipo = st.columns(3)
                with c_nome:
                    nome = st.text_input(
                        "Nome prodotto *",
                        value=valore_nome,
                        placeholder="es. UHX Block Middle 26",
                    )
                with c_marca:
                    marca = st.text_input(
                        "Marca",
                        value=valore_marca,
                        placeholder="es. HWK",
                    )
                with c_tipo:
                    tipo = st.selectbox(
                        "Categoria prodotto",
                        tipi,
                        index=_indice_opzione(tipi, valore_tipo, 0),
                    )

                tipo_neve_val = ""
                snow_origine_val = ""
                snow_consistenza_val = ""
                snow_umidita_val = ""
                snow_forma_grano_val = ""
                snow_granulometria_val = ""
                snow_caratteristiche_val = ""
                temp_min_txt = ""
                temp_max_txt = ""
                temp_nuova_min_txt = ""
                temp_nuova_max_txt = ""
                temp_trasformata_min_txt = ""
                temp_trasformata_max_txt = ""
                tipo_temperatura = ""
                umidita_min = None
                umidita_max = None

                if usa_condizioni:
                    st.markdown("#### Condizioni di utilizzo")
                    st.caption("Definisci il campo di utilizzo del prodotto e la classificazione neve di riferimento.")

                    temp_min_default = (
                        _input_numero_da_db(prodotto_edit.get("temp_min"))
                        if modalita_modifica else ""
                    )
                    temp_max_default = (
                        _input_numero_da_db(prodotto_edit.get("temp_max"))
                        if modalita_modifica else ""
                    )
                    tipo_temp_opzioni = ["Aria", "Neve", "Non specificato"]
                    tipo_temp_default = (
                        str(prodotto_edit.get("tipo_temperatura") or "")
                        if modalita_modifica else "Aria"
                    )

                    if categoria_tenuta:
                        tipo_temperatura = tipo_temperatura_dinamica

                        temp_nuova_min_default = (
                            _input_numero_da_db(prodotto_edit.get("temp_nuova_min"))
                            if modalita_modifica else ""
                        )
                        temp_nuova_max_default = (
                            _input_numero_da_db(prodotto_edit.get("temp_nuova_max"))
                            if modalita_modifica else ""
                        )
                        temp_trasformata_min_default = (
                            _input_numero_da_db(prodotto_edit.get("temp_trasformata_min"))
                            if modalita_modifica else ""
                        )
                        temp_trasformata_max_default = (
                            _input_numero_da_db(prodotto_edit.get("temp_trasformata_max"))
                            if modalita_modifica else ""
                        )

                        # Compatibilità con prodotti storici che avevano un solo intervallo.
                        if modalita_modifica and tipo_temperatura == "Neve":
                            if (
                                not temp_nuova_min_default
                                and not temp_nuova_max_default
                                and (temp_min_default or temp_max_default)
                            ):
                                temp_nuova_min_default = temp_min_default
                                temp_nuova_max_default = temp_max_default

                        icona_neve_nuova = SNOW_ICON_NEW_SVG
                        icona_neve_trasformata = SNOW_ICON_TRANSFORMED_SVG

                        if tipo_temperatura == "Neve":
                            c_nuova, c_trasf = st.columns(2)
                            with c_nuova:
                                st.markdown(
                                    f'<div style="display:flex;align-items:center;gap:.45rem;margin:.15rem 0 .55rem 0;">'
                                    f'{icona_neve_nuova}<strong>Intervallo neve nuova / cadente</strong>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                                n1, n2 = st.columns(2)
                                with n1:
                                    temp_nuova_min_txt = st.text_input(
                                        "Min nuova (°C)",
                                        value=temp_nuova_min_default,
                                        placeholder="-10",
                                    )
                                with n2:
                                    temp_nuova_max_txt = st.text_input(
                                        "Max nuova (°C)",
                                        value=temp_nuova_max_default,
                                        placeholder="-2",
                                    )
                            with c_trasf:
                                st.markdown(
                                    f'<div style="display:flex;align-items:center;gap:.45rem;margin:.15rem 0 .55rem 0;">'
                                    f'{icona_neve_trasformata}<strong>Intervallo neve trasformata</strong>'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                                t1, t2 = st.columns(2)
                                with t1:
                                    temp_trasformata_min_txt = st.text_input(
                                        "Min trasformata (°C)",
                                        value=temp_trasformata_min_default,
                                        placeholder="-15",
                                    )
                                with t2:
                                    temp_trasformata_max_txt = st.text_input(
                                        "Max trasformata (°C)",
                                        value=temp_trasformata_max_default,
                                        placeholder="-5",
                                    )
                        else:
                            c_tmin, c_tmax = st.columns(2)
                            with c_tmin:
                                temp_min_txt = st.text_input(
                                    "Temperatura minima (°C)",
                                    value=temp_min_default,
                                    placeholder="-10",
                                )
                            with c_tmax:
                                temp_max_txt = st.text_input(
                                    "Temperatura massima (°C)",
                                    value=temp_max_default,
                                    placeholder="-2",
                                )
                    else:
                        c_tmin, c_tmax, c_ttipo = st.columns(3)
                        with c_tmin:
                            temp_min_txt = st.text_input(
                                "Temperatura minima (°C)",
                                value=temp_min_default,
                                placeholder="-10",
                            )
                        with c_tmax:
                            temp_max_txt = st.text_input(
                                "Temperatura massima (°C)",
                                value=temp_max_default,
                                placeholder="-4",
                            )
                        with c_ttipo:
                            tipo_temperatura = st.selectbox(
                                "Temperatura riferita a",
                                tipo_temp_opzioni,
                                index=_indice_opzione(
                                    tipo_temp_opzioni,
                                    tipo_temp_default,
                                    0,
                                ),
                            )


                    legacy_snow_tags = (
                        _split_multi_values(prodotto_edit.get("tipo_neve"))
                        if modalita_modifica else []
                    )
                    compatibile_tutte_default = (
                        modalita_modifica and "Tutte" in legacy_snow_tags
                    )

                    snow_selection_map = {
                        "Origine": [],
                        "Consistenza": [],
                        "Umidità neve": [],
                        "Forma grano": [],
                        "Granulometria": [],
                        "Caratteristiche": [],
                    }

                    origini_default = _default_snow_values(
                        "snow_origine",
                        snow_option_groups["Origine"],
                        legacy_snow_tags,
                    )
                    consistenza_default = _default_snow_values(
                        "snow_consistenza",
                        snow_option_groups["Consistenza"],
                        legacy_snow_tags,
                    )
                    umidita_neve_default = _default_snow_values(
                        "snow_umidita",
                        snow_option_groups["Umidità neve"],
                        legacy_snow_tags,
                    )
                    forma_grano_default = _default_snow_values(
                        "snow_forma_grano",
                        snow_option_groups["Forma grano"],
                        legacy_snow_tags,
                    )
                    granulometria_default = _default_snow_values(
                        "snow_granulometria",
                        snow_option_groups["Granulometria"],
                        legacy_snow_tags,
                    )
                    caratteristiche_default = _default_snow_values(
                        "snow_caratteristiche",
                        snow_option_groups["Caratteristiche"],
                        legacy_snow_tags,
                    )

                    st.markdown("#### Classificazione neve target")
                    st.markdown(
                        '<div class="snow-classification-card">'
                        '<div class="snow-classification-title">Parametri indipendenti</div>'
                        '<div class="snow-classification-caption">'
                        'Seleziona le qualità della neve per cui il prodotto risulta più adatto. '
                        'I parametri sono indipendenti e seguono la stessa logica della pagina '
                        '"Tipologie di neve".'
                        '</div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )

                    compatibile_tutte_condizioni = st.checkbox(
                        "Compatibile con tutte le condizioni di neve",
                        value=compatibile_tutte_default,
                        help="Utile per basi o prodotti molto trasversali.",
                    )

                    c_snow_1, c_snow_2, c_snow_3 = st.columns(3)
                    with c_snow_1:
                        snow_selection_map["Origine"] = st.multiselect(
                            "Origine",
                            snow_option_groups["Origine"],
                            default=origini_default,
                            placeholder="Seleziona origine",
                            disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_2:
                        snow_selection_map["Consistenza"] = st.multiselect(
                            "Consistenza",
                            snow_option_groups["Consistenza"],
                            default=consistenza_default,
                            placeholder="Seleziona consistenza",
                            disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_3:
                        snow_selection_map["Umidità neve"] = st.multiselect(
                            "Umidità neve",
                            snow_option_groups["Umidità neve"],
                            default=umidita_neve_default,
                            placeholder="Seleziona umidità neve",
                            disabled=compatibile_tutte_condizioni,
                        )

                    c_snow_4, c_snow_5, c_snow_6 = st.columns(3)
                    with c_snow_4:
                        snow_selection_map["Forma grano"] = st.multiselect(
                            "Forma grano",
                            snow_option_groups["Forma grano"],
                            default=forma_grano_default,
                            placeholder="Seleziona forma grano",
                            disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_5:
                        snow_selection_map["Granulometria"] = st.multiselect(
                            "Granulometria",
                            snow_option_groups["Granulometria"],
                            default=granulometria_default,
                            placeholder="Seleziona granulometria",
                            disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_6:
                        snow_selection_map["Caratteristiche"] = st.multiselect(
                            "Caratteristiche",
                            snow_option_groups["Caratteristiche"],
                            default=caratteristiche_default,
                            placeholder="Seleziona caratteristiche",
                            disabled=compatibile_tutte_condizioni,
                        )

                    snow_origine_val = _snow_value_compact(
                        "Origine", snow_selection_map["Origine"]
                    )
                    snow_consistenza_val = _snow_value_compact(
                        "Consistenza", snow_selection_map["Consistenza"]
                    )
                    snow_umidita_val = _snow_value_compact(
                        "Umidità neve", snow_selection_map["Umidità neve"]
                    )
                    snow_forma_grano_val = _snow_value_compact(
                        "Forma grano", snow_selection_map["Forma grano"]
                    )
                    snow_granulometria_val = _snow_value_compact(
                        "Granulometria", snow_selection_map["Granulometria"]
                    )
                    snow_caratteristiche_val = _snow_value_compact(
                        "Caratteristiche", snow_selection_map["Caratteristiche"]
                    )
                    tipo_neve_val = _build_snow_summary(
                        snow_selection_map,
                        tutte_condizioni=compatibile_tutte_condizioni,
                    )

                st.markdown("#### Note")

                c_foto, c_descr = st.columns([1, 2.25])

                with c_foto:
                    foto_attuale = (
                        str(prodotto_edit.get("foto_data") or "").strip()
                        if modalita_modifica else ""
                    )
                    if modalita_modifica and foto_attuale:
                        st.caption("Foto attuale")
                        _mostra_foto_db(
                            foto_attuale,
                            use_container_width=False,
                            width=105,
                        )

                    foto_upload = st.file_uploader(
                        "Nuova foto" if modalita_modifica else "Foto prodotto",
                        type=["jpg", "jpeg", "png", "webp"],
                        key=(
                            f"upload_foto_edit_{categoria}_{edit_id}"
                            if modalita_modifica
                            else f"upload_foto_nuovo_{categoria}"
                        ),
                        help=(
                            "JPG, PNG o WEBP. "
                            + (
                                "Se non scegli una nuova foto, quella attuale resta invariata. "
                                if modalita_modifica else ""
                            )
                            + f"Massimo {MAX_FOTO_PRODOTTO_MB} MB."
                        ),
                    )
                    if foto_upload is not None:
                        st.caption("Nuova foto")
                        st.image(foto_upload, width=105)

                with c_descr:
                    descrizione = st.text_area(
                        "Descrizione tecnica",
                        value=(
                            str(prodotto_edit.get("descrizione") or "")
                            if modalita_modifica else ""
                        ),
                        placeholder="Caratteristiche e indicazioni principali...",
                        height=108,
                    )

                temp_applicazione_txt = ""

                if usa_applicazione and tipo_applicazione == "A caldo":
                    c_tapp, c_note = st.columns([1, 2.25])

                    with c_tapp:
                        temp_applicazione_default = (
                            _input_numero_da_db(
                                prodotto_edit.get("temp_applicazione")
                            )
                            if modalita_modifica else ""
                        )
                        temp_applicazione_txt = st.text_input(
                            "Temperatura ferro (°C)",
                            value=temp_applicazione_default,
                            placeholder="es. 150",
                            help=(
                                "Temperatura consigliata del ferro "
                                "per l'applicazione a caldo."
                            ),
                        )

                    with c_note:
                        note = st.text_area(
                            "Note personali",
                            value=(
                                str(prodotto_edit.get("note") or "")
                                if modalita_modifica else ""
                            ),
                            placeholder="Osservazioni interne...",
                            height=92,
                        )
                elif usa_temp_macchinetta:
                    c_tapp, c_note = st.columns([1, 2.25])

                    with c_tapp:
                        temp_applicazione_default = (
                            _input_numero_da_db(
                                prodotto_edit.get("temp_applicazione")
                            )
                            if modalita_modifica else ""
                        )
                        temp_applicazione_txt = st.text_input(
                            "Temperatura macchinetta (°C)",
                            value=temp_applicazione_default,
                            placeholder="es. 110",
                            help=(
                                "Campo opzionale. Indica la temperatura della "
                                "macchinetta quando prevista per l'applicazione."
                            ),
                        )

                    with c_note:
                        note = st.text_area(
                            "Note personali",
                            value=(
                                str(prodotto_edit.get("note") or "")
                                if modalita_modifica else ""
                            ),
                            placeholder="Osservazioni interne...",
                            height=92,
                        )
                else:
                    note = st.text_area(
                        "Note personali",
                        value=(
                            str(prodotto_edit.get("note") or "")
                            if modalita_modifica else ""
                        ),
                        placeholder="Osservazioni interne...",
                        height=92,
                    )

                if modalita_modifica:
                    c_submit, c_cancel = st.columns([2.2, 1])
                    with c_submit:
                        submit = st.form_submit_button(
                            "Modifica prodotto",
                            type="primary",
                            use_container_width=True,
                        )
                    with c_cancel:
                        annulla_modifica = st.form_submit_button(
                            "Annulla modifica",
                            use_container_width=True,
                        )
                else:
                    submit = st.form_submit_button(
                        "Salva prodotto",
                        type="primary",
                        use_container_width=True,
                    )
                    annulla_modifica = False

                if annulla_modifica:
                    st.session_state.pop(edit_state_key, None)
                    if categoria_tenuta:
                        st.session_state.pop(temp_ref_state_key, None)
                    st.rerun()

                if submit:
                    errori = []

                    if not nome.strip():
                        errori.append("Inserisci il nome del prodotto.")

                    temp_nuova_min = None
                    temp_nuova_max = None
                    temp_trasformata_min = None
                    temp_trasformata_max = None

                    try:
                        if categoria_tenuta and tipo_temperatura == "Neve":
                            temp_nuova_min = _numero_opzionale(temp_nuova_min_txt)
                            temp_nuova_max = _numero_opzionale(temp_nuova_max_txt)
                            temp_trasformata_min = _numero_opzionale(temp_trasformata_min_txt)
                            temp_trasformata_max = _numero_opzionale(temp_trasformata_max_txt)

                            estremi_min = [
                                v for v in [temp_nuova_min, temp_trasformata_min] if v is not None
                            ]
                            estremi_max = [
                                v for v in [temp_nuova_max, temp_trasformata_max] if v is not None
                            ]
                            temp_min = min(estremi_min) if estremi_min else None
                            temp_max = max(estremi_max) if estremi_max else None
                        else:
                            temp_min = _numero_opzionale(temp_min_txt)
                            temp_max = _numero_opzionale(temp_max_txt)

                        temp_applicazione = (
                            _numero_opzionale(temp_applicazione_txt)
                            if (
                                (usa_applicazione and tipo_applicazione == "A caldo")
                                or usa_temp_macchinetta
                            )
                            else None
                        )
                    except ValueError:
                        temp_min = temp_max = None
                        temp_nuova_min = temp_nuova_max = None
                        temp_trasformata_min = temp_trasformata_max = None
                        temp_applicazione = None
                        errori.append(
                            "Le temperature devono essere numeri "
                            "(es. -8, -2, 150)."
                        )

                    # I vecchi campi di umidità percentuale non vengono più usati.
                    umidita_min = None
                    umidita_max = None

                    if categoria_tenuta and tipo_temperatura == "Neve":
                        if (
                            temp_nuova_min is not None
                            and temp_nuova_max is not None
                            and temp_nuova_min > temp_nuova_max
                        ):
                            errori.append(
                                "Nell'intervallo neve nuova la temperatura minima non può essere superiore alla massima."
                            )
                        if (
                            temp_trasformata_min is not None
                            and temp_trasformata_max is not None
                            and temp_trasformata_min > temp_trasformata_max
                        ):
                            errori.append(
                                "Nell'intervallo neve trasformata la temperatura minima non può essere superiore alla massima."
                            )
                    elif (
                        temp_min is not None
                        and temp_max is not None
                        and temp_min > temp_max
                    ):
                        errori.append(
                            "La temperatura minima non può essere superiore alla massima."
                        )

                    if modalita_modifica:
                        foto_data = str(prodotto_edit.get("foto_data") or "")
                        foto_mime = str(prodotto_edit.get("foto_mime") or "")
                        foto_nome = str(prodotto_edit.get("foto_nome") or "")
                    else:
                        foto_data = foto_mime = foto_nome = ""

                    if foto_upload is not None:
                        try:
                            foto_data, foto_mime, foto_nome = _prepara_foto_upload(
                                foto_upload
                            )
                        except ValueError as exc:
                            errori.append(str(exc))

                    if errori:
                        for errore in errori:
                            st.error(errore)
                    else:
                        if modalita_modifica:
                            esegui("""
                                UPDATE catalogo_prodotti
                                SET
                                    nome = ?,
                                    marca = ?,
                                    tipo = ?,
                                    descrizione = ?,
                                    note = ?,
                                    foto_data = ?,
                                    foto_mime = ?,
                                    foto_nome = ?,
                                    temp_min = ?,
                                    temp_max = ?,
                                    tipo_temperatura = ?,
                                    tipo_neve = ?,
                                    snow_origine = ?,
                                    snow_consistenza = ?,
                                    snow_umidita = ?,
                                    snow_forma_grano = ?,
                                    snow_granulometria = ?,
                                    snow_caratteristiche = ?,
                                    umidita_min = ?,
                                    umidita_max = ?,
                                    temp_applicazione = ?,
                                    tipo_applicazione = ?,
                                    temp_nuova_min = ?,
                                    temp_nuova_max = ?,
                                    temp_trasformata_min = ?,
                                    temp_trasformata_max = ?
                                WHERE id = ? AND categoria = ?
                            """, (
                                nome.strip(),
                                marca.strip(),
                                tipo,
                                descrizione.strip(),
                                note.strip(),
                                foto_data,
                                foto_mime,
                                foto_nome,
                                temp_min,
                                temp_max,
                                tipo_temperatura if usa_condizioni else "",
                                tipo_neve_val if usa_condizioni else "",
                                snow_origine_val if usa_condizioni else "",
                                snow_consistenza_val if usa_condizioni else "",
                                snow_umidita_val if usa_condizioni else "",
                                snow_forma_grano_val if usa_condizioni else "",
                                snow_granulometria_val if usa_condizioni else "",
                                snow_caratteristiche_val if usa_condizioni else "",
                                umidita_min,
                                umidita_max,
                                temp_applicazione if (usa_applicazione or usa_temp_macchinetta) else None,
                                tipo_applicazione if usa_applicazione else "",
                                temp_nuova_min if categoria_tenuta else None,
                                temp_nuova_max if categoria_tenuta else None,
                                temp_trasformata_min if categoria_tenuta else None,
                                temp_trasformata_max if categoria_tenuta else None,
                                int(edit_id),
                                categoria,
                            ))
                            st.session_state.pop(edit_state_key, None)
                            st.session_state.pop(expander_keep_key, None)
                            if categoria_tenuta:
                                st.session_state.pop(temp_ref_state_key, None)
                            st.success("Prodotto modificato.")
                            st.rerun()

                        else:
                            esegui("""
                                INSERT INTO catalogo_prodotti (
                                    categoria, nome, marca, tipo,
                                    descrizione, note, creato_il,
                                    foto_data, foto_mime, foto_nome,
                                    temp_min, temp_max,
                                    tipo_temperatura, tipo_neve,
                                    snow_origine, snow_consistenza,
                                    snow_umidita, snow_forma_grano,
                                    snow_granulometria, snow_caratteristiche,
                                    umidita_min, umidita_max,
                                    temp_applicazione, tipo_applicazione,
                                    temp_nuova_min, temp_nuova_max,
                                    temp_trasformata_min, temp_trasformata_max
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                categoria,
                                nome.strip(),
                                marca.strip(),
                                tipo,
                                descrizione.strip(),
                                note.strip(),
                                datetime.now().isoformat(timespec="seconds"),
                                foto_data,
                                foto_mime,
                                foto_nome,
                                temp_min,
                                temp_max,
                                tipo_temperatura if usa_condizioni else "",
                                tipo_neve_val if usa_condizioni else "",
                                snow_origine_val if usa_condizioni else "",
                                snow_consistenza_val if usa_condizioni else "",
                                snow_umidita_val if usa_condizioni else "",
                                snow_forma_grano_val if usa_condizioni else "",
                                snow_granulometria_val if usa_condizioni else "",
                                snow_caratteristiche_val if usa_condizioni else "",
                                umidita_min,
                                umidita_max,
                                temp_applicazione if (usa_applicazione or usa_temp_macchinetta) else None,
                                tipo_applicazione if usa_applicazione else "",
                                temp_nuova_min if categoria_tenuta else None,
                                temp_nuova_max if categoria_tenuta else None,
                                temp_trasformata_min if categoria_tenuta else None,
                                temp_trasformata_max if categoria_tenuta else None,
                            ))
                            st.session_state.pop(expander_keep_key, None)
                            if categoria_tenuta:
                                st.session_state.pop(temp_ref_state_key, None)
                            st.success("Prodotto salvato.")
                            st.rerun()

    st.markdown("### Catalogo prodotti")

    df = leggi_df("""
        SELECT
            id, nome, marca, tipo,
            foto_data, foto_mime, foto_nome,
            temp_min, temp_max, tipo_temperatura, tipo_neve,
            snow_origine, snow_consistenza, snow_umidita,
            snow_forma_grano, snow_granulometria, snow_caratteristiche,
            umidita_min, umidita_max, temp_applicazione,
            tipo_applicazione, temp_nuova_min, temp_nuova_max,
            temp_trasformata_min, temp_trasformata_max,
            descrizione, note
        FROM catalogo_prodotti
        WHERE categoria = ?
        ORDER BY marca COLLATE NOCASE, nome COLLATE NOCASE
    """, (categoria,))

    if df.empty:
        st.info("Nessun prodotto ancora inserito in questo catalogo.")
        return

    with st.container(key=f"catalog_filter_panel_{categoria}"):
        # -----------------------------------------------------
        # Intestazione filtri + reset
        # -----------------------------------------------------
        h1, h2 = st.columns([4.2, 1], vertical_alignment="center")
        with h1:
            st.markdown(
                '<div class="catalog-filter-title">Filtri catalogo</div>'
                '<div class="catalog-filter-subtitle">'
                'Affina rapidamente i prodotti visualizzati.'
                '</div>',
                unsafe_allow_html=True,
            )

        with h2:
            if st.button(
                "↺ Azzera filtri",
                key=f"filter_reset_{categoria}",
                use_container_width=True,
            ):
                chiavi_filtri = [
                    f"cerca_catalogo_{categoria}",
                    f"filtro_marca_{categoria}",
                    f"filtro_tipo_{categoria}",
                    f"usa_temp_aria_{categoria}",
                    f"temp_aria_range_catalogo_{categoria}",
                    f"usa_temp_neve_{categoria}",
                    f"temp_neve_range_catalogo_{categoria}",
                    f"usa_temp_nuova_{categoria}",
                    f"temp_nuova_range_catalogo_{categoria}",
                    f"usa_temp_trasformata_{categoria}",
                    f"temp_trasformata_range_catalogo_{categoria}",
                    f"filtro_neve_{categoria}",
                ]
                for chiave in chiavi_filtri:
                    st.session_state.pop(chiave, None)
                st.rerun()

        st.markdown(
            '<div style="height:0.45rem;"></div>',
            unsafe_allow_html=True,
        )

        # -----------------------------------------------------
        # Ricerca / marca / categoria
        # -----------------------------------------------------
        f1, f2, f3 = st.columns([2.05, 1.05, 1.05])
        with f1:
            cerca = st.text_input(
                "Cerca",
                key=f"cerca_catalogo_{categoria}",
                placeholder="Nome, marca o descrizione...",
            )

        with f2:
            marche = ["Tutte"] + sorted(
                [
                    x
                    for x in df["marca"].dropna().astype(str).unique()
                    if x.strip()
                ],
                key=str.lower,
            )
            filtro_marca = st.selectbox(
                "Marca",
                marche,
                key=f"filtro_marca_{categoria}",
            )

        with f3:
            tipi_presenti = ["Tutti"] + sorted(
                [
                    x
                    for x in df["tipo"].dropna().astype(str).unique()
                    if x.strip()
                ],
                key=str.lower,
            )
            filtro_tipo = st.selectbox(
                "Categoria",
                tipi_presenti,
                key=f"filtro_tipo_{categoria}",
            )

        filtro_temp_aria_attivo = False
        filtro_temp_aria_range = None
        filtro_temp_neve_attivo = False
        filtro_temp_neve_range = None
        filtro_temp_nuova_attivo = False
        filtro_temp_nuova_range = None
        filtro_temp_trasformata_attivo = False
        filtro_temp_trasformata_range = None
        filtro_neve = []

        # -----------------------------------------------------
        # Condizioni di utilizzo
        # -----------------------------------------------------
        if usa_condizioni:
            tipo_temp_norm = (
                df["tipo_temperatura"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
            )

            def _limiti_temperatura_per_riferimento(riferimento):
                mask = tipo_temp_norm == riferimento.lower()
                temp_min_ref = pd.to_numeric(
                    df.loc[mask, "temp_min"], errors="coerce"
                )
                temp_max_ref = pd.to_numeric(
                    df.loc[mask, "temp_max"], errors="coerce"
                )
                valori = pd.concat([temp_min_ref, temp_max_ref]).dropna()

                if not valori.empty:
                    minimo = math.floor(float(valori.min()) * 2) / 2
                    massimo = math.ceil(float(valori.max()) * 2) / 2
                else:
                    minimo, massimo = -25.0, 20.0

                if minimo == massimo:
                    minimo -= 0.5
                    massimo += 0.5

                return float(minimo), float(massimo)

            def _limiti_temperatura_colonne(col_min, col_max):
                min_vals = pd.to_numeric(df[col_min], errors="coerce")
                max_vals = pd.to_numeric(df[col_max], errors="coerce")
                valori = pd.concat([min_vals, max_vals]).dropna()
                if not valori.empty:
                    minimo = math.floor(float(valori.min()) * 2) / 2
                    massimo = math.ceil(float(valori.max()) * 2) / 2
                else:
                    minimo, massimo = -25.0, 20.0
                if minimo == massimo:
                    minimo -= 0.5
                    massimo += 0.5
                return float(minimo), float(massimo)

            neve_presenti = set()
            for valore in df["tipo_neve"].fillna("").astype(str):
                for voce in valore.split(","):
                    voce = voce.strip()
                    if voce and voce != "Tutte":
                        neve_presenti.add(voce)

            st.markdown(
                '<div style="height:0.28rem;"></div>',
                unsafe_allow_html=True,
            )

            st.markdown(
                '<div class="catalog-filter-section-title">'
                'Temperature di utilizzo'
                '</div>',
                unsafe_allow_html=True,
            )

            if categoria_tenuta:
                aria_min, aria_max = _limiti_temperatura_per_riferimento("aria")
                nuova_min, nuova_max = _limiti_temperatura_colonne(
                    "temp_nuova_min", "temp_nuova_max"
                )
                trasf_min, trasf_max = _limiti_temperatura_colonne(
                    "temp_trasformata_min", "temp_trasformata_max"
                )

                c_aria_f, c_nuova_f, c_trasf_f = st.columns(3)

                with c_aria_f:
                    with st.container(key=f"filter_temp_aria_group_{categoria}"):
                        st.markdown(
                            '<div class="catalog-temperature-card-title">'
                            'Temperatura aria'
                            '</div>'
                            '<div class="catalog-temperature-card-subtitle">'
                            'Per prodotti con intervallo riferito all’aria.'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        filtro_temp_aria_attivo = st.toggle(
                            "Attiva filtro aria",
                            key=f"usa_temp_aria_{categoria}",
                        )
                        filtro_temp_aria_range = st.slider(
                            "Intervallo aria (°C)",
                            min_value=aria_min,
                            max_value=aria_max,
                            value=(aria_min, aria_max),
                            step=0.5,
                            disabled=not filtro_temp_aria_attivo,
                            key=f"temp_aria_range_catalogo_{categoria}",
                        )

                with c_nuova_f:
                    with st.container(key=f"filter_temp_nuova_group_{categoria}"):
                        st.markdown(
                            f'<div class="catalog-temperature-card-title">'
                            f'{SNOW_ICON_NEW_SVG}Neve nuova / cadente'
                            f'</div>'
                            '<div class="catalog-temperature-card-subtitle">'
                            'Per prodotti con temperatura riferita alla neve.'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        filtro_temp_nuova_attivo = st.toggle(
                            "Attiva filtro neve nuova",
                            key=f"usa_temp_nuova_{categoria}",
                        )
                        filtro_temp_nuova_range = st.slider(
                            "Intervallo neve nuova (°C)",
                            min_value=nuova_min,
                            max_value=nuova_max,
                            value=(nuova_min, nuova_max),
                            step=0.5,
                            disabled=not filtro_temp_nuova_attivo,
                            key=f"temp_nuova_range_catalogo_{categoria}",
                        )

                with c_trasf_f:
                    with st.container(key=f"filter_temp_trasformata_group_{categoria}"):
                        st.markdown(
                            f'<div class="catalog-temperature-card-title">'
                            f'{SNOW_ICON_TRANSFORMED_SVG}Neve trasformata'
                            f'</div>'
                            '<div class="catalog-temperature-card-subtitle">'
                            'Per prodotti con temperatura riferita alla neve.'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        filtro_temp_trasformata_attivo = st.toggle(
                            "Attiva filtro neve trasformata",
                            key=f"usa_temp_trasformata_{categoria}",
                        )
                        filtro_temp_trasformata_range = st.slider(
                            "Intervallo neve trasformata (°C)",
                            min_value=trasf_min,
                            max_value=trasf_max,
                            value=(trasf_min, trasf_max),
                            step=0.5,
                            disabled=not filtro_temp_trasformata_attivo,
                            key=f"temp_trasformata_range_catalogo_{categoria}",
                        )
            else:
                aria_min, aria_max = _limiti_temperatura_per_riferimento("aria")
                neve_min, neve_max = _limiti_temperatura_per_riferimento("neve")

                c_aria, c_neve_temp = st.columns(2)

                with c_aria:
                    with st.container(key=f"filter_temp_aria_group_{categoria}"):
                        st.markdown(
                            '<div class="catalog-temperature-card-title">'
                            'Temperatura aria'
                            '</div>'
                            '<div class="catalog-temperature-card-subtitle">'
                            'Filtra i prodotti con temperatura dichiarata rispetto all’aria.'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        filtro_temp_aria_attivo = st.toggle(
                            "Attiva filtro aria",
                            key=f"usa_temp_aria_{categoria}",
                        )
                        filtro_temp_aria_range = st.slider(
                            "Intervallo aria (°C)",
                            min_value=aria_min,
                            max_value=aria_max,
                            value=(aria_min, aria_max),
                            step=0.5,
                            disabled=not filtro_temp_aria_attivo,
                            key=f"temp_aria_range_catalogo_{categoria}",
                        )

                with c_neve_temp:
                    with st.container(key=f"filter_temp_neve_group_{categoria}"):
                        st.markdown(
                            '<div class="catalog-temperature-card-title">'
                            'Temperatura neve'
                            '</div>'
                            '<div class="catalog-temperature-card-subtitle">'
                            'Filtra i prodotti con temperatura dichiarata rispetto alla neve.'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        filtro_temp_neve_attivo = st.toggle(
                            "Attiva filtro neve",
                            key=f"usa_temp_neve_{categoria}",
                        )
                        filtro_temp_neve_range = st.slider(
                            "Intervallo neve (°C)",
                            min_value=neve_min,
                            max_value=neve_max,
                            value=(neve_min, neve_max),
                            step=0.5,
                            disabled=not filtro_temp_neve_attivo,
                            key=f"temp_neve_range_catalogo_{categoria}",
                        )

            st.markdown(
                '<div style="height:0.35rem;"></div>',
                unsafe_allow_html=True,
            )

            with st.container(key=f"filter_snow_group_{categoria}"):
                st.markdown(
                    '<div class="catalog-filter-section-title">'
                    'Classificazione neve'
                    '</div>',
                    unsafe_allow_html=True,
                )

                filtro_neve = st.multiselect(
                    "Seleziona una o più caratteristiche",
                    sorted(neve_presenti, key=str.lower),
                    placeholder="Tutte le caratteristiche",
                    key=f"filtro_neve_{categoria}",
                    help=(
                        "Con più caratteristiche selezionate vengono mostrati "
                        "i prodotti compatibili con almeno una di esse."
                    ),
                )


    filtrato = df.copy()

    if cerca.strip():
        q = cerca.strip().lower()
        colonne_testo = ["nome", "marca", "tipo", "descrizione", "note"]
        maschera = pd.Series(False, index=filtrato.index)
        for col in colonne_testo:
            maschera = (
                maschera
                | filtrato[col]
                .fillna("")
                .astype(str)
                .str.lower()
                .str.contains(q, regex=False)
            )
        filtrato = filtrato[maschera]

    if filtro_marca != "Tutte":
        filtrato = filtrato[filtrato["marca"] == filtro_marca]

    if filtro_tipo != "Tutti":
        filtrato = filtrato[filtrato["tipo"] == filtro_tipo]

    if usa_condizioni:
        if categoria_tenuta and (
            filtro_temp_aria_attivo
            or filtro_temp_nuova_attivo
            or filtro_temp_trasformata_attivo
        ):
            temp_min_prod = pd.to_numeric(filtrato["temp_min"], errors="coerce")
            temp_max_prod = pd.to_numeric(filtrato["temp_max"], errors="coerce")
            temp_nuova_min_prod = pd.to_numeric(
                filtrato["temp_nuova_min"], errors="coerce"
            )
            temp_nuova_max_prod = pd.to_numeric(
                filtrato["temp_nuova_max"], errors="coerce"
            )
            temp_trasf_min_prod = pd.to_numeric(
                filtrato["temp_trasformata_min"], errors="coerce"
            )
            temp_trasf_max_prod = pd.to_numeric(
                filtrato["temp_trasformata_max"], errors="coerce"
            )
            tipo_temp_prod = (
                filtrato["tipo_temperatura"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
            )

            maschera_temperatura = pd.Series(False, index=filtrato.index)

            if filtro_temp_aria_attivo and filtro_temp_aria_range is not None:
                aria_sel_min, aria_sel_max = filtro_temp_aria_range
                mask_aria = (
                    (tipo_temp_prod == "aria")
                    & (temp_min_prod.notna() | temp_max_prod.notna())
                    & (temp_min_prod.fillna(float("-inf")) <= float(aria_sel_max))
                    & (temp_max_prod.fillna(float("inf")) >= float(aria_sel_min))
                )
                maschera_temperatura = maschera_temperatura | mask_aria

            if filtro_temp_nuova_attivo and filtro_temp_nuova_range is not None:
                nuova_sel_min, nuova_sel_max = filtro_temp_nuova_range
                mask_nuova = (
                    (tipo_temp_prod == "neve")
                    & (temp_nuova_min_prod.notna() | temp_nuova_max_prod.notna())
                    & (
                        temp_nuova_min_prod.fillna(float("-inf"))
                        <= float(nuova_sel_max)
                    )
                    & (
                        temp_nuova_max_prod.fillna(float("inf"))
                        >= float(nuova_sel_min)
                    )
                )
                maschera_temperatura = maschera_temperatura | mask_nuova

            if (
                filtro_temp_trasformata_attivo
                and filtro_temp_trasformata_range is not None
            ):
                trasf_sel_min, trasf_sel_max = filtro_temp_trasformata_range
                mask_trasf = (
                    (tipo_temp_prod == "neve")
                    & (temp_trasf_min_prod.notna() | temp_trasf_max_prod.notna())
                    & (
                        temp_trasf_min_prod.fillna(float("-inf"))
                        <= float(trasf_sel_max)
                    )
                    & (
                        temp_trasf_max_prod.fillna(float("inf"))
                        >= float(trasf_sel_min)
                    )
                )
                maschera_temperatura = maschera_temperatura | mask_trasf

            filtrato = filtrato[maschera_temperatura]
        elif (filtro_temp_aria_attivo or filtro_temp_neve_attivo):
            temp_min_prod = pd.to_numeric(filtrato["temp_min"], errors="coerce")
            temp_max_prod = pd.to_numeric(filtrato["temp_max"], errors="coerce")
            tipo_temp_prod = (
                filtrato["tipo_temperatura"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.lower()
            )

            maschera_temperatura = pd.Series(False, index=filtrato.index)

            if filtro_temp_aria_attivo and filtro_temp_aria_range is not None:
                aria_sel_min, aria_sel_max = filtro_temp_aria_range
                aria_min_eff = temp_min_prod.fillna(float("-inf"))
                aria_max_eff = temp_max_prod.fillna(float("inf"))
                maschera_aria = (
                    (tipo_temp_prod == "aria")
                    & (temp_min_prod.notna() | temp_max_prod.notna())
                    & (aria_min_eff <= float(aria_sel_max))
                    & (aria_max_eff >= float(aria_sel_min))
                )
                maschera_temperatura = maschera_temperatura | maschera_aria

            if filtro_temp_neve_attivo and filtro_temp_neve_range is not None:
                neve_sel_min, neve_sel_max = filtro_temp_neve_range
                neve_min_eff = temp_min_prod.fillna(float("-inf"))
                neve_max_eff = temp_max_prod.fillna(float("inf"))
                maschera_neve_temp = (
                    (tipo_temp_prod == "neve")
                    & (temp_min_prod.notna() | temp_max_prod.notna())
                    & (neve_min_eff <= float(neve_sel_max))
                    & (neve_max_eff >= float(neve_sel_min))
                )
                maschera_temperatura = (
                    maschera_temperatura | maschera_neve_temp
                )

            filtrato = filtrato[maschera_temperatura]

    if usa_condizioni and filtro_neve:
        neve_selezionate = set(filtro_neve)

        def _compatibile_neve(valore):
            tipi_prodotto = {
                voce.strip()
                for voce in str(valore or "").split(",")
                if voce.strip()
            }
            if "Tutte" in tipi_prodotto:
                return True
            return bool(tipi_prodotto & neve_selezionate)

        filtrato = filtrato[
            filtrato["tipo_neve"].apply(_compatibile_neve)
        ]

    st.caption(f"{len(filtrato)} prodotti visualizzati su {len(df)}")

    if filtrato.empty:
        st.info("Nessun prodotto corrisponde ai filtri selezionati.")
        return

    righe = filtrato.to_dict("records")

    for start_idx in range(0, len(righe), 3):
        colonne = st.columns(3)

        for col_idx, prodotto in enumerate(righe[start_idx:start_idx + 3]):
            prodotto_id = int(prodotto["id"])

            with colonne[col_idx]:
                with st.container(
                    key=f"catalog_card_{categoria}_{prodotto_id}",
                    border=False,
                ):
                    nome_prodotto = str(
                        prodotto.get("nome") or "Prodotto"
                    ).strip()
                    marca_prodotto = str(
                        prodotto.get("marca") or ""
                    ).strip()
                    tipo_prodotto = str(
                        prodotto.get("tipo") or ""
                    ).strip()

                    if tipo_prodotto:
                        st.markdown(
                            f'<div class="catalog-product-category">'
                            f'{tipo_prodotto}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            '<div class="catalog-product-category">&nbsp;</div>',
                            unsafe_allow_html=True,
                        )

                    foto_data = str(
                        prodotto.get("foto_data") or ""
                    ).strip()

                    if foto_data:
                        _mostra_foto_db(foto_data)
                    else:
                        st.markdown(
                            '<div class="catalog-image-placeholder">'
                            'Nessuna foto'
                            '</div>',
                            unsafe_allow_html=True,
                        )

                    titolo_card = (
                        f"{marca_prodotto} - {nome_prodotto}"
                        if marca_prodotto
                        else nome_prodotto
                    )
                    st.markdown(f"### {titolo_card}")

                    if usa_condizioni:
                        tipo_temp_card = str(
                            prodotto.get("tipo_temperatura") or ""
                        ).strip().lower()
                        if tipo_temp_card == "aria":
                            riferimento_temp = "aria"
                        elif tipo_temp_card == "neve":
                            riferimento_temp = "neve"
                        else:
                            riferimento_temp = "n.d."

                        if categoria_tenuta:
                            if tipo_temp_card == "neve":
                                intervalli_card = _intervallo_duale_summary(
                                    prodotto.get("temp_nuova_min"),
                                    prodotto.get("temp_nuova_max"),
                                    prodotto.get("temp_trasformata_min"),
                                    prodotto.get("temp_trasformata_max"),
                                )
                                if intervalli_card:
                                    for _, etichetta_int, valore_int in intervalli_card:
                                        icona_int = (
                                            SNOW_ICON_NEW_SVG
                                            if "nuova" in etichetta_int.lower()
                                            else SNOW_ICON_TRANSFORMED_SVG
                                        )
                                        st.markdown(
                                            f'<div style="display:flex;align-items:center;gap:.28rem;margin:.18rem 0;">'
                                            f'{icona_int}<span><strong>{html_escape(etichetta_int)}:</strong> {html_escape(valore_int)}</span>'
                                            f'</div>',
                                            unsafe_allow_html=True,
                                        )
                                else:
                                    temp_txt = _testo_range(
                                        prodotto.get("temp_min"),
                                        prodotto.get("temp_max"),
                                        "°C",
                                    )
                                    if temp_txt != "—":
                                        st.markdown(
                                            f"**Temperatura:** {temp_txt} · neve"
                                        )
                            else:
                                temp_txt = _testo_range(
                                    prodotto.get("temp_min"),
                                    prodotto.get("temp_max"),
                                    "°C",
                                )
                                if temp_txt != "—":
                                    st.markdown(
                                        f"**Temperatura:** {temp_txt} · {riferimento_temp}"
                                    )
                        else:
                            temp_txt = _testo_range(
                                prodotto.get("temp_min"),
                                prodotto.get("temp_max"),
                                "°C",
                            )
                            if temp_txt != "—":
                                st.markdown(
                                    f"**Temperatura:** {temp_txt} · {riferimento_temp}"
                                )

                    descrizione_prodotto = str(
                        prodotto.get("descrizione") or ""
                    ).strip()

                    with st.expander("Scheda completa"):
                        if descrizione_prodotto:
                            st.markdown("**Descrizione tecnica**")
                            st.write(descrizione_prodotto)

                        note_prodotto = str(
                            prodotto.get("note") or ""
                        ).strip()
                        if note_prodotto:
                            st.markdown("**Note personali**")
                            st.write(note_prodotto)

                        if usa_condizioni:
                            if usa_applicazione:
                                tipo_app_salvato = str(
                                    prodotto.get("tipo_applicazione") or ""
                                ).strip()
                                temp_applicazione = prodotto.get(
                                    "temp_applicazione"
                                )

                                if (
                                    not tipo_app_salvato
                                    and temp_applicazione is not None
                                    and not pd.isna(temp_applicazione)
                                ):
                                    tipo_app_salvato = "A caldo"

                                if tipo_app_salvato:
                                    testo_applicazione = tipo_app_salvato

                                    if (
                                        tipo_app_salvato == "A caldo"
                                        and temp_applicazione is not None
                                        and not pd.isna(temp_applicazione)
                                    ):
                                        try:
                                            valore_tapp = float(temp_applicazione)
                                            testo_tapp = (
                                                str(int(valore_tapp))
                                                if valore_tapp.is_integer()
                                                else str(valore_tapp).rstrip("0").rstrip(".")
                                            )
                                        except Exception:
                                            testo_tapp = str(temp_applicazione)

                                        testo_applicazione += (
                                            f" · ferro {testo_tapp} °C"
                                        )

                                    st.markdown(
                                        f"**Applicazione:** {testo_applicazione}"
                                    )

                            if usa_temp_macchinetta:
                                temp_macchinetta = prodotto.get("temp_applicazione")
                                if (
                                    temp_macchinetta is not None
                                    and not pd.isna(temp_macchinetta)
                                ):
                                    try:
                                        valore_macchinetta = float(temp_macchinetta)
                                        testo_macchinetta = (
                                            str(int(valore_macchinetta))
                                            if valore_macchinetta.is_integer()
                                            else str(valore_macchinetta).rstrip("0").rstrip(".")
                                        )
                                    except Exception:
                                        testo_macchinetta = str(temp_macchinetta)

                                    st.markdown(
                                        f"**Temperatura macchinetta:** {testo_macchinetta} °C"
                                    )

                            tipo_temp_scheda = str(
                                prodotto.get("tipo_temperatura") or ""
                            ).strip().lower()
                            if tipo_temp_scheda == "aria":
                                riferimento_temp_scheda = "aria"
                            elif tipo_temp_scheda == "neve":
                                riferimento_temp_scheda = "neve"
                            else:
                                riferimento_temp_scheda = "n.d."

                            if categoria_tenuta:
                                if tipo_temp_scheda == "neve":
                                    intervalli_scheda = _intervallo_duale_summary(
                                        prodotto.get("temp_nuova_min"),
                                        prodotto.get("temp_nuova_max"),
                                        prodotto.get("temp_trasformata_min"),
                                        prodotto.get("temp_trasformata_max"),
                                    )
                                    if intervalli_scheda:
                                        st.markdown("**Temperature di utilizzo · neve**")
                                        for _, etichetta_int, valore_int in intervalli_scheda:
                                            icona_int = (
                                                SNOW_ICON_NEW_SVG
                                                if "nuova" in etichetta_int.lower()
                                                else SNOW_ICON_TRANSFORMED_SVG
                                            )
                                            st.markdown(
                                                f'<div style="display:flex;align-items:center;gap:.3rem;margin:.28rem 0;">'
                                                f'{icona_int}<span><strong>{html_escape(etichetta_int)}:</strong> {html_escape(valore_int)}</span>'
                                                f'</div>',
                                                unsafe_allow_html=True,
                                            )
                                    else:
                                        temp_generica = _testo_range(
                                            prodotto.get("temp_min"),
                                            prodotto.get("temp_max"),
                                            "°C",
                                        )
                                        if temp_generica != "—":
                                            st.markdown(
                                                f"**Temperatura:** {temp_generica} · neve"
                                            )
                                else:
                                    temp_generica = _testo_range(
                                        prodotto.get("temp_min"),
                                        prodotto.get("temp_max"),
                                        "°C",
                                    )
                                    if temp_generica != "—":
                                        st.markdown(
                                            f"**Temperatura:** {temp_generica} · {riferimento_temp_scheda}"
                                        )
                            else:
                                temp_generica = _testo_range(
                                    prodotto.get("temp_min"),
                                    prodotto.get("temp_max"),
                                    "°C",
                                )
                                if temp_generica != "—":
                                    st.markdown(
                                        f"**Temperatura:** {temp_generica} · {riferimento_temp_scheda}"
                                    )

                            neve_completa = str(
                                prodotto.get("tipo_neve") or ""
                            ).strip()
                            campi_neve_card = [
                                ("Origine", str(prodotto.get("snow_origine") or "").strip()),
                                ("Consistenza", str(prodotto.get("snow_consistenza") or "").strip()),
                                ("Umidità neve", str(prodotto.get("snow_umidita") or "").strip()),
                                ("Forma grano", str(prodotto.get("snow_forma_grano") or "").strip()),
                                ("Granulometria", str(prodotto.get("snow_granulometria") or "").strip()),
                                ("Caratteristiche", str(prodotto.get("snow_caratteristiche") or "").strip()),
                            ]
                            dettagli_neve_presenti = any(
                                valore for _, valore in campi_neve_card
                            )

                            if dettagli_neve_presenti:
                                elementi_neve_html = []

                                for etichetta_campo, valore_campo in campi_neve_card:
                                    if not valore_campo:
                                        continue

                                    valori_singoli = [
                                        voce.strip()
                                        for voce in valore_campo.split(",")
                                        if voce.strip()
                                    ]

                                    opzioni_complete = snow_option_groups.get(
                                        etichetta_campo, []
                                    )
                                    if (
                                        "Tutte" in valori_singoli
                                        or (
                                            opzioni_complete
                                            and set(valori_singoli) == set(opzioni_complete)
                                        )
                                    ):
                                        valori_singoli = ["Tutte"]

                                    badge_html = "".join(
                                        f'<span class="snow-detail-chip">{html_escape(voce)}</span>'
                                        for voce in valori_singoli
                                    )
                                    elementi_neve_html.append(
                                        f'<div class="snow-detail-item">'
                                        f'<div class="snow-detail-label">{html_escape(etichetta_campo)}</div>'
                                        f'<div class="snow-detail-values">{badge_html}</div>'
                                        f'</div>'
                                    )

                                st.markdown(
                                    '<div class="snow-detail-panel">'
                                    '<div class="snow-detail-heading">'
                                    '<div class="snow-detail-title">Classificazione neve</div>'
                                    '</div>'
                                    '<div class="snow-detail-grid">'
                                    + "".join(elementi_neve_html)
                                    + '</div>'
                                    '</div>',
                                    unsafe_allow_html=True,
                                )
                            elif neve_completa:
                                st.markdown(
                                    f"**Tipi di neve:** {neve_completa}"
                                )

                        # --------------------------------------------
                        # MODIFICA PRODOTTO
                        # --------------------------------------------
                        if st.button(
                            "Modifica prodotto",
                            key=f"edit_product_{categoria}_{prodotto_id}",
                            use_container_width=True,
                        ):
                            st.session_state[edit_state_key] = prodotto_id
                            # Chiude un'eventuale conferma eliminazione aperta
                            st.session_state.pop(
                                f"conferma_elimina_{categoria}_{prodotto_id}",
                                None,
                            )
                            st.rerun()

                        st.markdown(
                            '<div style="height:0.15rem;"></div><hr style="margin:0.20rem 0 1.10rem 0;border:none;border-top:1px solid #d9dfe4;">',
                            unsafe_allow_html=True,
                        )

                        # --------------------------------------------
                        # ELIMINA PRODOTTO
                        # --------------------------------------------
                        conferma_key = (
                            f"conferma_elimina_{categoria}_{prodotto_id}"
                        )

                        if not st.session_state.get(conferma_key, False):
                            if st.button(
                                "Elimina prodotto",
                                key=f"delete_product_{categoria}_{prodotto_id}",
                                use_container_width=True,
                            ):
                                st.session_state[conferma_key] = True
                                st.rerun()

                        else:
                            st.markdown(
                                '<div class="catalog-delete-warning">'
                                '<strong>Eliminare definitivamente il prodotto?</strong><br>'
                                'Questa operazione non può essere annullata.'
                                '</div>',
                                unsafe_allow_html=True,
                            )

                            if st.button(
                                "Conferma eliminazione",
                                key=(
                                    f"confirm_delete_product_"
                                    f"{categoria}_{prodotto_id}"
                                ),
                                use_container_width=True,
                            ):
                                esegui(
                                    "DELETE FROM catalogo_prodotti WHERE id = ?",
                                    (prodotto_id,),
                                )

                                if (
                                    st.session_state.get(edit_state_key)
                                    == prodotto_id
                                ):
                                    st.session_state.pop(edit_state_key, None)

                                st.session_state.pop(conferma_key, None)
                                st.success("Prodotto eliminato.")
                                st.rerun()

                            if st.button(
                                "Annulla",
                                key=(
                                    f"cancel_delete_product_"
                                    f"{categoria}_{prodotto_id}"
                                ),
                                use_container_width=True,
                            ):
                                st.session_state.pop(conferma_key, None)
                                st.rerun()


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
    # Logo più grande, sempre centrato e ben visibile.
    col_logo_sx, col_logo, col_logo_dx = st.sidebar.columns([0.35, 5.3, 0.35])

    with col_logo:
        st.image(
            logo_sidebar_path,
            width=340,
        )

    # Spaziatura simile a Sector tra logo e Dashboard.
    st.sidebar.markdown(
        '<div style="height: 24px;"></div>',
        unsafe_allow_html=True,
    )
else:
    st.sidebar.markdown(
        '<div style="height: 28px;"></div>',
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


if st.sidebar.button(
    "Tipologie di neve",
    icon=":material/ac_unit:",
    key="menu_tipologie_neve",
    use_container_width=True,
    type="primary" if pagina == "Tipologie di neve" else "secondary",
):
    cambia_pagina("Tipologie di neve")


# ============================================================
# PAGINE
# ============================================================

mostra_banner_fotografico()

with st.container(key="sector_page_content"):

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
            "Catalogo di prodotti solidi, basi, polveri, top finish, liquidi tampone e spray.",
            ["Solida", "Base", "Polvere", "Top finish", "Liquido tampone", "Spray"],
        )


    elif pagina == "Scioline di tenuta":
        pagina_catalogo_prodotti(
            "tenuta",
            "Scioline di tenuta",
            "Catalogo di basi, stick e klister con classificazione neve e condizioni di utilizzo.",
            ["Base stick", "Base klister", "Base spray", "Stick", "Klister"],
        )


    elif pagina == "Rigature manuali":
        pagina_catalogo_prodotti(
            "rigatura",
            "Rigature manuali",
            "Catalogo degli utensili e delle configurazioni di rigatura manuale.",
            ["Lineare", "Incrociata", "V", "Rullo", "Utensile", "Altro"],
        )



    elif pagina == "Tipologie di neve":
        mostra_banner(
            "Tipologie di neve",
            "Riferimento per la classificazione standardizzata delle condizioni neve in SnowDataPro.",
        )

        st.markdown("### Parametri fondamentali della neve")
        st.caption(
            "Ogni colonna rappresenta un parametro indipendente: le voci non devono essere lette come combinazioni obbligatorie, "
            "ma come qualità da comporre tra loro per descrivere in modo preciso la neve."
        )

        classificazione_rows = [
            {
                "Origine": "Naturale",
                "Consistenza": "Compatta",
                "Umidità": "Secca",
                "Forma grano": "Nuova (cristalli esagonali)",
                "Granulometria": "Fine",
                "Caratteristiche": "Sporca",
            },
            {
                "Origine": "Artificiale",
                "Consistenza": "Sfarinata / Soffice",
                "Umidità": "Umida",
                "Forma grano": "In trasformazione (forte gradiente)",
                "Granulometria": "Media",
                "Caratteristiche": "Salata",
            },
            {
                "Origine": "Mista",
                "Consistenza": "Sgranata",
                "Umidità": "Bagnata",
                "Forma grano": "In trasformazione (basso gradiente)",
                "Granulometria": "Grossa",
                "Caratteristiche": "Ventata",
            },
            {
                "Origine": "",
                "Consistenza": "Ghiacciata",
                "Umidità": "Molto bagnata",
                "Forma grano": "Trasformata (cristalli angolari)",
                "Granulometria": "",
                "Caratteristiche": "Lucida",
            },
            {
                "Origine": "",
                "Consistenza": "Soffice su fondo ghiacciato",
                "Umidità": "",
                "Forma grano": "Trasformata (grani arrotondati)",
                "Granulometria": "",
                "Caratteristiche": "Cadente",
            },
            {
                "Origine": "",
                "Consistenza": "Soffice su fondo compatto",
                "Umidità": "",
                "Forma grano": "Mista nuova e trasformata",
                "Granulometria": "",
                "Caratteristiche": "",
            },
        ]

        headers = ["Origine", "Consistenza", "Umidità", "Forma grano", "Granulometria", "Caratteristiche"]
        html_rows = []
        for row in classificazione_rows:
            celle = "".join(f"<td>{row.get(col, '')}</td>" for col in headers)
            html_rows.append(f"<tr>{celle}</tr>")
        html_rows_render = "".join(html_rows)

        st.markdown(
            f"""
            <div class="snow-reference-card">
                <div class="snow-reference-header">
                    <div class="snow-reference-grid">
                        <div class="snow-reference-mini">
                            <div class="snow-reference-mini-title">Logica di classificazione</div>
                            <div class="snow-reference-mini-text">Ogni parametro descrive un aspetto diverso della neve: origine, struttura superficiale, presenza di acqua, evoluzione del grano e caratteristiche utili alla scelta del prodotto.</div>
                        </div>
                        <div class="snow-reference-mini">
                            <div class="snow-reference-mini-title">Come usarla nei prodotti</div>
                            <div class="snow-reference-mini-text">Nel catalogo prodotti di scorrimento puoi selezionare i parametri in modo indipendente, senza combinazioni predefinite, così da descrivere in modo più preciso il campo di utilizzo della paraffina.</div>
                        </div>
                        <div class="snow-reference-mini">
                            <div class="snow-reference-mini-title">Lettura corretta</div>
                            <div class="snow-reference-mini-text">Le righe sono solo un riferimento visivo per distribuire le voci nella tabella. Una descrizione completa della neve nasce combinando liberamente le celle delle diverse colonne.</div>
                        </div>
                    </div>
                </div>
                <div class="snow-reference-table-wrap">
                    <table class="snow-reference-table">
                        <thead>
                            <tr>{''.join(f'<th>{col}</th>' for col in headers)}</tr>
                        </thead>
                        <tbody>
                            {html_rows_render}
                        </tbody>
                    </table>
                </div>
                <div class="snow-reference-note">
                    Le scritte sono completamente visibili e la tabella rimane leggibile anche con voci lunghe grazie all'impaginazione a larghezza automatica e al ritorno a capo nelle celle.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### Come leggere la classificazione")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Origine**")
            st.caption("Provenienza della neve: naturale, artificiale o mista.")
            st.markdown("**Consistenza**")
            st.caption("Come si presenta meccanicamente la superficie nevosa.")

        with c2:
            st.markdown("**Umidità**")
            st.caption("Stato della neve rispetto alla presenza di acqua liquida.")
            st.markdown("**Forma grano**")
            st.caption("Forma ed evoluzione del cristallo durante il metamorfismo.")

        with c3:
            st.markdown("**Granulometria**")
            st.caption("Dimensione prevalente dei grani, distinta dalla loro forma.")
            st.markdown("**Caratteristiche**")
            st.caption("Condizioni aggiuntive utili per descrivere la neve e scegliere il prodotto.")



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
