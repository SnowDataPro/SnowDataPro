import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import textwrap
import base64
from datetime import datetime, date
import math
import re
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
VERSIONE_DATABASE_APP = 12


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


@st.cache_resource(show_spinner=False)
def inizializza_database():
    """Esegue creazione/migrazioni DB una sola volta per processo Streamlit."""
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
            meteo TEXT,
            tipo_neve TEXT,
            condizione_pista TEXT,
            snow_origine TEXT,
            snow_consistenza TEXT,
            snow_umidita TEXT,
            snow_forma_grano TEXT,
            snow_granulometria TEXT,
            snow_caratteristiche TEXT,
            zero_batteria TEXT,
            zero_modello_sci TEXT,
            tipo_test TEXT,
            categoria_test_scorrimento TEXT,
            zero_riferimento_id INTEGER,
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
            prodotto_a_id INTEGER,
            prodotto_b_id INTEGER,
            paio_a INTEGER,
            paio_b INTEGER,
            zero_sessione_id INTEGER,
            note TEXT,
            creato_il TEXT NOT NULL,
            FOREIGN KEY(sessione_id) REFERENCES sessioni(id),
            FOREIGN KEY(sci_a_id) REFERENCES sci(id),
            FOREIGN KEY(sci_b_id) REFERENCES sci(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_scorrimento_aste (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessione_id INTEGER NOT NULL,
            posizione INTEGER,
            numero_sci TEXT,
            base_prodotto_id INTEGER,
            paraffina_prodotto_id INTEGER,
            top_coating_prodotto_id INTEGER,
            liquido_prodotto_id INTEGER,
            note TEXT,
            creato_il TEXT NOT NULL,
            FOREIGN KEY(sessione_id) REFERENCES sessioni(id),
            FOREIGN KEY(base_prodotto_id) REFERENCES catalogo_prodotti(id),
            FOREIGN KEY(paraffina_prodotto_id) REFERENCES catalogo_prodotti(id),
            FOREIGN KEY(top_coating_prodotto_id) REFERENCES catalogo_prodotti(id),
            FOREIGN KEY(liquido_prodotto_id) REFERENCES catalogo_prodotti(id)
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

    # Migrazione non distruttiva delle condizioni neve delle sessioni.
    colonne_sessioni = {
        r[1] for r in conn.execute("PRAGMA table_info(sessioni)").fetchall()
    }
    nuove_colonne_sessioni = {
        "snow_origine": "TEXT",
        "snow_consistenza": "TEXT",
        "snow_umidita": "TEXT",
        "snow_forma_grano": "TEXT",
        "snow_granulometria": "TEXT",
        "snow_caratteristiche": "TEXT",
        "zero_batteria": "TEXT",
        "zero_modello_sci": "TEXT",
        "meteo": "TEXT",
        "tipo_test": "TEXT",
        "categoria_test_scorrimento": "TEXT",
        "zero_riferimento_id": "INTEGER",
    }
    for nome_colonna, tipo_colonna in nuove_colonne_sessioni.items():
        if nome_colonna not in colonne_sessioni:
            conn.execute(
                f"ALTER TABLE sessioni ADD COLUMN {nome_colonna} {tipo_colonna}"
            )

    colonne_test_materiali = {
        r[1] for r in conn.execute("PRAGMA table_info(test_materiali)").fetchall()
    }
    nuove_colonne_test_materiali = {
        "prodotto_a_id": "INTEGER",
        "prodotto_b_id": "INTEGER",
        "paio_a": "INTEGER",
        "paio_b": "INTEGER",
        "zero_sessione_id": "INTEGER",
    }
    for nome_colonna, tipo_colonna in nuove_colonne_test_materiali.items():
        if nome_colonna not in colonne_test_materiali:
            conn.execute(
                f"ALTER TABLE test_materiali ADD COLUMN {nome_colonna} {tipo_colonna}"
            )

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
            'Molle su fondo compatto'
        )
        WHERE INSTR(COALESCE(snow_consistenza, ''), 'Soffice su superficie dura') > 0
    """)
    conn.execute("""
        UPDATE catalogo_prodotti
        SET tipo_neve = REPLACE(
            tipo_neve,
            'Soffice su superficie dura',
            'Molle su fondo compatto'
        )
        WHERE INSTR(COALESCE(tipo_neve, ''), 'Soffice su superficie dura') > 0
    """)
    # Uniformazione definitiva della consistenza neve nei dati storici.
    conn.execute("""
        UPDATE catalogo_prodotti
        SET snow_consistenza = REPLACE(
            snow_consistenza,
            'Soffice su fondo ghiacciato',
            'Molle su fondo compatto'
        )
        WHERE INSTR(COALESCE(snow_consistenza, ''), 'Soffice su fondo ghiacciato') > 0
    """)
    conn.execute("""
        UPDATE catalogo_prodotti
        SET tipo_neve = REPLACE(
            tipo_neve,
            'Soffice su fondo ghiacciato',
            'Molle su fondo compatto'
        )
        WHERE INSTR(COALESCE(tipo_neve, ''), 'Soffice su fondo ghiacciato') > 0
    """)
    conn.execute("""
        UPDATE sessioni
        SET snow_consistenza = REPLACE(
            snow_consistenza,
            'Soffice su fondo ghiacciato',
            'Molle su fondo compatto'
        )
        WHERE INSTR(COALESCE(snow_consistenza, ''), 'Soffice su fondo ghiacciato') > 0
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

    # Aggiornamento nomenclatura scioline di tenuta.
    conn.execute("""
        UPDATE catalogo_prodotti
        SET tipo = 'Kick wax'
        WHERE categoria = 'tenuta'
          AND TRIM(COALESCE(tipo, '')) = 'Stick'
    """)
    conn.execute("""
        UPDATE catalogo_prodotti
        SET tipo = 'Base kick wax'
        WHERE categoria = 'tenuta'
          AND TRIM(COALESCE(tipo, '')) = 'Base stick'
    """)

    # Non convertire più automaticamente un range generico delle scioline di
    # tenuta in "Neve nuova". Il range generico rappresenta intenzionalmente
    # la scelta "Non specificato" e deve restare tale anche dopo refresh/redeploy.
    # La vecchia migrazione è stata rimossa dalla versione 9.

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

    box-shadow: none !important;

    margin-top: 0.35rem;
}

/* Rimuove completamente i riquadri degli expander, in stile Sector G2 Lab */
section[data-testid="stSidebar"]
[data-testid="stExpander"] > details,
section[data-testid="stSidebar"]
[data-testid="stExpander"] > details[open],
section[data-testid="stSidebar"]
[data-testid="stExpander"] > details > summary,
section[data-testid="stSidebar"]
[data-testid="stExpander"] > details > div {
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    background: transparent !important;
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

    div[class*="st-key-zero_snow_panel"],
    div[class*="st-key-zero_table_panel"],
    div[class*="st-key-zero_summary_panel"] {
        background: #ffffff !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-medium) !important;
        padding: 1rem 1.1rem 1.05rem 1.1rem !important;
        box-shadow: var(--shadow-soft) !important;
        margin-bottom: 1rem !important;
    }

    .zero-section-title {
        color: var(--text-main);
        font-size: 1.05rem;
        font-weight: 700;
        line-height: 1.2;
        margin-bottom: 0.18rem;
    }

    .zero-section-caption {
        color: var(--text-light);
        font-size: 0.82rem;
        line-height: 1.4;
        margin-bottom: 0.75rem;
    }

    .zero-test-kicker {
        color: var(--accent);
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        margin-bottom: 0.28rem;
    }

    .zero-test-header-row {
        display: flex;
        align-items: stretch;
        gap: 0.55rem;
        flex-wrap: wrap;
        margin: 0.78rem 0 0.72rem 0;
    }

    .zero-test-chip {
        min-width: 120px;
        flex: 0 1 auto;
        padding: 0.56rem 0.72rem;
        border: 1px solid var(--border);
        border-radius: var(--radius-small);
        background: var(--surface-soft);
    }

    .zero-test-chip-label {
        color: var(--text-light);
        font-size: 0.66rem;
        font-weight: 800;
        letter-spacing: 0.055em;
        text-transform: uppercase;
        line-height: 1.15;
        margin-bottom: 0.16rem;
    }

    .zero-test-chip-value {
        color: var(--text-main);
        font-size: 0.88rem;
        font-weight: 700;
        line-height: 1.25;
        white-space: nowrap;
    }

    .zero-test-guide {
        display: flex;
        gap: 0.45rem 1rem;
        flex-wrap: wrap;
        align-items: center;
        padding: 0.55rem 0.72rem;
        margin: 0 0 0.82rem 0;
        border-left: 3px solid var(--accent);
        background: #f7f9fa;
        border-radius: 0 var(--radius-small) var(--radius-small) 0;
        color: var(--text-secondary);
        font-size: 0.76rem;
        line-height: 1.35;
    }

    .zero-test-guide strong {
        color: var(--text-main);
        font-weight: 700;
    }

    div[class*="st-key-zero_table_panel"] div[data-testid="stDataFrame"] {
        border: 1px solid var(--border-strong) !important;
        border-radius: 10px !important;
        box-shadow: none !important;
        background: #ffffff !important;
        margin-top: 0.1rem !important;
    }

    div[class*="st-key-zero_table_panel"] [data-testid="stButton"] button {
        margin-top: 0.35rem !important;
        min-height: 2.85rem !important;
        font-weight: 700 !important;
    }

    .zero-session-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 0.42rem 0.9rem;
        padding: 0.68rem 0.78rem;
        background: var(--surface-soft);
        border: 1px solid var(--border);
        border-radius: var(--radius-small);
        margin: 0.15rem 0 0.85rem 0;
        color: var(--text-secondary);
        font-size: 0.80rem;
    }

    .zero-session-strip strong {
        color: var(--text-main);
        font-weight: 600;
    }

    div[class*="st-key-catalog_card_"] {
        background: #ffffff !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-medium) !important;
        padding: 0.9rem 0.95rem 0.85rem 0.95rem !important;
        min-height: 390px !important;
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
        height: 24px;
        min-height: 24px;
        max-height: 24px;
        margin-bottom: 0.42rem;
        color: var(--text-secondary);
        font-size: 0.78rem;
        font-weight: 700;
        line-height: 24px;
        letter-spacing: 0.035em;
        text-transform: uppercase;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
    }

    /* Slot temperatura identico per tutte le card. */
    .catalog-card-temperature-slot {
        min-height: 5.55rem;
        height: 5.55rem;
        max-height: 5.55rem;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        margin-top: 0.02rem;
        margin-bottom: 0.14rem;
    }

    .catalog-temp-block-title {
        color: var(--text-secondary);
        font-size: 0.69rem;
        font-weight: 700;
        line-height: 1.15;
        letter-spacing: 0.035em;
        text-transform: uppercase;
        margin: 0 0 0.10rem 0;
    }

    .catalog-temp-reference {
        color: var(--text-secondary);
        font-size: 0.72rem;
        line-height: 1.15;
        margin: 0 0 0.42rem 0;
    }

    .catalog-temperature-line {
        display: flex;
        align-items: center;
        gap: 0.22rem;
        margin: 0.16rem 0;
        color: var(--text-secondary);
        font-size: 0.76rem;
        line-height: 1.18;
        min-width: 0;
    }

    .catalog-temperature-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 auto;
        color: var(--text-secondary);
    }

    .catalog-temperature-icon svg {
        width: 16px !important;
        height: 16px !important;
        margin-right: 0 !important;
        vertical-align: 0 !important;
    }

    .catalog-temperature-text {
        color: var(--text-secondary);
        font-size: 0.76rem;
        line-height: 1.18;
        min-width: 0;
    }

    .catalog-temperature-label {
        color: var(--text-secondary);
        font-weight: 600;
    }

    .catalog-temp-detail {
        background: var(--surface-soft);
        border: 1px solid var(--border);
        border-radius: var(--radius-small);
        padding: 0.65rem 0.75rem;
        margin: 0.30rem 0 0.55rem 0;
    }

    .catalog-temp-detail .catalog-temp-block-title {
        font-size: 0.72rem;
    }

    .catalog-temp-detail .catalog-temp-reference {
        font-size: 0.76rem;
        margin-bottom: 0.44rem;
    }

    .catalog-temp-detail .catalog-temperature-line,
    .catalog-temp-detail .catalog-temperature-text {
        font-size: 0.80rem;
    }

    .catalog-temp-detail .catalog-temperature-line {
        margin-top: 0.20rem;
        margin-bottom: 0.20rem;
    }

    div[class*="st-key-catalog_card_"] h3 {
        height: 4.0rem !important;
        min-height: 4.0rem !important;
        max-height: 4.0rem !important;
        overflow: hidden !important;
        display: flex !important;
        align-items: flex-start !important;
        font-size: 1.00rem !important;
        line-height: 1.18 !important;
        margin-top: 0.18rem !important;
        margin-bottom: 0.18rem !important;
    }

    div[class*="st-key-catalog_card_"] [data-testid="stExpander"] {
        margin-top: 0.38rem !important;
        margin-bottom: 0 !important;
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

@st.cache_data(ttl=600, max_entries=160, show_spinner=False)
def leggi_df(query, params=()):
    """Cache breve delle letture DB: i filtri non riaprono Turso a ogni rerun."""
    conn = apri_connessione_database()
    try:
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def _invalida_cache_dati():
    """Invalida i dati dopo ogni modifica reale al database."""
    try:
        leggi_df.clear()
    except Exception:
        pass

    # Le foto del catalogo sono tenute in RAM di sessione per evitare
    # trasferimento + decodifica base64 a ogni cambio filtro.
    try:
        for chiave in list(st.session_state.keys()):
            if str(chiave).startswith("_catalog_photo_bytes_"):
                st.session_state.pop(chiave, None)
    except Exception:
        pass


def esegui(query, params=()):
    conn = apri_connessione_database()
    try:
        conn.execute(query, params)
        conn.commit()
    finally:
        conn.close()
    _invalida_cache_dati()


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


def tabella_zero_test_da_risultati(df_risultati):
    """Costruisce la matrice 1-10 con P1-P4, media, SD e paio più simile."""
    colonne = [
        "Paio", "P1 (s)", "P2 (s)", "P3 (s)", "P4 (s)",
        "Media (s)", "SD (s)", "Paio più simile", "Δ dal più simile (s)", "Note",
    ]
    if df_risultati is None or df_risultati.empty:
        return pd.DataFrame(columns=colonne)

    gruppi = {}
    paia_occupati = set()
    prossimo_libero = 1

    for sci_id, gruppo in df_risultati.groupby("sci_id", sort=False):
        gruppo = gruppo.sort_values("prova_numero")
        codice = str(gruppo.iloc[0].get("sci") or "").strip()
        try:
            paio_num = int(codice)
            if paio_num < 1 or paio_num > 10 or paio_num in paia_occupati:
                raise ValueError
        except (TypeError, ValueError):
            while prossimo_libero in paia_occupati and prossimo_libero <= 10:
                prossimo_libero += 1
            if prossimo_libero > 10:
                continue
            paio_num = prossimo_libero

        paia_occupati.add(paio_num)
        tempi = {}
        for _, prova in gruppo.iterrows():
            try:
                numero = int(prova.get("prova_numero"))
                valore = float(prova.get("tempo_sec"))
            except (TypeError, ValueError):
                continue
            if 1 <= numero <= 4:
                tempi[numero] = round(valore, 2)

        note_valide = [
            str(v).strip() for v in gruppo.get("note", pd.Series(dtype=str)).tolist()
            if str(v or "").strip()
        ]
        gruppi[paio_num] = (tempi, note_valide[0] if note_valide else "")

    righe = []
    for paio in range(1, 11):
        tempi, nota = gruppi.get(paio, ({}, ""))
        righe.append({
            "Paio": paio,
            "P1 (s)": tempi.get(1),
            "P2 (s)": tempi.get(2),
            "P3 (s)": tempi.get(3),
            "P4 (s)": tempi.get(4),
            "Note": nota,
        })

    df_calc = pd.DataFrame(righe)
    colonne_tempi = ["P1 (s)", "P2 (s)", "P3 (s)", "P4 (s)"]
    for colonna in colonne_tempi:
        df_calc[colonna] = pd.to_numeric(df_calc[colonna], errors="coerce")

    df_calc["Media (s)"] = df_calc[colonne_tempi].mean(axis=1, skipna=True)
    conteggio = df_calc[colonne_tempi].count(axis=1)
    df_calc.loc[conteggio == 0, "Media (s)"] = pd.NA

    df_calc["SD (s)"] = df_calc[colonne_tempi].std(axis=1, skipna=True, ddof=1)
    df_calc.loc[conteggio == 1, "SD (s)"] = 0.0
    df_calc.loc[conteggio == 0, "SD (s)"] = pd.NA

    paio_simile = []
    delta_simile = []
    for idx, riga in df_calc.iterrows():
        media_corrente = riga["Media (s)"]
        if pd.isna(media_corrente):
            paio_simile.append(None)
            delta_simile.append(None)
            continue

        candidati = df_calc.loc[
            (df_calc.index != idx) & df_calc["Media (s)"].notna(),
            ["Paio", "Media (s)"],
        ].copy()
        if candidati.empty:
            paio_simile.append(None)
            delta_simile.append(None)
            continue

        candidati["delta"] = (candidati["Media (s)"] - float(media_corrente)).abs()
        candidati = candidati.sort_values(["delta", "Paio"], ascending=[True, True])
        match = candidati.iloc[0]
        paio_simile.append(int(match["Paio"]))
        delta_simile.append(float(match["delta"]))

    df_calc["Paio più simile"] = paio_simile
    df_calc["Δ dal più simile (s)"] = delta_simile

    for colonna in colonne_tempi + ["Media (s)", "SD (s)", "Δ dal più simile (s)"]:
        df_calc[colonna] = pd.to_numeric(df_calc[colonna], errors="coerce").round(2)

    return df_calc[colonne]


def coppia_zero_test_piu_vicina(df_tabella):
    """Restituisce (paio_a, paio_b, delta) evitando duplicati speculari."""
    if df_tabella is None or df_tabella.empty:
        return None
    coppie = {}
    for _, riga in df_tabella.iterrows():
        a = riga.get("Paio")
        b = riga.get("Paio più simile")
        delta = riga.get("Δ dal più simile (s)")
        if pd.isna(a) or pd.isna(b) or pd.isna(delta):
            continue
        coppia = tuple(sorted((int(a), int(b))))
        if coppia[0] == coppia[1]:
            continue
        valore = float(delta)
        if coppia not in coppie or valore < coppie[coppia]:
            coppie[coppia] = valore
    if not coppie:
        return None
    (a, b), delta = sorted(coppie.items(), key=lambda item: (item[1], item[0]))[0]
    return a, b, delta


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
                    "Paio A": righe[i]["sci"],
                    "Paio B": righe[j]["sci"],
                    "Tempo A": round(righe[i]["tempo_medio"], 2),
                    "Tempo B": round(righe[j]["tempo_medio"], 2),
                    "Δ medio (s)": round(delta, 2),
                })

    if not coppie:
        return pd.DataFrame()

    return pd.DataFrame(coppie).sort_values("Δ medio (s)").reset_index(drop=True)



def salva_zero_test_matrice(sessione_id, righe, classificazione):
    """Sostituisce le prove della sessione, crea gli sci mancanti e salva la classificazione neve."""
    conn = apri_connessione_database()
    try:
        conn.execute("DELETE FROM zero_test WHERE sessione_id = ?", (int(sessione_id),))
        for riga in righe:
            codice_sci = str(riga.get("codice_sci") or "").strip()
            if not codice_sci:
                continue

            esistente = conn.execute(
                "SELECT id FROM sci WHERE codice = ? COLLATE NOCASE LIMIT 1",
                (codice_sci,),
            ).fetchone()
            if esistente:
                sci_id = int(esistente[0])
            else:
                conn.execute(
                    "INSERT INTO sci (codice, marca, modello, tecnica, note) VALUES (?, '', '', 'Entrambi', '')",
                    (codice_sci,),
                )
                nuovo = conn.execute(
                    "SELECT id FROM sci WHERE codice = ? COLLATE NOCASE LIMIT 1",
                    (codice_sci,),
                ).fetchone()
                sci_id = int(nuovo[0])

            note = str(riga.get("note") or "").strip()
            for prova_numero, tempo in enumerate(riga["tempi"], start=1):
                if tempo is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO zero_test (sessione_id, sci_id, prova_numero, tempo_sec, note)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (int(sessione_id), sci_id, int(prova_numero), float(tempo), note),
                )

        conn.execute(
            """
            UPDATE sessioni
            SET snow_origine = ?, snow_consistenza = ?, snow_umidita = ?,
                snow_forma_grano = ?, snow_granulometria = ?, snow_caratteristiche = ?,
                zero_batteria = ?
            WHERE id = ?
            """,
            (
                classificazione.get("snow_origine", ""),
                classificazione.get("snow_consistenza", ""),
                classificazione.get("snow_umidita", ""),
                classificazione.get("snow_forma_grano", ""),
                classificazione.get("snow_granulometria", ""),
                classificazione.get("snow_caratteristiche", ""),
                classificazione.get("zero_batteria", ""),
                int(sessione_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    _invalida_cache_dati()

def _valori_sessione_neve(valore, opzioni):
    valori = [v.strip() for v in str(valore or "").split(",") if v.strip()]
    if "Tutte" in valori:
        return list(opzioni)
    return [v for v in valori if v in opzioni]


def _compatta_neve_sessione(valori, opzioni):
    puliti = [v for v in valori if v in opzioni]
    if opzioni and len(puliti) == len(opzioni) and set(puliti) == set(opzioni):
        return "Tutte"
    return ", ".join(puliti)


def _numero_opzionale(valore):
    valore = str(valore or "").strip().replace(",", ".")
    if not valore:
        return None
    return float(valore)


def _formatta_temperatura_1d(valore, default=0.0):
    """Formato unico per temperature aria/neve: un decimale e punto."""
    try:
        if valore is None or pd.isna(valore):
            valore = default
        return f"{float(valore):.1f}"
    except Exception:
        return f"{float(default):.1f}"


def _parse_temperatura_1d(valore):
    """Accetta punto o virgola in input, salva sempre un numero a un decimale."""
    testo = str(valore or "").strip().replace(",", ".")
    if not testo:
        raise ValueError("Temperatura mancante")
    return round(float(testo), 1)


METEO_OPZIONI = [
    "Soleggiato",
    "Parzialmente nuvoloso",
    "Coperto",
    "Precipitazioni nevose",
    "Precipitazioni piovose",
    "Nebbia/foschia",
]


def _formatta_dataframe_temperature_ambientali(df):
    """Converte solo le colonne aria/neve destinate alla visualizzazione."""
    risultato = df.copy()
    for colonna in ["temperatura_aria", "temperatura_neve", "T aria °C", "T neve °C"]:
        if colonna in risultato.columns:
            risultato[colonna] = risultato[colonna].apply(
                lambda v: _formatta_temperatura_1d(v) if pd.notna(v) else "—"
            )
    return risultato


def _testo_range(minimo, massimo, unita="°C"):
    if pd.isna(minimo) and pd.isna(massimo):
        return "—"
    if pd.isna(minimo):
        return f"≤ {massimo:g} {unita}"
    if pd.isna(massimo):
        return f"≥ {minimo:g} {unita}"
    if float(minimo) == float(massimo):
        return f"{minimo:g} {unita}"
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
     style="display:inline-block;vertical-align:-4px;color:#395b68;margin-right:4px;">
  <g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 2.8 19.45 7.1 19.45 15.9 12 20.2 4.55 15.9 4.55 7.1Z"/>
    <path d="M12 6.9 15.9 9.15 15.9 13.85 12 16.1 8.1 13.85 8.1 9.15Z"/>
  </g>
</svg>
"""

def _intervallo_duale_summary(temp_nuova_min, temp_nuova_max, temp_trasf_min, temp_trasf_max):
    intervalli = []
    testo_nuova = _testo_range(temp_nuova_min, temp_nuova_max, "°C")
    testo_trasf = _testo_range(temp_trasf_min, temp_trasf_max, "°C")
    if testo_nuova != "—":
        intervalli.append(("❄️", "Neve nuova", testo_nuova))
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
    if foto_data is None:
        return False
    try:
        if isinstance(foto_data, (bytes, bytearray, memoryview)):
            dati = bytes(foto_data)
        else:
            valore = str(foto_data or "").strip()
            if not valore:
                return False
            dati = base64.b64decode(valore)

        if not dati:
            return False
        if width is not None:
            st.image(dati, width=width)
        else:
            st.image(dati, use_container_width=use_container_width)
        return True
    except Exception:
        return False


def _foto_catalogo_sessione(categoria):
    """Carica e decodifica le foto una volta sola per catalogo e sessione."""
    chiave = f"_catalog_photo_bytes_{categoria}"
    if chiave in st.session_state:
        return st.session_state[chiave]

    foto_df = leggi_df("""
        SELECT id, foto_data
        FROM catalogo_prodotti
        WHERE categoria = ?
    """, (categoria,))

    foto_bytes = {}
    if not foto_df.empty:
        for record in foto_df.to_dict("records"):
            valore = str(record.get("foto_data") or "").strip()
            if not valore:
                continue
            try:
                foto_bytes[int(record["id"])] = base64.b64decode(valore)
            except Exception:
                continue

    st.session_state[chiave] = foto_bytes
    return foto_bytes


def pagina_trova_prodotto_migliore():
    mostra_banner(
        "Trova prodotto migliore",
        "Inserisci temperatura e caratteristiche della neve per individuare rapidamente i prodotti più compatibili.",
    )

    st.markdown("### Condizioni attuali")
    st.caption(
        "Prima versione del motore di suggerimento: la temperatura viene considerata come criterio principale, "
        "mentre la classificazione neve aumenta o riduce il punteggio di compatibilità."
    )

    snow_option_groups = {
        "Origine": ["Naturale", "Artificiale", "Mista"],
        "Consistenza": [
            "Compatta",
            "Sfarinata / Soffice",
            "Sgranata",
            "Ghiacciata",
            "Molle su fondo compatto",
            "Soffice su fondo compatto",
            "Molle",
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
    snow_field_map = {
        "Origine": "snow_origine",
        "Consistenza": "snow_consistenza",
        "Umidità neve": "snow_umidita",
        "Forma grano": "snow_forma_grano",
        "Granulometria": "snow_granulometria",
        "Caratteristiche": "snow_caratteristiche",
    }

    c_tipo, c_temp, c_rif = st.columns([1.1, 1, 1])
    with c_tipo:
        famiglia = st.selectbox(
            "Famiglia prodotto",
            ["Prodotti di scorrimento", "Scioline di tenuta"],
            key="best_product_family",
        )
    with c_temp:
        temperatura = st.number_input(
            "Temperatura (°C)",
            min_value=-40.0,
            max_value=20.0,
            value=-5.0,
            step=0.5,
            format="%.1f",
            key="best_product_temperature",
        )
    with c_rif:
        opzioni_riferimento_best = (
            ["Aria", "Neve"]
            if famiglia == "Scioline di tenuta"
            else ["Aria", "Neve", "Range produttore", "Non specificato"]
        )
        if st.session_state.get("best_product_temperature_ref") not in opzioni_riferimento_best:
            st.session_state["best_product_temperature_ref"] = opzioni_riferimento_best[0]
        riferimento = st.selectbox(
            "Temperatura riferita a",
            opzioni_riferimento_best,
            key="best_product_temperature_ref",
        )

    st.markdown("#### Classificazione neve")
    st.caption("Compila solo i parametri che conosci: quelli lasciati vuoti non penalizzano il prodotto.")

    selezioni = {}
    c1, c2, c3 = st.columns(3)
    with c1:
        selezioni["Origine"] = st.multiselect(
            "Origine", snow_option_groups["Origine"], key="best_snow_origin"
        )
    with c2:
        selezioni["Consistenza"] = st.multiselect(
            "Consistenza", snow_option_groups["Consistenza"], key="best_snow_consistency"
        )
    with c3:
        selezioni["Umidità neve"] = st.multiselect(
            "Umidità neve", snow_option_groups["Umidità neve"], key="best_snow_humidity"
        )

    c4, c5, c6 = st.columns(3)
    with c4:
        selezioni["Forma grano"] = st.multiselect(
            "Forma grano", snow_option_groups["Forma grano"], key="best_snow_grain"
        )
    with c5:
        selezioni["Granulometria"] = st.multiselect(
            "Granulometria", snow_option_groups["Granulometria"], key="best_snow_size"
        )
    with c6:
        selezioni["Caratteristiche"] = st.multiselect(
            "Caratteristiche", snow_option_groups["Caratteristiche"], key="best_snow_features"
        )

    categoria = "scorrimento" if famiglia == "Prodotti di scorrimento" else "tenuta"

    prodotti = leggi_df("""
        SELECT
            id, nome, marca, tipo, categoria,
            temp_min, temp_max, tipo_temperatura,
            temp_nuova_min, temp_nuova_max,
            temp_trasformata_min, temp_trasformata_max,
            tipo_neve,
            snow_origine, snow_consistenza, snow_umidita,
            snow_forma_grano, snow_granulometria, snow_caratteristiche
        FROM catalogo_prodotti
        WHERE categoria = ?
        ORDER BY marca COLLATE NOCASE, nome COLLATE NOCASE
    """, (categoria,))

    def _lista_valori(valore):
        return {
            voce.strip()
            for voce in str(valore or "").split(",")
            if voce.strip()
        }

    def _intervallo_riga(riga):
        tipo_ref = str(riga.get("tipo_temperatura") or "").strip().lower()
        ref_richiesto = riferimento.strip().lower()

        if ref_richiesto != "non specificato" and tipo_ref not in {ref_richiesto, "non specificato", ""}:
            return None

        if categoria == "tenuta":
            forma = set(selezioni.get("Forma grano", []))
            caratteristiche = set(selezioni.get("Caratteristiche", []))
            nuova_richiesta = bool(
                "Nuova (cristalli esagonali)" in forma
                or "Cadente" in caratteristiche
            )
            trasformata_richiesta = bool(
                any("trasformat" in voce.lower() for voce in forma)
                or any("in trasformazione" in voce.lower() for voce in forma)
            )

            intervalli = []
            if nuova_richiesta or not trasformata_richiesta:
                intervalli.append((
                    riga.get("temp_nuova_min"),
                    riga.get("temp_nuova_max"),
                    "Neve nuova",
                ))
            if trasformata_richiesta or not nuova_richiesta:
                intervalli.append((
                    riga.get("temp_trasformata_min"),
                    riga.get("temp_trasformata_max"),
                    "Neve trasformata",
                ))

            validi = []
            for minimo, massimo, etichetta in intervalli:
                if pd.isna(minimo) and pd.isna(massimo):
                    continue
                min_eff = float("-inf") if pd.isna(minimo) else float(minimo)
                max_eff = float("inf") if pd.isna(massimo) else float(massimo)
                if min_eff <= float(temperatura) <= max_eff:
                    validi.append((minimo, massimo, etichetta))
            if validi:
                return validi[0]

            # Compatibilità retroattiva con scioline vecchie a intervallo unico.
            minimo, massimo = riga.get("temp_min"), riga.get("temp_max")
            if not (pd.isna(minimo) and pd.isna(massimo)):
                min_eff = float("-inf") if pd.isna(minimo) else float(minimo)
                max_eff = float("inf") if pd.isna(massimo) else float(massimo)
                if min_eff <= float(temperatura) <= max_eff:
                    return (minimo, massimo, "Range produttore")
            return None

        minimo, massimo = riga.get("temp_min"), riga.get("temp_max")
        if pd.isna(minimo) and pd.isna(massimo):
            return None
        min_eff = float("-inf") if pd.isna(minimo) else float(minimo)
        max_eff = float("inf") if pd.isna(massimo) else float(massimo)
        if min_eff <= float(temperatura) <= max_eff:
            etichetta = "Range produttore" if ref_richiesto == "range produttore" else riferimento
            return (minimo, massimo, etichetta)
        return None

    risultati = []
    parametri_compilati = [nome for nome, valori in selezioni.items() if valori]

    if not prodotti.empty:
        for riga in prodotti.to_dict("records"):
            intervallo = _intervallo_riga(riga)
            if intervallo is None:
                continue

            score_neve = 0.0
            dettagli_match = []
            for nome_gruppo in parametri_compilati:
                richiesti = set(selezioni[nome_gruppo])
                prodotto_vals = _lista_valori(riga.get(snow_field_map[nome_gruppo]))
                if not prodotto_vals:
                    # fallback per prodotti più vecchi
                    prodotto_vals = _lista_valori(riga.get("tipo_neve"))

                if "Tutte" in prodotto_vals:
                    quota = 1.0
                else:
                    quota = len(richiesti & prodotto_vals) / max(1, len(richiesti))
                score_neve += quota
                if quota > 0:
                    dettagli_match.append(nome_gruppo)

            if parametri_compilati:
                compat_neve = score_neve / len(parametri_compilati)
            else:
                compat_neve = 1.0

            minimo, massimo, etichetta_intervallo = intervallo
            if not pd.isna(minimo) and not pd.isna(massimo):
                centro = (float(minimo) + float(massimo)) / 2.0
                ampiezza = max(1.0, abs(float(massimo) - float(minimo)))
                centralita = max(0.0, 1.0 - abs(float(temperatura) - centro) / ampiezza)
            else:
                centralita = 0.5

            # 70% temperatura / 30% neve. È volutamente semplice per la prima versione.
            score_totale = 70.0 + 20.0 * compat_neve + 10.0 * centralita
            risultati.append({
                **riga,
                "score": round(score_totale, 1),
                "compat_neve": compat_neve,
                "intervallo_usato": _testo_range(minimo, massimo, "°C"),
                "tipo_intervallo": etichetta_intervallo,
                "match": dettagli_match,
            })

    risultati.sort(key=lambda x: (-x["score"], str(x.get("marca") or ""), str(x.get("nome") or "")))

    st.markdown("### Prodotti consigliati")
    if not risultati:
        st.info("Nessun prodotto del catalogo rientra nelle condizioni inserite.")
        return

    foto = _foto_catalogo_sessione(categoria)
    migliori = risultati[:6]
    for start_idx in range(0, len(migliori), 3):
        colonne = st.columns(3)
        for col_idx, prodotto in enumerate(migliori[start_idx:start_idx + 3]):
            with colonne[col_idx]:
                with st.container(border=True):
                    categoria_prod = str(prodotto.get("tipo") or "").strip()
                    if categoria_prod:
                        st.caption(categoria_prod.upper())

                    foto_prodotto = foto.get(int(prodotto["id"]))
                    if foto_prodotto:
                        st.image(foto_prodotto, use_container_width=True)

                    marca = str(prodotto.get("marca") or "").strip()
                    nome = str(prodotto.get("nome") or "Prodotto").strip()
                    titolo = f"{marca} - {nome}" if marca else nome
                    st.markdown(f"#### {titolo}")
                    st.markdown(f"**Compatibilità stimata: {prodotto['score']:.0f}%**")
                    st.caption(
                        f"Temperatura: {prodotto['intervallo_usato']} · {prodotto['tipo_intervallo']}"
                    )
                    if prodotto["match"]:
                        st.caption("Match neve: " + " · ".join(prodotto["match"]))

    st.caption(
        "Ranking provvisorio: lo useremo come base per definire successivamente pesi, priorità e logica specifica per gara/test."
    )


@st.fragment
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
            "Molle su fondo compatto",
            "Soffice su fondo compatto",
            "Molle",
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
    tenuta_nome_key = f"tenuta_nome_{app_widget_suffix}"
    tenuta_marca_key = f"tenuta_marca_{app_widget_suffix}"
    tenuta_tipo_key = f"tenuta_tipo_{app_widget_suffix}"
    tenuta_condizioni_key = f"tenuta_condizioni_range_{app_widget_suffix}"
    tenuta_temp_nuova_min_key = f"tenuta_temp_nuova_min_{app_widget_suffix}"
    tenuta_temp_nuova_max_key = f"tenuta_temp_nuova_max_{app_widget_suffix}"
    tenuta_temp_nuova_unica_key = f"tenuta_temp_nuova_unica_{app_widget_suffix}"
    tenuta_temp_trasf_min_key = f"tenuta_temp_trasf_min_{app_widget_suffix}"
    tenuta_temp_trasf_max_key = f"tenuta_temp_trasf_max_{app_widget_suffix}"
    tenuta_temp_trasf_unica_key = f"tenuta_temp_trasf_unica_{app_widget_suffix}"
    tenuta_temp_tutte_min_key = f"tenuta_temp_tutte_min_{app_widget_suffix}"
    tenuta_temp_tutte_max_key = f"tenuta_temp_tutte_max_{app_widget_suffix}"
    tenuta_temp_tutte_unica_key = f"tenuta_temp_tutte_unica_{app_widget_suffix}"
    tenuta_ui_keys = [
        temp_ref_state_key,
        tenuta_nome_key,
        tenuta_marca_key,
        tenuta_tipo_key,
        tenuta_condizioni_key,
        tenuta_temp_nuova_min_key,
        tenuta_temp_nuova_max_key,
        tenuta_temp_nuova_unica_key,
        tenuta_temp_trasf_min_key,
        tenuta_temp_trasf_max_key,
        tenuta_temp_trasf_unica_key,
        tenuta_temp_tutte_min_key,
        tenuta_temp_tutte_max_key,
        tenuta_temp_tutte_unica_key,
    ]

    if categoria_tenuta:
        valore_nome_tenuta = (
            str(prodotto_edit.get("nome") or "") if modalita_modifica else ""
        )
        valore_marca_tenuta = (
            str(prodotto_edit.get("marca") or "") if modalita_modifica else ""
        )
        valore_tipo_tenuta = (
            str(prodotto_edit.get("tipo") or "") if modalita_modifica else ""
        )

        if tenuta_nome_key not in st.session_state:
            st.session_state[tenuta_nome_key] = valore_nome_tenuta
        if tenuta_marca_key not in st.session_state:
            st.session_state[tenuta_marca_key] = valore_marca_tenuta
        if tenuta_tipo_key not in st.session_state:
            st.session_state[tenuta_tipo_key] = (
                valore_tipo_tenuta if valore_tipo_tenuta in tipi else tipi[0]
            )

        tipo_temp_db = (
            str(prodotto_edit.get("tipo_temperatura") or "").strip()
            if modalita_modifica else "Aria"
        )
        if tipo_temp_db == "Neve":
            tipo_temp_ui = "Neve"
        elif tipo_temp_db == "Non specificato":
            tipo_temp_ui = "Non specificato"
        else:
            tipo_temp_ui = "Aria / ambiente"
        if temp_ref_state_key not in st.session_state:
            st.session_state[temp_ref_state_key] = tipo_temp_ui

        nuova_min_db = (
            _input_numero_da_db(prodotto_edit.get("temp_nuova_min"))
            if modalita_modifica else ""
        )
        nuova_max_db = (
            _input_numero_da_db(prodotto_edit.get("temp_nuova_max"))
            if modalita_modifica else ""
        )
        trasf_min_db = (
            _input_numero_da_db(prodotto_edit.get("temp_trasformata_min"))
            if modalita_modifica else ""
        )
        trasf_max_db = (
            _input_numero_da_db(prodotto_edit.get("temp_trasformata_max"))
            if modalita_modifica else ""
        )
        generic_min_db = (
            _input_numero_da_db(prodotto_edit.get("temp_min"))
            if modalita_modifica else ""
        )
        generic_max_db = (
            _input_numero_da_db(prodotto_edit.get("temp_max"))
            if modalita_modifica else ""
        )

        condizioni_default = []
        tutte_min_db = ""
        tutte_max_db = ""
        nuova_unica_db = ""
        trasf_unica_db = ""
        tutte_unica_db = ""

        range_tutte = (
            (nuova_min_db or nuova_max_db)
            and (trasf_min_db or trasf_max_db)
            and nuova_min_db == trasf_min_db
            and nuova_max_db == trasf_max_db
        )

        if range_tutte:
            condizioni_default = ["Tutte le tipologie di neve"]
            if nuova_min_db and nuova_max_db and nuova_min_db == nuova_max_db:
                tutte_unica_db = nuova_min_db
            else:
                tutte_min_db = nuova_min_db
                tutte_max_db = nuova_max_db
        else:
            if nuova_min_db or nuova_max_db:
                condizioni_default.append("Neve nuova")
                if nuova_min_db and nuova_max_db and nuova_min_db == nuova_max_db:
                    nuova_unica_db = nuova_min_db
                    nuova_min_db = ""
                    nuova_max_db = ""
            if trasf_min_db or trasf_max_db:
                condizioni_default.append("Neve trasformata")
                if trasf_min_db and trasf_max_db and trasf_min_db == trasf_max_db:
                    trasf_unica_db = trasf_min_db
                    trasf_min_db = ""
                    trasf_max_db = ""

        if modalita_modifica and not condizioni_default and (generic_min_db or generic_max_db):
            condizioni_default = ["Non specificato"]
            if generic_min_db and generic_max_db and generic_min_db == generic_max_db:
                tutte_unica_db = generic_min_db
            else:
                tutte_min_db = generic_min_db
                tutte_max_db = generic_max_db

        if tenuta_condizioni_key not in st.session_state:
            st.session_state[tenuta_condizioni_key] = condizioni_default
        if tenuta_temp_nuova_min_key not in st.session_state:
            st.session_state[tenuta_temp_nuova_min_key] = nuova_min_db
        if tenuta_temp_nuova_max_key not in st.session_state:
            st.session_state[tenuta_temp_nuova_max_key] = nuova_max_db
        if tenuta_temp_nuova_unica_key not in st.session_state:
            st.session_state[tenuta_temp_nuova_unica_key] = nuova_unica_db
        if tenuta_temp_trasf_min_key not in st.session_state:
            st.session_state[tenuta_temp_trasf_min_key] = trasf_min_db
        if tenuta_temp_trasf_max_key not in st.session_state:
            st.session_state[tenuta_temp_trasf_max_key] = trasf_max_db
        if tenuta_temp_trasf_unica_key not in st.session_state:
            st.session_state[tenuta_temp_trasf_unica_key] = trasf_unica_db
        if tenuta_temp_tutte_min_key not in st.session_state:
            st.session_state[tenuta_temp_tutte_min_key] = tutte_min_db
        if tenuta_temp_tutte_max_key not in st.session_state:
            st.session_state[tenuta_temp_tutte_max_key] = tutte_max_db
        if tenuta_temp_tutte_unica_key not in st.session_state:
            st.session_state[tenuta_temp_tutte_unica_key] = tutte_unica_db

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
        condizioni_range_tenuta = []
        temp_nuova_min_txt = ""
        temp_nuova_max_txt = ""
        temp_nuova_unica_txt = ""
        temp_trasformata_min_txt = ""
        temp_trasformata_max_txt = ""
        temp_trasformata_unica_txt = ""
        temp_tutte_min_txt = ""
        temp_tutte_max_txt = ""
        temp_tutte_unica_txt = ""

        if categoria_tenuta:
            st.markdown("#### Dati prodotto")
            c_nome_top, c_marca_top, c_tipo_top = st.columns(3)
            with c_nome_top:
                nome = st.text_input(
                    "Nome prodotto *",
                    key=tenuta_nome_key,
                    placeholder="es. V40 Blue Extra",
                )
            with c_marca_top:
                marca = st.text_input(
                    "Marca",
                    key=tenuta_marca_key,
                    placeholder="es. Swix",
                )
            with c_tipo_top:
                tipo = st.selectbox(
                    "Categoria prodotto",
                    tipi,
                    key=tenuta_tipo_key,
                )

            st.markdown("#### Range temperatura produttore")
            st.caption(
                "Indica a cosa si riferisce la temperatura dichiarata dal produttore e "
                "per quale tipo di neve è valido ciascun intervallo."
            )

            def _mantieni_aperto_dopo_tipo_temp():
                st.session_state[expander_keep_key] = True

            c_ref_range, c_cond_range = st.columns([1, 1.35])
            with c_ref_range:
                riferimento_ui = st.selectbox(
                    "Temperatura riferita a",
                    ["Aria / ambiente", "Neve", "Non specificato"],
                    key=temp_ref_state_key,
                    on_change=_mantieni_aperto_dopo_tipo_temp,
                    help=(
                        "Scegli se il range indicato dal produttore è riferito alla temperatura "
                        "dell'aria/ambiente oppure alla temperatura della neve."
                    ),
                )
                if riferimento_ui == "Aria / ambiente":
                    tipo_temperatura_dinamica = "Aria"
                elif riferimento_ui == "Neve":
                    tipo_temperatura_dinamica = "Neve"
                else:
                    tipo_temperatura_dinamica = "Non specificato"

            with c_cond_range:
                condizioni_range_tenuta = st.multiselect(
                    "Range valido con",
                    ["Neve nuova", "Neve trasformata", "Tutte le tipologie di neve", "Non specificato"],
                    key=tenuta_condizioni_key,
                    placeholder="Seleziona una o più opzioni",
                    help=(
                        "Scegli se il range produttore vale per neve nuova, neve trasformata, "
                        "per tutte le tipologie di neve oppure se il produttore non lo specifica. "
                        "Se selezioni 'Tutte le tipologie di neve' o 'Non specificato', "
                        "inserirai un solo intervallo."
                    ),
                )

            if "Tutte le tipologie di neve" in condizioni_range_tenuta and len(condizioni_range_tenuta) > 1:
                condizioni_range_tenuta = ["Tutte le tipologie di neve"]
                st.session_state[tenuta_condizioni_key] = condizioni_range_tenuta
            if "Non specificato" in condizioni_range_tenuta and len(condizioni_range_tenuta) > 1:
                condizioni_range_tenuta = ["Non specificato"]
                st.session_state[tenuta_condizioni_key] = condizioni_range_tenuta

            mostra_tutte = "Tutte le tipologie di neve" in condizioni_range_tenuta
            mostra_non_specificato = "Non specificato" in condizioni_range_tenuta
            mostra_nuova = ("Neve nuova" in condizioni_range_tenuta) and not mostra_tutte and not mostra_non_specificato
            mostra_trasformata = ("Neve trasformata" in condizioni_range_tenuta) and not mostra_tutte and not mostra_non_specificato

            if mostra_tutte or mostra_non_specificato:
                intestazione_range = "Tutte le tipologie di neve" if mostra_tutte else "Non specificato"
                if mostra_tutte:
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:.45rem;margin:.15rem 0 .55rem 0;">'
                        f'{SNOW_ICON_NEW_SVG}{SNOW_ICON_TRANSFORMED_SVG}<strong>{intestazione_range}</strong>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                tt1, tt2, tt3 = st.columns(3)
                with tt1:
                    temp_tutte_min_txt = st.text_input(
                        "Temperatura minima (°C)",
                        key=tenuta_temp_tutte_min_key,
                        placeholder="-10",
                    )
                with tt2:
                    temp_tutte_max_txt = st.text_input(
                        "Temperatura massima (°C)",
                        key=tenuta_temp_tutte_max_key,
                        placeholder="-2",
                    )
                with tt3:
                    temp_tutte_unica_txt = st.text_input(
                        "Temperatura unica (°C)",
                        key=tenuta_temp_tutte_unica_key,
                        placeholder="0",
                        help="Usa questo campo quando il produttore indica un solo valore di temperatura.",
                    )
            else:
                if mostra_nuova and mostra_trasformata:
                    c_nuova_range, c_trasf_range = st.columns(2)
                elif mostra_nuova:
                    c_nuova_range, c_trasf_range = st.container(), None
                elif mostra_trasformata:
                    c_nuova_range, c_trasf_range = st.container(), None
                else:
                    c_nuova_range = c_trasf_range = None
                    st.info("Seleziona almeno una condizione neve per inserire il relativo range produttore.")

                if mostra_nuova:
                    target_col = c_nuova_range
                    with target_col:
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:.45rem;margin:.15rem 0 .55rem 0;">'
                            f'{SNOW_ICON_NEW_SVG}<strong>Neve nuova</strong>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        n1, n2, n3 = st.columns(3)
                        with n1:
                            temp_nuova_min_txt = st.text_input(
                                "Min neve nuova (°C)",
                                key=tenuta_temp_nuova_min_key,
                                placeholder="-10",
                            )
                        with n2:
                            temp_nuova_max_txt = st.text_input(
                                "Max neve nuova (°C)",
                                key=tenuta_temp_nuova_max_key,
                                placeholder="-2",
                            )
                        with n3:
                            temp_nuova_unica_txt = st.text_input(
                                "Temperatura unica (°C)",
                                key=tenuta_temp_nuova_unica_key,
                                placeholder="0",
                            )

                if mostra_trasformata:
                    target_col = c_trasf_range if mostra_nuova else c_nuova_range
                    with target_col:
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:.45rem;margin:.15rem 0 .55rem 0;">'
                            f'{SNOW_ICON_TRANSFORMED_SVG}<strong>Neve trasformata</strong>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        t1, t2, t3 = st.columns(3)
                        with t1:
                            temp_trasformata_min_txt = st.text_input(
                                "Min neve trasformata (°C)",
                                key=tenuta_temp_trasf_min_key,
                                placeholder="-15",
                            )
                        with t2:
                            temp_trasformata_max_txt = st.text_input(
                                "Max neve trasformata (°C)",
                                key=tenuta_temp_trasf_max_key,
                                placeholder="-5",
                            )
                        with t3:
                            temp_trasformata_unica_txt = st.text_input(
                                "Temperatura unica (°C)",
                                key=tenuta_temp_trasf_unica_key,
                                placeholder="0",
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

                if not categoria_tenuta:
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
                if not categoria_tenuta:
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
                    tipo_temp_opzioni = ["Aria", "Neve", "Range produttore", "Non specificato"]
                    tipo_temp_default = (
                        str(prodotto_edit.get("tipo_temperatura") or "")
                        if modalita_modifica else "Aria"
                    )

                    if categoria_tenuta:
                        tipo_temperatura = tipo_temperatura_dinamica
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
                        for chiave_ui in tenuta_ui_keys:
                            st.session_state.pop(chiave_ui, None)
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
                        if categoria_tenuta:
                            if "Tutte le tipologie di neve" in condizioni_range_tenuta:
                                temp_tutte_unica = _numero_opzionale(temp_tutte_unica_txt)
                                if temp_tutte_unica is not None:
                                    temp_tutte_min = temp_tutte_max = temp_tutte_unica
                                else:
                                    temp_tutte_min = _numero_opzionale(temp_tutte_min_txt)
                                    temp_tutte_max = _numero_opzionale(temp_tutte_max_txt)
                                temp_nuova_min = temp_tutte_min
                                temp_nuova_max = temp_tutte_max
                                temp_trasformata_min = temp_tutte_min
                                temp_trasformata_max = temp_tutte_max
                                temp_min = temp_tutte_min
                                temp_max = temp_tutte_max
                            elif "Non specificato" in condizioni_range_tenuta:
                                temp_tutte_unica = _numero_opzionale(temp_tutte_unica_txt)
                                if temp_tutte_unica is not None:
                                    temp_tutte_min = temp_tutte_max = temp_tutte_unica
                                else:
                                    temp_tutte_min = _numero_opzionale(temp_tutte_min_txt)
                                    temp_tutte_max = _numero_opzionale(temp_tutte_max_txt)
                                temp_min = temp_tutte_min
                                temp_max = temp_tutte_max
                            else:
                                if "Neve nuova" in condizioni_range_tenuta:
                                    temp_nuova_unica = _numero_opzionale(temp_nuova_unica_txt)
                                    if temp_nuova_unica is not None:
                                        temp_nuova_min = temp_nuova_max = temp_nuova_unica
                                    else:
                                        temp_nuova_min = _numero_opzionale(temp_nuova_min_txt)
                                        temp_nuova_max = _numero_opzionale(temp_nuova_max_txt)
                                if "Neve trasformata" in condizioni_range_tenuta:
                                    temp_trasformata_unica = _numero_opzionale(temp_trasformata_unica_txt)
                                    if temp_trasformata_unica is not None:
                                        temp_trasformata_min = temp_trasformata_max = temp_trasformata_unica
                                    else:
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

                    if categoria_tenuta:
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
                                for chiave_ui in tenuta_ui_keys:
                                    st.session_state.pop(chiave_ui, None)
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
                                for chiave_ui in tenuta_ui_keys:
                                    st.session_state.pop(chiave_ui, None)
                            st.success("Prodotto salvato.")
                            st.rerun()

    st.markdown("### Catalogo prodotti")

    df = leggi_df("""
        SELECT
            id, nome, marca, tipo,
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
                    f"usa_temp_produttore_{categoria}",
                    f"temp_produttore_range_catalogo_{categoria}",
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
        filtro_temp_produttore_attivo = False
        filtro_temp_produttore_range = None
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
                            format="%.1f °C",
                            disabled=not filtro_temp_aria_attivo,
                            key=f"temp_aria_range_catalogo_{categoria}",
                        )

                with c_nuova_f:
                    with st.container(key=f"filter_temp_nuova_group_{categoria}"):
                        st.markdown(
                            f'<div class="catalog-temperature-card-title">'
                            f'{SNOW_ICON_NEW_SVG}Neve nuova'
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
                            format="%.1f °C",
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
                            format="%.1f °C",
                            disabled=not filtro_temp_trasformata_attivo,
                            key=f"temp_trasformata_range_catalogo_{categoria}",
                        )

                produttore_min, produttore_max = _limiti_temperatura_per_riferimento("range produttore")
                with st.container(key=f"filter_temp_produttore_group_{categoria}"):
                    st.markdown(
                        '<div class="catalog-temperature-card-title">'
                        'Range produttore'
                        '</div>'
                        '<div class="catalog-temperature-card-subtitle">'
                        'Usa il range dichiarato dal produttore quando non è specificato se si riferisce ad aria o neve.'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    filtro_temp_produttore_attivo = st.toggle(
                        "Attiva filtro range produttore",
                        key=f"usa_temp_produttore_{categoria}",
                    )
                    filtro_temp_produttore_range = st.slider(
                        "Intervallo produttore (°C)",
                        min_value=produttore_min,
                        max_value=produttore_max,
                        value=(produttore_min, produttore_max),
                        step=0.5,
                        format="%.1f °C",
                        disabled=not filtro_temp_produttore_attivo,
                        key=f"temp_produttore_range_catalogo_{categoria}",
                    )
            else:
                aria_min, aria_max = _limiti_temperatura_per_riferimento("aria")
                neve_min, neve_max = _limiti_temperatura_per_riferimento("neve")
                produttore_min, produttore_max = _limiti_temperatura_per_riferimento("range produttore")

                c_aria, c_neve_temp, c_produttore = st.columns(3)

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
                            format="%.1f °C",
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
                            format="%.1f °C",
                            disabled=not filtro_temp_neve_attivo,
                            key=f"temp_neve_range_catalogo_{categoria}",
                        )

                with c_produttore:
                    with st.container(key=f"filter_temp_produttore_group_{categoria}"):
                        st.markdown(
                            '<div class="catalog-temperature-card-title">'
                            'Range produttore'
                            '</div>'
                            '<div class="catalog-temperature-card-subtitle">'
                            'Filtra i prodotti usando il range dichiarato dal produttore.'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        filtro_temp_produttore_attivo = st.toggle(
                            "Attiva range produttore",
                            key=f"usa_temp_produttore_{categoria}",
                        )
                        filtro_temp_produttore_range = st.slider(
                            "Intervallo produttore (°C)",
                            min_value=produttore_min,
                            max_value=produttore_max,
                            value=(produttore_min, produttore_max),
                            step=0.5,
                            format="%.1f °C",
                            disabled=not filtro_temp_produttore_attivo,
                            key=f"temp_produttore_range_catalogo_{categoria}",
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
            or filtro_temp_produttore_attivo
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

            if filtro_temp_produttore_attivo and filtro_temp_produttore_range is not None:
                prod_sel_min, prod_sel_max = filtro_temp_produttore_range
                mask_produttore = (
                    (tipo_temp_prod == "range produttore")
                    & (temp_min_prod.notna() | temp_max_prod.notna())
                    & (temp_min_prod.fillna(float("-inf")) <= float(prod_sel_max))
                    & (temp_max_prod.fillna(float("inf")) >= float(prod_sel_min))
                )
                maschera_temperatura = maschera_temperatura | mask_produttore

            filtrato = filtrato[maschera_temperatura]
        elif (filtro_temp_aria_attivo or filtro_temp_neve_attivo or filtro_temp_produttore_attivo):
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

            if filtro_temp_produttore_attivo and filtro_temp_produttore_range is not None:
                prod_sel_min, prod_sel_max = filtro_temp_produttore_range
                prod_min_eff = temp_min_prod.fillna(float("-inf"))
                prod_max_eff = temp_max_prod.fillna(float("inf"))
                maschera_produttore = (
                    (tipo_temp_prod == "range produttore")
                    & (temp_min_prod.notna() | temp_max_prod.notna())
                    & (prod_min_eff <= float(prod_sel_max))
                    & (prod_max_eff >= float(prod_sel_min))
                )
                maschera_temperatura = maschera_temperatura | maschera_produttore

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

    # Le foto non partecipano ai filtri: vengono recuperate separatamente
    # e restano in RAM di sessione. Questo evita di trascinare decine di
    # stringhe base64 dentro il DataFrame a ogni interazione.
    foto_catalogo = _foto_catalogo_sessione(categoria)
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

                    foto_data = foto_catalogo.get(prodotto_id)

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

                    temp_card_html = ""
                    if usa_condizioni:
                        tipo_temp_card = str(
                            prodotto.get("tipo_temperatura") or ""
                        ).strip().lower()
                        if tipo_temp_card == "aria":
                            riferimento_temp = "ad aria/ambiente"
                        elif tipo_temp_card == "neve":
                            riferimento_temp = "a neve"
                        elif tipo_temp_card == "range produttore":
                            riferimento_temp = "al range produttore"
                        else:
                            riferimento_temp = ""

                        righe_temperatura = []

                        if categoria_tenuta:
                            righe_temperatura.append(
                                '<div class="catalog-temp-block-title">Range temperatura produttore</div>'
                            )
                            if riferimento_temp:
                                righe_temperatura.append(
                                    f'<div class="catalog-temp-reference">Riferito {html_escape(riferimento_temp)}</div>'
                                )

                            testo_nuova = _testo_range(
                                prodotto.get("temp_nuova_min"),
                                prodotto.get("temp_nuova_max"),
                                "°C",
                            )
                            testo_trasf = _testo_range(
                                prodotto.get("temp_trasformata_min"),
                                prodotto.get("temp_trasformata_max"),
                                "°C",
                            )

                            if (
                                testo_nuova != "—"
                                and testo_trasf != "—"
                                and testo_nuova == testo_trasf
                            ):
                                righe_temperatura.append(
                                    f'<div class="catalog-temperature-line">'
                                    f'<span class="catalog-temperature-icon">{SNOW_ICON_NEW_SVG}{SNOW_ICON_TRANSFORMED_SVG}</span>'
                                    f'<span class="catalog-temperature-text">'
                                    f'<span class="catalog-temperature-label">Con tutte le tipologie di neve:</span> '
                                    f'{html_escape(testo_nuova)}'
                                    f'</span></div>'
                                )
                            else:
                                if testo_nuova != "—":
                                    righe_temperatura.append(
                                        f'<div class="catalog-temperature-line">'
                                        f'<span class="catalog-temperature-icon">{SNOW_ICON_NEW_SVG}</span>'
                                        f'<span class="catalog-temperature-text">'
                                        f'<span class="catalog-temperature-label">Con neve nuova:</span> '
                                        f'{html_escape(testo_nuova)}'
                                        f'</span></div>'
                                    )
                                if testo_trasf != "—":
                                    righe_temperatura.append(
                                        f'<div class="catalog-temperature-line">'
                                        f'<span class="catalog-temperature-icon">{SNOW_ICON_TRANSFORMED_SVG}</span>'
                                        f'<span class="catalog-temperature-text">'
                                        f'<span class="catalog-temperature-label">Con neve trasformata:</span> '
                                        f'{html_escape(testo_trasf)}'
                                        f'</span></div>'
                                    )

                            if testo_nuova == "—" and testo_trasf == "—":
                                temp_txt = _testo_range(
                                    prodotto.get("temp_min"),
                                    prodotto.get("temp_max"),
                                    "°C",
                                )
                                if temp_txt != "—":
                                    righe_temperatura.append(
                                        f'<div class="catalog-temperature-line">'
                                        f'<span class="catalog-temperature-text">{html_escape(temp_txt)}</span>'
                                        f'</div>'
                                    )
                        else:
                            temp_txt = _testo_range(
                                prodotto.get("temp_min"),
                                prodotto.get("temp_max"),
                                "°C",
                            )
                            if temp_txt != "—":
                                righe_temperatura.append(
                                    f'<div class="catalog-temperature-line">'
                                    f'<span class="catalog-temperature-text">'
                                    f'<span class="catalog-temperature-label">Temperatura:</span> '
                                    f'{html_escape(temp_txt)} · {html_escape(riferimento_temp)}'
                                    f'</span></div>'
                                )

                        temp_card_html = "".join(righe_temperatura)

                    st.markdown(
                        f'<div class="catalog-card-temperature-slot">{temp_card_html}</div>',
                        unsafe_allow_html=True,
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
                                riferimento_temp_scheda = "ad aria/ambiente"
                            elif tipo_temp_scheda == "neve":
                                riferimento_temp_scheda = "a neve"
                            elif tipo_temp_scheda == "range produttore":
                                riferimento_temp_scheda = "al range produttore"
                            else:
                                riferimento_temp_scheda = ""

                            if categoria_tenuta:
                                # Il range temperatura produttore è già visibile nella card.
                                # Evitiamo di duplicarlo nella Scheda completa.
                                pass
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



def _stile_moduli_test():
    st.markdown(
        """
        <style>
        .insert-test-panel {
            background:#ffffff;
            border:1px solid #d8dde3;
            border-radius:14px;
            padding:1.15rem 1.25rem;
            margin:0.7rem 0 1rem 0;
            box-shadow:0 2px 10px rgba(15,23,42,.04);
        }
        .insert-test-title {
            font-size:1.15rem;
            font-weight:700;
            color:#1f2933;
            margin-bottom:.2rem;
        }
        .insert-test-caption {
            color:#7a8a96;
            font-size:.92rem;
            margin-bottom:.85rem;
        }
        .insert-test-divider {
            border-top:1px solid #e3e7eb;
            margin:1.15rem 0 1rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_form_test_scorrimento():
    snow_options_scroll = {
        "Origine": ["Naturale", "Artificiale", "Mista"],
        "Consistenza": [
            "Compatta", "Sfarinata / Soffice", "Sgranata", "Ghiacciata",
            "Molle su fondo compatto", "Soffice su fondo compatto", "Molle",
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

    edit_scroll_session_id = st.session_state.get("scroll_edit_session_id")
    edit_scroll_row = None
    needs_scroll_edit_load = False
    if edit_scroll_session_id is not None:
        df_edit_scroll = leggi_df(
            """
            SELECT id, data, ora, luogo, temperatura_aria, temperatura_neve,
                   umidita, meteo, snow_origine, snow_consistenza, snow_umidita,
                   snow_forma_grano, snow_granulometria, snow_caratteristiche,
                   zero_modello_sci, tipo_test, categoria_test_scorrimento, zero_riferimento_id
            FROM sessioni
            WHERE id = ?
            """,
            (int(edit_scroll_session_id),),
        )
        if not df_edit_scroll.empty:
            edit_scroll_row = df_edit_scroll.iloc[0]
            needs_scroll_edit_load = (
                st.session_state.get("scroll_edit_loaded_id") != int(edit_scroll_session_id)
            )
        else:
            st.session_state.pop("scroll_edit_session_id", None)
            st.session_state.pop("scroll_edit_loaded_id", None)
            edit_scroll_session_id = None

    if needs_scroll_edit_load and edit_scroll_row is not None:
        metodo_edit = str(edit_scroll_row.get("tipo_test") or "Asta").replace("Test prodotti scorrimento · ", "").strip()
        st.session_state["scroll_test_method"] = metodo_edit if metodo_edit in ["Asta", "Parallel", "Fotocellula"] else "Asta"
        tipo_prodotti_edit = str(edit_scroll_row.get("categoria_test_scorrimento") or "").strip()
        tipologie_prodotti_valide = [
            "Test liquidi", "Test top coating", "Test paraffine", "Test basi", "Test combinazioni"
        ]
        st.session_state["scroll_product_test_type"] = (
            tipo_prodotti_edit if tipo_prodotti_edit in tipologie_prodotti_valide else "Test combinazioni"
        )
        try:
            st.session_state["scroll_date"] = pd.to_datetime(edit_scroll_row.get("data")).date()
        except Exception:
            st.session_state["scroll_date"] = date.today()
        try:
            st.session_state["scroll_time"] = datetime.strptime(str(edit_scroll_row.get("ora") or "00:00")[:5], "%H:%M").time()
        except Exception:
            st.session_state["scroll_time"] = datetime.now().time().replace(second=0, microsecond=0)
        st.session_state["scroll_place"] = str(edit_scroll_row.get("luogo") or "")
        st.session_state["scroll_air"] = _formatta_temperatura_1d(edit_scroll_row.get("temperatura_aria"))
        st.session_state["scroll_snow"] = _formatta_temperatura_1d(edit_scroll_row.get("temperatura_neve"))
        ur_edit = edit_scroll_row.get("umidita")
        st.session_state["scroll_rh_missing"] = bool(pd.isna(ur_edit))
        st.session_state["scroll_rh"] = 70 if pd.isna(ur_edit) else int(round(float(ur_edit)))
        st.session_state["scroll_ski_model"] = str(edit_scroll_row.get("zero_modello_sci") or "")
        meteo_edit = str(edit_scroll_row.get("meteo") or "").strip()
        st.session_state["scroll_weather"] = meteo_edit if meteo_edit in METEO_OPZIONI else None
        st.session_state["scroll_origin"] = _valori_sessione_neve(edit_scroll_row.get("snow_origine"), snow_options_scroll["Origine"])
        st.session_state["scroll_consistency"] = _valori_sessione_neve(edit_scroll_row.get("snow_consistenza"), snow_options_scroll["Consistenza"])
        st.session_state["scroll_snow_humidity"] = _valori_sessione_neve(edit_scroll_row.get("snow_umidita"), snow_options_scroll["Umidità neve"])
        st.session_state["scroll_grain"] = _valori_sessione_neve(edit_scroll_row.get("snow_forma_grano"), snow_options_scroll["Forma grano"])
        st.session_state["scroll_size"] = _valori_sessione_neve(edit_scroll_row.get("snow_granulometria"), snow_options_scroll["Granulometria"])
        st.session_state["scroll_features"] = _valori_sessione_neve(edit_scroll_row.get("snow_caratteristiche"), snow_options_scroll["Caratteristiche"])
        df_edit_count = leggi_df(
            "SELECT COUNT(*) AS n FROM test_scorrimento_aste WHERE sessione_id = ?",
            (int(edit_scroll_session_id),),
        )
        n_edit = int(df_edit_count.iloc[0]["n"] or 1) if not df_edit_count.empty else 1
        st.session_state["scroll_num_rods"] = max(1, n_edit)

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="insert-test-title">Test prodotti scorrimento</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="insert-test-caption">Imposta prima il tipo di test e registra le condizioni reali della sessione. Lo Zero Test di riferimento resta esclusivamente un collegamento informativo.</div>',
        unsafe_allow_html=True,
    )

    if edit_scroll_session_id is not None:
        ce1, ce2 = st.columns([4, 1.25])
        with ce1:
            st.info("Modalità modifica attiva: stai aggiornando un test prodotti scorrimento già presente nello storico.")
        with ce2:
            if st.button("Annulla modifica", use_container_width=True, key="cancel_scroll_edit"):
                st.session_state.pop("scroll_edit_session_id", None)
                st.session_state.pop("scroll_edit_loaded_id", None)
                for k in [
                    "scroll_rods_table_data", "scroll_rods_table_n",
                    "scroll_product_columns", "scroll_product_test_type"
                ]:
                    st.session_state.pop(k, None)
                st.rerun()

    # 1. TIPO DI TEST + ZERO TEST DI RIFERIMENTO
    st.markdown("#### Impostazione test")
    c_tipo_scroll, c_zero_ref = st.columns([1, 1.6])
    with c_tipo_scroll:
        metodo_scroll = st.selectbox(
            "Metodo test",
            ["Asta", "Parallel", "Fotocellula"],
            key="scroll_test_method",
            help="Seleziona il metodo con cui hai effettuato il test prodotti.",
        )

    df_zero_ref = leggi_df("""
        SELECT
            s.id,
            s.data,
            s.ora,
            s.luogo,
            s.zero_batteria,
            s.zero_modello_sci
        FROM sessioni s
        JOIN zero_test z ON z.sessione_id = s.id
        WHERE COALESCE(s.zero_batteria, '') = 'Batteria prodotti scorrimento'
        GROUP BY s.id
        ORDER BY s.data DESC, COALESCE(s.ora, '') DESC, s.id DESC
    """)

    zero_ref_labels = ["Nessuno"]
    zero_ref_map = {"Nessuno": None}
    for _, ref in df_zero_ref.iterrows():
        data_ref = str(ref.get("data") or "").strip()
        luogo_ref = str(ref.get("luogo") or "").strip() or "—"
        modello_ref = str(ref.get("zero_modello_sci") or "").strip()
        label = f"{data_ref} · {luogo_ref}"
        if modello_ref:
            label += f" · {modello_ref}"
        zero_ref_labels.append(label)
        zero_ref_map[label] = int(ref["id"])

    if needs_scroll_edit_load and edit_scroll_row is not None:
        ref_id_edit = edit_scroll_row.get("zero_riferimento_id")
        ref_label_edit = "Nessuno"
        if ref_id_edit is not None and not pd.isna(ref_id_edit):
            for lbl_ref, id_ref in zero_ref_map.items():
                if id_ref == int(ref_id_edit):
                    ref_label_edit = lbl_ref
                    break
        st.session_state["insert_scroll_zero_reference"] = ref_label_edit

    with c_zero_ref:
        zero_ref_label = st.selectbox(
            "Zero Test di riferimento",
            zero_ref_labels,
            key="insert_scroll_zero_reference",
            help=(
                "Solo riferimento informativo. La selezione non precompila i dati, "
                "non modifica i risultati e non attribuisce alcun vantaggio ai prodotti."
            ),
        )
    zero_ref_id = zero_ref_map.get(zero_ref_label)

    if zero_ref_id is not None:
        st.markdown(
            f'<div class="catalog-edit-notice"><strong>Zero Test collegato:</strong> {html_escape(zero_ref_label)}<br>'
            '<span style="color:#7a8a96">Riferimento esclusivamente informativo: i dati e i risultati del test prodotti restano indipendenti.</span></div>',
            unsafe_allow_html=True,
        )

    # 2. DATI SESSIONE - INDIPENDENTI DALLO ZERO TEST
    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### Dati sessione")
    st.caption("Inserisci le condizioni effettive rilevate durante il test prodotti.")

    c1, c2, c3 = st.columns(3)
    with c1:
        scroll_data = st.date_input("Data", value=date.today(), key="scroll_date")
        scroll_luogo = st.text_input("Luogo *", key="scroll_place", placeholder="es. Davos (SUI)")
    with c2:
        scroll_ora = st.time_input(
            "Ora",
            value=datetime.now().time().replace(second=0, microsecond=0),
            key="scroll_time",
        )
        scroll_taria_txt = st.text_input(
            "Temperatura aria (°C)",
            value="0.0",
            key="scroll_air",
            help="Usa il punto come separatore decimale, es. -3.0",
        )
    with c3:
        scroll_tneve_txt = st.text_input(
            "Temperatura neve (°C)",
            value="0.0",
            key="scroll_snow",
            help="Usa il punto come separatore decimale, es. -1.5",
        )
        if "scroll_rh_missing" not in st.session_state:
            st.session_state["scroll_rh_missing"] = False
        scroll_ur = st.number_input(
            "Umidità relativa (%)",
            min_value=0,
            max_value=100,
            value=70,
            step=1,
            format="%d",
            disabled=bool(st.session_state.get("scroll_rh_missing", False)),
            key="scroll_rh",
        )
        scroll_ur_missing = st.checkbox(
            "Umidità non disponibile",
            key="scroll_rh_missing",
        )

    c4, c5 = st.columns(2)
    with c4:
        scroll_modello_sci = st.text_input(
            "Modello sci",
            key="scroll_ski_model",
            placeholder="es. Speedmax 3D",
        )
    with c5:
        scroll_meteo = st.selectbox(
            "Meteo",
            METEO_OPZIONI,
            index=None,
            placeholder="Seleziona meteo",
            key="scroll_weather",
        )

    # 3. CLASSIFICAZIONE NEVE - STESSO SISTEMA DELLO ZERO TEST
    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### Classificazione neve")
    st.caption("Usa la stessa classificazione indipendente adottata nello Zero Test e nel catalogo scioline.")

    s1, s2, s3 = st.columns(3)
    with s1:
        scroll_origine = st.multiselect(
            "Origine", snow_options_scroll["Origine"], key="scroll_origin"
        )
    with s2:
        scroll_consistenza = st.multiselect(
            "Consistenza", snow_options_scroll["Consistenza"], key="scroll_consistency"
        )
    with s3:
        scroll_umidita_neve = st.multiselect(
            "Umidità neve", snow_options_scroll["Umidità neve"], key="scroll_snow_humidity"
        )

    s4, s5, s6 = st.columns(3)
    with s4:
        scroll_forma = st.multiselect(
            "Forma grano", snow_options_scroll["Forma grano"], key="scroll_grain"
        )
    with s5:
        scroll_granulometria = st.multiselect(
            "Granulometria", snow_options_scroll["Granulometria"], key="scroll_size"
        )
    with s6:
        scroll_caratteristiche = st.multiselect(
            "Caratteristiche", snow_options_scroll["Caratteristiche"], key="scroll_features"
        )

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### Prodotti testati")

    if metodo_scroll == "Asta":
        st.caption(
            "Imposta il numero di aste e compila una riga per ogni posizione. "
            "I prodotti sono selezionati direttamente dal catalogo SnowDataPro."
        )

        tipologie_prodotti_test = [
            "Test liquidi",
            "Test top coating",
            "Test paraffine",
            "Test basi",
            "Test combinazioni",
        ]
        if "scroll_product_test_type" not in st.session_state:
            st.session_state["scroll_product_test_type"] = "Test combinazioni"
        tipologia_prodotti_testati = st.selectbox(
            "Tipologia prodotti testati",
            tipologie_prodotti_test,
            key="scroll_product_test_type",
            help=(
                "Indica quali prodotti stai realmente confrontando. La preparazione completa dello sci "
                "può comunque contenere altre colonne uguali per tutti. Sul podio verranno mostrati "
                "solo i prodotti della tipologia scelta."
            ),
        )
        focus_to_column = {
            "Test liquidi": "Liquido",
            "Test top coating": "Top coating",
            "Test paraffine": "Paraffina",
            "Test basi": "Base",
            "Test combinazioni": None,
        }
        colonna_focus_test = focus_to_column.get(tipologia_prodotti_testati)
        if colonna_focus_test:
            st.caption(
                f"Confronto principale: **{colonna_focus_test}**. Le altre colonne servono a descrivere "
                "la preparazione completa dello sci e non verranno mostrate sul podio."
            )
        else:
            st.caption(
                "Confronto combinazioni: sul podio verrà mostrata l'intera preparazione prodotto dello sci."
            )

        numero_aste = st.number_input(
            "Numero di aste",
            min_value=1,
            max_value=30,
            value=10,
            step=1,
            format="%d",
            key="scroll_num_rods",
            help="Definisce il numero di posizioni/righe da compilare nel test ad asta.",
        )

        colonne_prodotto_disponibili = ["Base", "Paraffina", "Top coating", "Liquido"]

        # Quando si apre un test in modifica, mostra automaticamente soltanto le
        # colonne prodotto realmente utilizzate in quel test. Se non è possibile
        # ricavarle, mantiene la configurazione completa tradizionale.
        if needs_scroll_edit_load and edit_scroll_session_id is not None:
            df_colonne_usate = leggi_df(
                """
                SELECT base_prodotto_id, paraffina_prodotto_id,
                       top_coating_prodotto_id, liquido_prodotto_id
                FROM test_scorrimento_aste
                WHERE sessione_id = ?
                """,
                (int(edit_scroll_session_id),),
            )
            mappa_colonne_db = {
                "Base": "base_prodotto_id",
                "Paraffina": "paraffina_prodotto_id",
                "Top coating": "top_coating_prodotto_id",
                "Liquido": "liquido_prodotto_id",
            }
            colonne_rilevate = []
            if not df_colonne_usate.empty:
                for nome_colonna, col_db in mappa_colonne_db.items():
                    if col_db in df_colonne_usate.columns and df_colonne_usate[col_db].notna().any():
                        colonne_rilevate.append(nome_colonna)
            st.session_state["scroll_product_columns"] = (
                colonne_rilevate or colonne_prodotto_disponibili.copy()
            )

        if "scroll_product_columns" not in st.session_state:
            st.session_state["scroll_product_columns"] = colonne_prodotto_disponibili.copy()

        colonne_prodotto_selezionate = st.multiselect(
            "Colonne della preparazione da inserire",
            colonne_prodotto_disponibili,
            key="scroll_product_columns",
            help=(
                "Scegli quante e quali colonne compongono lo sci durante il test. "
                "Esempio: per un Test liquidi puoi usare due colonne, 'Top coating' uguale per tutti "
                "e 'Liquido' diverso per ogni sci."
            ),
        )
        # Mantiene sempre l'ordine logico delle colonne, indipendentemente
        # dall'ordine con cui vengono selezionate nel multiselect.
        colonne_prodotto_attive = [
            col for col in colonne_prodotto_disponibili
            if col in colonne_prodotto_selezionate
        ]
        st.caption(
            f"Colonne prodotto visualizzate: {len(colonne_prodotto_attive)}"
            + (
                " · " + " · ".join(colonne_prodotto_attive)
                if colonne_prodotto_attive else " · nessuna selezionata"
            )
        )

        df_catalogo_scroll = leggi_df("""
            SELECT id, nome, marca, tipo
            FROM catalogo_prodotti
            WHERE categoria = 'scorrimento'
            ORDER BY COALESCE(marca, ''), nome
        """)

        def _etichette_prodotti_scroll():
            # In ogni colonna (Base, Paraffina, Top coating, Liquido) è possibile
            # scegliere qualsiasi prodotto del catalogo di scorrimento. Le colonne
            # descrivono infatti il ruolo/strato usato nel test, non la categoria
            # commerciale assegnata al prodotto nel catalogo.
            if df_catalogo_scroll.empty:
                return ["—"]
            etichette = ["—"]
            for _, prodotto in df_catalogo_scroll.iterrows():
                marca = str(prodotto.get("marca") or "").strip()
                nome = str(prodotto.get("nome") or "").strip()
                label = f"{marca} - {nome}" if marca else nome
                if label and label not in etichette:
                    etichette.append(label)
            return etichette

        opzioni_tutti_prodotti = _etichette_prodotti_scroll()
        prodotto_id_da_label = {"—": None}
        if not df_catalogo_scroll.empty:
            for _, prodotto in df_catalogo_scroll.iterrows():
                marca = str(prodotto.get("marca") or "").strip()
                nome = str(prodotto.get("nome") or "").strip()
                label = f"{marca} - {nome}" if marca else nome
                if label and label not in prodotto_id_da_label:
                    prodotto_id_da_label[label] = int(prodotto["id"])

        n_aste = int(numero_aste)

        if needs_scroll_edit_load and edit_scroll_session_id is not None:
            df_edit_aste = leggi_df(
                """
                SELECT a.posizione, a.numero_sci,
                       COALESCE(pb.marca || ' - ' || pb.nome, pb.nome, '—') AS base,
                       COALESCE(pp.marca || ' - ' || pp.nome, pp.nome, '—') AS paraffina,
                       COALESCE(pt.marca || ' - ' || pt.nome, pt.nome, '—') AS top_coating,
                       COALESCE(pl.marca || ' - ' || pl.nome, pl.nome, '—') AS liquido,
                       a.note
                FROM test_scorrimento_aste a
                LEFT JOIN catalogo_prodotti pb ON pb.id = a.base_prodotto_id
                LEFT JOIN catalogo_prodotti pp ON pp.id = a.paraffina_prodotto_id
                LEFT JOIN catalogo_prodotti pt ON pt.id = a.top_coating_prodotto_id
                LEFT JOIN catalogo_prodotti pl ON pl.id = a.liquido_prodotto_id
                WHERE a.sessione_id = ?
                ORDER BY a.id
                """,
                (int(edit_scroll_session_id),),
            )
            righe_edit = []
            for idx_edit, r_edit in df_edit_aste.reset_index(drop=True).iterrows():
                righe_edit.append({
                    "_ordine_inserimento": idx_edit,
                    "Posizione": None if pd.isna(r_edit.get("posizione")) else int(r_edit.get("posizione")),
                    "Numero sci": str(r_edit.get("numero_sci") or ""),
                    "Base": str(r_edit.get("base") or "—"),
                    "Paraffina": str(r_edit.get("paraffina") or "—"),
                    "Top coating": str(r_edit.get("top_coating") or "—"),
                    "Liquido": str(r_edit.get("liquido") or "—"),
                    "Note": str(r_edit.get("note") or ""),
                })
            if righe_edit:
                st.session_state["scroll_rods_table_data"] = pd.DataFrame(righe_edit)
                st.session_state["scroll_rods_table_n"] = len(righe_edit)
                st.session_state["scroll_rods_table_version"] = st.session_state.get("scroll_rods_table_version", 0) + 1
            st.session_state["scroll_edit_loaded_id"] = int(edit_scroll_session_id)

        def _tabella_aste_vuota(n):
            return pd.DataFrame({
                "_ordine_inserimento": list(range(n)),
                "Posizione": [None] * n,
                "Numero sci": [""] * n,
                "Base": ["—"] * n,
                "Paraffina": ["—"] * n,
                "Top coating": ["—"] * n,
                "Liquido": ["—"] * n,
                "Note": [""] * n,
            })

        stato_tabella_key = "scroll_rods_table_data"
        stato_n_key = "scroll_rods_table_n"
        versione_key = "scroll_rods_table_version"

        if versione_key not in st.session_state:
            st.session_state[versione_key] = 0

        # Se cambia il numero di aste, preserva quanto già inserito nelle righe esistenti.
        if (
            stato_tabella_key not in st.session_state
            or st.session_state.get(stato_n_key) != n_aste
        ):
            nuova_tabella = _tabella_aste_vuota(n_aste)
            precedente = st.session_state.get(stato_tabella_key)
            if isinstance(precedente, pd.DataFrame) and not precedente.empty:
                precedente = precedente.copy().reset_index(drop=True)
                # Se cambia il numero di aste, conserva le righe già compilate
                # seguendo l'ordine originario di inserimento, non il nome dello sci.
                if "_ordine_inserimento" in precedente.columns:
                    precedente = precedente.sort_values("_ordine_inserimento", kind="stable").reset_index(drop=True)
                righe_da_copiare = min(len(precedente), n_aste)
                for idx in range(righe_da_copiare):
                    for col in ["Posizione", "Numero sci", "Base", "Paraffina", "Top coating", "Liquido", "Note"]:
                        if col in precedente.columns:
                            nuova_tabella.at[idx, col] = precedente.at[idx, col]
            st.session_state[stato_tabella_key] = nuova_tabella
            st.session_state[stato_n_key] = n_aste
            st.session_state[versione_key] += 1

        df_aste = st.session_state[stato_tabella_key].copy()

        # Le colonne non selezionate vengono realmente escluse dal test corrente:
        # non compaiono nell'editor e vengono azzerate, così non restano prodotti
        # nascosti salvati per errore quando si passa, ad esempio, a "solo Liquido".
        for colonna_prodotto in colonne_prodotto_disponibili:
            if colonna_prodotto not in colonne_prodotto_attive:
                df_aste[colonna_prodotto] = "—"

        colonne_editor = [
            "_ordine_inserimento", "Posizione", "Numero sci",
            *colonne_prodotto_attive,
            "Note",
        ]
        df_aste_visibile = df_aste[colonne_editor].copy()

        config_editor = {
            "_ordine_inserimento": None,
            "Posizione": st.column_config.NumberColumn(
                "Posizione",
                min_value=1,
                max_value=n_aste,
                step=1,
                format="%d",
                width="small",
                help="Inserisci la posizione ottenuta nel test. Puoi poi riordinare la tabella per classifica.",
            ),
            "Numero sci": st.column_config.TextColumn(
                "Numero sci",
                width="small",
                help="Inserisci liberamente il codice dello sci, ad esempio 1A, 1B, 3A, 3B.",
            ),
            "Note": st.column_config.TextColumn("Note", width="large"),
        }
        for colonna_prodotto in colonne_prodotto_attive:
            config_editor[colonna_prodotto] = st.column_config.SelectboxColumn(
                colonna_prodotto,
                options=opzioni_tutti_prodotti,
                width="medium",
                required=False,
            )

        firma_colonne = "_".join(
            col.lower().replace(" ", "_") for col in colonne_prodotto_attive
        ) or "nessuna"
        tabella_editata_visibile = st.data_editor(
            df_aste_visibile,
            key=f"scroll_rods_editor_{n_aste}_{firma_colonne}_{st.session_state[versione_key]}",
            hide_index=True,
            use_container_width=True,
            height=min(650, 38 + n_aste * 36),
            column_config=config_editor,
        )

        # Ricompone lo stato completo richiesto dal database mantenendo invisibili
        # le colonne non utilizzate.
        tabella_editata = df_aste.copy()
        for col in tabella_editata_visibile.columns:
            tabella_editata[col] = tabella_editata_visibile[col].values
        for colonna_prodotto in colonne_prodotto_disponibili:
            if colonna_prodotto not in colonne_prodotto_attive:
                tabella_editata[colonna_prodotto] = "—"
        st.session_state[stato_tabella_key] = tabella_editata.copy()

        c_ordina, c_reset, c_spazio = st.columns([1.4, 1.4, 4])
        with c_ordina:
            if st.button("↕ Riordina per classifica", use_container_width=True, key="scroll_sort_by_rank"):
                tab = st.session_state[stato_tabella_key].copy()
                # Le posizioni mancanti rimangono in fondo; le altre vengono ordinate 1,2,3...
                tab["_pos_sort"] = pd.to_numeric(tab["Posizione"], errors="coerce")
                tab = tab.sort_values(
                    by=["_pos_sort", "_ordine_inserimento"],
                    na_position="last",
                    kind="stable",
                ).drop(columns=["_pos_sort"]).reset_index(drop=True)
                st.session_state[stato_tabella_key] = tab
                st.session_state[versione_key] += 1
                st.rerun()

        with c_reset:
            if st.button("↺ Ripristina ordine inserimento", use_container_width=True, key="scroll_reset_ski_order"):
                tab = st.session_state[stato_tabella_key].copy()
                tab = tab.sort_values("_ordine_inserimento", kind="stable").reset_index(drop=True)
                st.session_state[stato_tabella_key] = tab
                st.session_state[versione_key] += 1
                st.rerun()

        st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
        salva_scroll = st.button(
            "Salva modifiche test" if edit_scroll_session_id is not None else "Salva test prodotti scorrimento",
            type="primary",
            use_container_width=True,
            key="save_scroll_rod_test",
        )

        if salva_scroll:
            if not colonne_prodotto_attive:
                st.error("Seleziona almeno una colonna prodotto da usare nel test.")
            elif colonna_focus_test and colonna_focus_test not in colonne_prodotto_attive:
                st.error(
                    f"Hai selezionato '{tipologia_prodotti_testati}': aggiungi la colonna "
                    f"'{colonna_focus_test}' alla preparazione del test."
                )
            elif not str(scroll_luogo or "").strip():
                st.error("Inserisci il luogo del test.")
            else:
                try:
                    temp_aria_val = _parse_temperatura_1d(scroll_taria_txt)
                    temp_neve_val = _parse_temperatura_1d(scroll_tneve_txt)
                except Exception:
                    st.error("Controlla temperatura aria e temperatura neve. Usa valori come -3.0 o 0.0.")
                    return

                tab_da_salvare = st.session_state[stato_tabella_key].copy()
                righe_asta = []
                for _, riga in tab_da_salvare.iterrows():
                    numero_sci = str(riga.get("Numero sci") or "").strip()
                    base_label = str(riga.get("Base") or "—").strip()
                    paraffina_label = str(riga.get("Paraffina") or "—").strip()
                    top_label = str(riga.get("Top coating") or "—").strip()
                    liquido_label = str(riga.get("Liquido") or "—").strip()
                    note_riga = str(riga.get("Note") or "").strip()

                    posizione_raw = riga.get("Posizione")
                    posizione = None
                    if posizione_raw is not None and not pd.isna(posizione_raw) and str(posizione_raw).strip():
                        posizione = int(float(posizione_raw))

                    # Salva solo righe realmente compilate. La posizione può essere aggiunta anche dopo.
                    if not numero_sci and all(
                        x in ("", "—", "None")
                        for x in [base_label, paraffina_label, top_label, liquido_label]
                    ) and not note_riga:
                        continue

                    righe_asta.append({
                        "posizione": posizione,
                        "numero_sci": numero_sci,
                        "base_id": prodotto_id_da_label.get(base_label),
                        "paraffina_id": prodotto_id_da_label.get(paraffina_label),
                        "top_id": prodotto_id_da_label.get(top_label),
                        "liquido_id": prodotto_id_da_label.get(liquido_label),
                        "note": note_riga,
                    })

                if not righe_asta:
                    st.error("Compila almeno una riga della tabella prima di salvare il test.")
                else:
                    conn = apri_connessione_database()
                    try:
                        if edit_scroll_session_id is not None:
                            sessione_scroll_id = int(edit_scroll_session_id)
                            conn.execute(
                                """
                                UPDATE sessioni
                                SET data = ?, ora = ?, luogo = ?, temperatura_aria = ?, temperatura_neve = ?,
                                    umidita = ?, meteo = ?,
                                    snow_origine = ?, snow_consistenza = ?, snow_umidita = ?,
                                    snow_forma_grano = ?, snow_granulometria = ?, snow_caratteristiche = ?,
                                    zero_modello_sci = ?, tipo_test = ?, categoria_test_scorrimento = ?, zero_riferimento_id = ?
                                WHERE id = ?
                                """,
                                (
                                    scroll_data.isoformat(),
                                    scroll_ora.strftime("%H:%M"),
                                    str(scroll_luogo).strip(),
                                    temp_aria_val,
                                    temp_neve_val,
                                    None if scroll_ur_missing else int(scroll_ur),
                                    scroll_meteo or "",
                                    _compatta_neve_sessione(scroll_origine, snow_options_scroll["Origine"]),
                                    _compatta_neve_sessione(scroll_consistenza, snow_options_scroll["Consistenza"]),
                                    _compatta_neve_sessione(scroll_umidita_neve, snow_options_scroll["Umidità neve"]),
                                    _compatta_neve_sessione(scroll_forma, snow_options_scroll["Forma grano"]),
                                    _compatta_neve_sessione(scroll_granulometria, snow_options_scroll["Granulometria"]),
                                    _compatta_neve_sessione(scroll_caratteristiche, snow_options_scroll["Caratteristiche"]),
                                    str(scroll_modello_sci or "").strip(),
                                    f"Test prodotti scorrimento · {metodo_scroll}",
                                    tipologia_prodotti_testati,
                                    int(zero_ref_id) if zero_ref_id is not None else None,
                                    sessione_scroll_id,
                                ),
                            )
                            conn.execute("DELETE FROM test_scorrimento_aste WHERE sessione_id = ?", (sessione_scroll_id,))
                        else:
                            cur = conn.execute(
                                """
                                INSERT INTO sessioni (
                                    data, ora, luogo, temperatura_aria, temperatura_neve,
                                    umidita, meteo, tipo_neve, condizione_pista,
                                    snow_origine, snow_consistenza, snow_umidita,
                                    snow_forma_grano, snow_granulometria, snow_caratteristiche,
                                    zero_modello_sci, tipo_test, categoria_test_scorrimento, zero_riferimento_id, note, creato_il
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?)
                                """,
                                (
                                    scroll_data.isoformat(),
                                    scroll_ora.strftime("%H:%M"),
                                    str(scroll_luogo).strip(),
                                    temp_aria_val,
                                    temp_neve_val,
                                    None if scroll_ur_missing else int(scroll_ur),
                                    scroll_meteo or "",
                                    _compatta_neve_sessione(scroll_origine, snow_options_scroll["Origine"]),
                                    _compatta_neve_sessione(scroll_consistenza, snow_options_scroll["Consistenza"]),
                                    _compatta_neve_sessione(scroll_umidita_neve, snow_options_scroll["Umidità neve"]),
                                    _compatta_neve_sessione(scroll_forma, snow_options_scroll["Forma grano"]),
                                    _compatta_neve_sessione(scroll_granulometria, snow_options_scroll["Granulometria"]),
                                    _compatta_neve_sessione(scroll_caratteristiche, snow_options_scroll["Caratteristiche"]),
                                    str(scroll_modello_sci or "").strip(),
                                    f"Test prodotti scorrimento · {metodo_scroll}",
                                    tipologia_prodotti_testati,
                                    int(zero_ref_id) if zero_ref_id is not None else None,
                                    datetime.now().isoformat(timespec="seconds"),
                                ),
                            )
                            sessione_scroll_id = int(cur.lastrowid)

                        for riga in righe_asta:
                            conn.execute(
                                """
                                INSERT INTO test_scorrimento_aste (
                                    sessione_id, posizione, numero_sci,
                                    base_prodotto_id, paraffina_prodotto_id,
                                    top_coating_prodotto_id, liquido_prodotto_id,
                                    note, creato_il
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    sessione_scroll_id,
                                    riga["posizione"],
                                    riga["numero_sci"],
                                    riga["base_id"],
                                    riga["paraffina_id"],
                                    riga["top_id"],
                                    riga["liquido_id"],
                                    riga["note"],
                                    datetime.now().isoformat(timespec="seconds"),
                                ),
                            )
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
                    finally:
                        conn.close()
                    _invalida_cache_dati()
                    if edit_scroll_session_id is not None:
                        st.session_state["scroll_history_notice"] = f"Test prodotti scorrimento aggiornato correttamente · {len(righe_asta)} righe registrate."
                        st.session_state.pop("scroll_edit_session_id", None)
                        st.session_state.pop("scroll_edit_loaded_id", None)
                    else:
                        st.session_state["scroll_history_notice"] = f"Test prodotti scorrimento salvato correttamente · {len(righe_asta)} righe registrate."
                    for k in [
                        "scroll_rods_table_data", "scroll_rods_table_n",
                        "scroll_product_columns", "scroll_product_test_type"
                    ]:
                        st.session_state.pop(k, None)
                    st.rerun()
    else:
        st.info(
            f"La struttura di inserimento per il test {metodo_scroll} verrà definita nel prossimo passaggio."
        )
    return


def render_form_zero_test():
    edit_zero_session_id = st.session_state.get("zero_edit_session_id")
    # 2. DATI SESSIONE ZERO TEST
    # ------------------------------------------------------------
    df_sessioni_corrente = sessioni_df()
    riga_sessione = None
    if edit_zero_session_id is not None and not df_sessioni_corrente.empty:
        match_sessione = df_sessioni_corrente[
            df_sessioni_corrente["id"].astype(int) == int(edit_zero_session_id)
        ]
        if not match_sessione.empty:
            riga_sessione = match_sessione.iloc[0]

    if edit_zero_session_id is not None and riga_sessione is None:
        st.error("Lo Zero test da modificare non è più disponibile.")
        if st.button("Torna allo storico Zero test", use_container_width=True):
            st.session_state.pop("zero_edit_session_id", None)
            st.session_state.pop("zero_insert_open", None)
            cambia_pagina("Zero test")
        return

    def _safe_float_zero(valore, default=0.0):
        try:
            if pd.isna(valore):
                return float(default)
            return float(valore)
        except Exception:
            return float(default)

    def _safe_date_zero(valore):
        if valore is None or str(valore).strip() == "":
            return date.today()
        try:
            return pd.to_datetime(valore).date()
        except Exception:
            return date.today()

    def _safe_time_zero(valore):
        if valore is None or str(valore).strip() == "":
            return datetime.now().time().replace(second=0, microsecond=0)
        try:
            return datetime.strptime(str(valore)[:5], "%H:%M").time()
        except Exception:
            return datetime.now().time().replace(second=0, microsecond=0)

    suffix_zero = f"edit_{int(edit_zero_session_id)}" if edit_zero_session_id is not None else "new"

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="insert-test-title">Dati Zero test</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="insert-test-caption">Registra una volta sola le condizioni della sessione e scegli la batteria utilizzata.</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        zero_data = st.date_input(
            "Data",
            value=_safe_date_zero(riga_sessione.get("data") if riga_sessione is not None else None),
            key=f"insert_zero_date_{suffix_zero}",
        )
        zero_luogo = st.text_input(
            "Luogo *",
            value=str(riga_sessione.get("luogo") or "") if riga_sessione is not None else "",
            key=f"insert_zero_place_{suffix_zero}",
        )
    with c2:
        zero_ora = st.time_input(
            "Ora",
            value=_safe_time_zero(riga_sessione.get("ora") if riga_sessione is not None else None),
            key=f"insert_zero_time_{suffix_zero}",
        )
        zero_t_aria_txt = st.text_input(
            "Temperatura aria (°C)",
            value=_formatta_temperatura_1d(riga_sessione.get("temperatura_aria") if riga_sessione is not None else 0.0),
            key=f"insert_zero_air_{suffix_zero}",
        )
    with c3:
        zero_t_neve_txt = st.text_input(
            "Temperatura neve (°C)",
            value=_formatta_temperatura_1d(riga_sessione.get("temperatura_neve") if riga_sessione is not None else 0.0),
            key=f"insert_zero_snow_{suffix_zero}",
        )
        umidita_db_zero = (
            riga_sessione.get("umidita")
            if riga_sessione is not None and "umidita" in riga_sessione.index
            else None
        )
        umidita_non_disponibile_default = bool(
            riga_sessione is not None and pd.isna(umidita_db_zero)
        )
        zero_rh_missing_key = f"insert_zero_rh_missing_{suffix_zero}"
        if zero_rh_missing_key not in st.session_state:
            st.session_state[zero_rh_missing_key] = umidita_non_disponibile_default
        zero_ur = st.number_input(
            "Umidità relativa (%)",
            min_value=0,
            max_value=100,
            value=int(round(_safe_float_zero(umidita_db_zero if pd.notna(umidita_db_zero) else 70, 70.0))),
            step=1,
            format="%d",
            disabled=bool(st.session_state.get(zero_rh_missing_key, False)),
            key=f"insert_zero_rh_{suffix_zero}",
        )
        zero_ur_non_disponibile = st.checkbox(
            "Umidità non disponibile",
            key=zero_rh_missing_key,
        )

    batteria_opzioni = [
        "Batteria prodotti scorrimento",
        "Batteria rigature manuali",
    ]
    batteria_db = (
        str(riga_sessione.get("zero_batteria") or "").strip()
        if riga_sessione is not None and "zero_batteria" in riga_sessione.index
        else ""
    )
    batteria_index = batteria_opzioni.index(batteria_db) if batteria_db in batteria_opzioni else 0
    c_batteria, c_modello_sci, c_meteo = st.columns([1.2, 1, 1])
    with c_batteria:
        zero_batteria = st.selectbox(
            "Batteria",
            batteria_opzioni,
            index=batteria_index,
            key=f"insert_zero_battery_{suffix_zero}",
            help="Indica a quale gruppo di test verranno destinati i paia selezionati con questo Zero test.",
        )
    with c_modello_sci:
        zero_modello_sci = st.text_input(
            "Modello sci",
            value=(
                str(riga_sessione.get("zero_modello_sci") or "").strip()
                if riga_sessione is not None and "zero_modello_sci" in riga_sessione.index
                else ""
            ),
            key=f"insert_zero_ski_model_{suffix_zero}",
            placeholder="es. Speedmax 3D",
        )
    with c_meteo:
        meteo_db = (
            str(riga_sessione.get("meteo") or "").strip()
            if riga_sessione is not None and "meteo" in riga_sessione.index
            else ""
        )
        meteo_index = METEO_OPZIONI.index(meteo_db) if meteo_db in METEO_OPZIONI else None
        zero_meteo = st.selectbox(
            "Meteo",
            METEO_OPZIONI,
            index=meteo_index,
            placeholder="Seleziona meteo",
            key=f"insert_zero_weather_{suffix_zero}",
        )

    zero_note = st.text_area(
        "Note sessione",
        value=str(riga_sessione.get("note") or "") if riga_sessione is not None else "",
        key=f"insert_zero_notes_{suffix_zero}",
        placeholder="Note opzionali sulla giornata o sulle condizioni del test...",
        height=80,
    )

    # ------------------------------------------------------------
    # 3. CLASSIFICAZIONE NEVE
    # ------------------------------------------------------------
    zero_snow_options = {
        "Origine": ["Naturale", "Artificiale", "Mista"],
        "Consistenza": [
            "Compatta", "Sfarinata / Soffice", "Sgranata", "Ghiacciata",
            "Molle su fondo compatto", "Soffice su fondo compatto", "Molle",
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

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="insert-test-title">Classificazione neve</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="insert-test-caption">Usa la stessa classificazione indipendente già adottata nel catalogo scioline.</div>',
        unsafe_allow_html=True,
    )

    z1, z2, z3 = st.columns(3)
    with z1:
        zero_origine = st.multiselect(
            "Origine",
            zero_snow_options["Origine"],
            default=_valori_sessione_neve(riga_sessione.get("snow_origine") if riga_sessione is not None else "", zero_snow_options["Origine"]),
            key=f"insert_zero_origin_{suffix_zero}",
            placeholder="Seleziona origine",
        )
    with z2:
        zero_consistenza = st.multiselect(
            "Consistenza",
            zero_snow_options["Consistenza"],
            default=_valori_sessione_neve(riga_sessione.get("snow_consistenza") if riga_sessione is not None else "", zero_snow_options["Consistenza"]),
            key=f"insert_zero_consistency_{suffix_zero}",
            placeholder="Seleziona consistenza",
        )
    with z3:
        zero_umidita = st.multiselect(
            "Umidità neve",
            zero_snow_options["Umidità neve"],
            default=_valori_sessione_neve(riga_sessione.get("snow_umidita") if riga_sessione is not None else "", zero_snow_options["Umidità neve"]),
            key=f"insert_zero_humidity_{suffix_zero}",
            placeholder="Seleziona umidità neve",
        )

    z4, z5, z6 = st.columns(3)
    with z4:
        zero_forma = st.multiselect(
            "Forma grano",
            zero_snow_options["Forma grano"],
            default=_valori_sessione_neve(riga_sessione.get("snow_forma_grano") if riga_sessione is not None else "", zero_snow_options["Forma grano"]),
            key=f"insert_zero_grain_{suffix_zero}",
            placeholder="Seleziona forma grano",
        )
    with z5:
        zero_granulometria = st.multiselect(
            "Granulometria",
            zero_snow_options["Granulometria"],
            default=_valori_sessione_neve(riga_sessione.get("snow_granulometria") if riga_sessione is not None else "", zero_snow_options["Granulometria"]),
            key=f"insert_zero_size_{suffix_zero}",
            placeholder="Seleziona granulometria",
        )
    with z6:
        zero_caratteristiche = st.multiselect(
            "Caratteristiche",
            zero_snow_options["Caratteristiche"],
            default=_valori_sessione_neve(riga_sessione.get("snow_caratteristiche") if riga_sessione is not None else "", zero_snow_options["Caratteristiche"]),
            key=f"insert_zero_features_{suffix_zero}",
            placeholder="Seleziona caratteristiche",
        )

    # ------------------------------------------------------------
    # 4. MATRICE 10 PAIA x 4 PASSAGGI
    # ------------------------------------------------------------
    risultati_esistenti = (
        zero_test_sessione(int(edit_zero_session_id))
        if edit_zero_session_id is not None
        else pd.DataFrame()
    )

    gruppi_esistenti = {}
    if not risultati_esistenti.empty:
        paia_occupati = set()
        prossimo_libero = 1
        for sci_id, gruppo in risultati_esistenti.groupby("sci_id"):
            gruppo = gruppo.sort_values("prova_numero")
            tempi = {
                int(r["prova_numero"]): round(float(r["tempo_sec"]), 2)
                for _, r in gruppo.iterrows()
            }
            note_valide = [
                str(v).strip() for v in gruppo["note"].tolist()
                if str(v or "").strip()
            ]
            codice = str(gruppo.iloc[0]["sci"] or "").strip()
            try:
                paio_num = int(codice)
                if paio_num < 1 or paio_num > 10 or paio_num in paia_occupati:
                    raise ValueError
            except (TypeError, ValueError):
                while prossimo_libero in paia_occupati and prossimo_libero <= 10:
                    prossimo_libero += 1
                if prossimo_libero > 10:
                    continue
                paio_num = prossimo_libero
            paia_occupati.add(paio_num)
            gruppi_esistenti[paio_num] = (tempi, note_valide[0] if note_valide else "")

    righe_input = []
    for paio in range(1, 11):
        tempi, nota = gruppi_esistenti.get(paio, ({}, ""))
        righe_input.append({
            "Paio": paio,
            "P1 (s)": tempi.get(1),
            "P2 (s)": tempi.get(2),
            "P3 (s)": tempi.get(3),
            "P4 (s)": tempi.get(4),
            "Note": nota,
        })

    def _applica_modifiche_editor_zero(df_base, stato_editor):
        df_lavoro = df_base.copy()
        if not isinstance(stato_editor, dict):
            return df_lavoro
        modifiche = stato_editor.get("edited_rows", {}) or {}
        for indice_riga, valori in modifiche.items():
            try:
                idx = int(indice_riga)
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(df_lavoro) or not isinstance(valori, dict):
                continue
            for colonna, valore in valori.items():
                if colonna in df_lavoro.columns:
                    df_lavoro.at[idx, colonna] = valore
        return df_lavoro

    def _aggiungi_metriche_zero(df_tempi):
        df_calc = df_tempi.copy().sort_values("Paio").reset_index(drop=True)
        colonne_tempi = ["P1 (s)", "P2 (s)", "P3 (s)", "P4 (s)"]
        for colonna in colonne_tempi:
            df_calc[colonna] = pd.to_numeric(df_calc[colonna], errors="coerce")

        df_calc["Media (s)"] = df_calc[colonne_tempi].mean(axis=1, skipna=True)
        conteggio = df_calc[colonne_tempi].count(axis=1)
        df_calc.loc[conteggio == 0, "Media (s)"] = pd.NA

        df_calc["SD (s)"] = df_calc[colonne_tempi].std(axis=1, skipna=True, ddof=1)
        df_calc.loc[conteggio == 1, "SD (s)"] = 0.0
        df_calc.loc[conteggio == 0, "SD (s)"] = pd.NA

        paio_simile = []
        delta_simile = []
        for idx, riga in df_calc.iterrows():
            media_corrente = riga["Media (s)"]
            if pd.isna(media_corrente):
                paio_simile.append(None)
                delta_simile.append(None)
                continue
            candidati = df_calc.loc[
                (df_calc.index != idx) & df_calc["Media (s)"].notna(),
                ["Paio", "Media (s)"],
            ].copy()
            if candidati.empty:
                paio_simile.append(None)
                delta_simile.append(None)
                continue
            candidati["delta"] = (candidati["Media (s)"] - float(media_corrente)).abs()
            candidati = candidati.sort_values(["delta", "Paio"], ascending=[True, True])
            match = candidati.iloc[0]
            paio_simile.append(int(match["Paio"]))
            delta_simile.append(float(match["delta"]))

        df_calc["Paio più simile"] = paio_simile
        df_calc["Δ dal più simile (s)"] = delta_simile
        for colonna in colonne_tempi + ["Media (s)", "SD (s)", "Δ dal più simile (s)"]:
            df_calc[colonna] = pd.to_numeric(df_calc[colonna], errors="coerce").round(2)
        return df_calc[[
            "Paio", "P1 (s)", "P2 (s)", "P3 (s)", "P4 (s)",
            "Media (s)", "SD (s)", "Paio più simile", "Δ dal più simile (s)", "Note",
        ]]

    editor_key = f"insert_zero_matrix_{suffix_zero}"
    df_base_zero = _applica_modifiche_editor_zero(
        pd.DataFrame(righe_input),
        st.session_state.get(editor_key),
    )
    df_zero_completo = _aggiungi_metriche_zero(df_base_zero)
    coppia_top = coppia_zero_test_piu_vicina(df_zero_completo)
    if coppia_top:
        paio_a, paio_b, delta_top = coppia_top
        coppia_label = f"{paio_a} ↔ {paio_b} · Δ {delta_top:.2f} s"
    else:
        coppia_label = "—"

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="insert-test-title">Zero test · 10 paia × 4 passaggi</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="insert-test-caption">Inserisci i quattro tempi. Media, deviazione standard e paio più simile sono calcolati automaticamente.</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="zero-test-header-row">'
        f'<div class="zero-test-chip"><div class="zero-test-chip-label">Paia</div><div class="zero-test-chip-value">10</div></div>'
        f'<div class="zero-test-chip"><div class="zero-test-chip-label">Passaggi / paio</div><div class="zero-test-chip-value">4</div></div>'
        f'<div class="zero-test-chip"><div class="zero-test-chip-label">Coppia più vicina</div><div class="zero-test-chip-value">{coppia_label}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    editor_zero = st.data_editor(
        df_zero_completo,
        key=editor_key,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        height=455,
        column_config={
            "Paio": st.column_config.NumberColumn("Paio", width="small", format="%d"),
            "P1 (s)": st.column_config.NumberColumn("P1", min_value=0.0, step=0.01, format="%.2f", width="small"),
            "P2 (s)": st.column_config.NumberColumn("P2", min_value=0.0, step=0.01, format="%.2f", width="small"),
            "P3 (s)": st.column_config.NumberColumn("P3", min_value=0.0, step=0.01, format="%.2f", width="small"),
            "P4 (s)": st.column_config.NumberColumn("P4", min_value=0.0, step=0.01, format="%.2f", width="small"),
            "Media (s)": st.column_config.NumberColumn("Media", format="%.2f", width="small"),
            "SD (s)": st.column_config.NumberColumn("Dev. std.", format="%.2f", width="small"),
            "Paio più simile": st.column_config.NumberColumn("Paio simile", format="%d", width="medium"),
            "Δ dal più simile (s)": st.column_config.NumberColumn("Δ simile", format="%.2f", width="medium"),
            "Note": st.column_config.TextColumn("Note", width="small"),
        },
        disabled=["Paio", "Media (s)", "SD (s)", "Paio più simile", "Δ dal più simile (s)"],
    )

    # ------------------------------------------------------------
    # 5. SALVATAGGIO
    # ------------------------------------------------------------
    c_save, c_cancel = st.columns([3, 1])
    with c_save:
        salva_zero = st.button(
            "Salva modifiche" if edit_zero_session_id is not None else "Salva Zero test",
            type="primary",
            use_container_width=True,
            key=f"save_insert_zero_{suffix_zero}",
        )
    with c_cancel:
        annulla_zero = False
        if edit_zero_session_id is not None:
            annulla_zero = st.button(
                "Annulla modifica",
                use_container_width=True,
                key=f"cancel_insert_zero_{suffix_zero}",
            )

    if annulla_zero:
        st.session_state.pop("zero_edit_session_id", None)
        st.session_state.pop("zero_insert_open", None)
        cambia_pagina("Zero test")

    if salva_zero:
        if not zero_luogo.strip():
            st.error("Inserisci il luogo dello Zero test.")
        else:
            righe_da_salvare = []
            for _, riga in editor_zero.sort_values("Paio").iterrows():
                paio_num = int(riga["Paio"])
                valori_tempi = []
                for colonna in ["P1 (s)", "P2 (s)", "P3 (s)", "P4 (s)"]:
                    valore = riga.get(colonna)
                    if pd.isna(valore) or valore in ("", None):
                        valori_tempi.append(None)
                    else:
                        numero = round(float(valore), 2)
                        valori_tempi.append(numero if numero > 0 else None)
                if not any(v is not None for v in valori_tempi):
                    continue
                righe_da_salvare.append({
                    "codice_sci": str(paio_num),
                    "tempi": valori_tempi,
                    "note": str(riga.get("Note") or "").strip(),
                })

            if not righe_da_salvare:
                st.error("Inserisci almeno un paio con un tempo valido.")
            else:
                if edit_zero_session_id is None:
                    esegui(
                        """
                        INSERT INTO sessioni (
                            data, ora, luogo, temperatura_aria, temperatura_neve,
                            umidita, meteo, tipo_neve, condizione_pista, note, zero_batteria, zero_modello_sci, creato_il
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?)
                        """,
                        (
                            zero_data.isoformat(),
                            zero_ora.strftime("%H:%M"),
                            zero_luogo.strip(),
                            _parse_temperatura_1d(zero_t_aria_txt),
                            _parse_temperatura_1d(zero_t_neve_txt),
                            None if zero_ur_non_disponibile else int(zero_ur),
                            zero_meteo or "",
                            zero_note.strip(),
                            zero_batteria,
                            zero_modello_sci.strip(),
                            datetime.now().isoformat(timespec="seconds"),
                        ),
                    )
                    df_nuova_sessione = leggi_df("SELECT MAX(id) AS id FROM sessioni")
                    sessione_id = int(df_nuova_sessione.iloc[0]["id"])
                else:
                    sessione_id = int(edit_zero_session_id)
                    esegui(
                        """
                        UPDATE sessioni
                        SET data = ?, ora = ?, luogo = ?, temperatura_aria = ?,
                            temperatura_neve = ?, umidita = ?, meteo = ?, note = ?, zero_batteria = ?, zero_modello_sci = ?
                        WHERE id = ?
                        """,
                        (
                            zero_data.isoformat(),
                            zero_ora.strftime("%H:%M"),
                            zero_luogo.strip(),
                            _parse_temperatura_1d(zero_t_aria_txt),
                            _parse_temperatura_1d(zero_t_neve_txt),
                            None if zero_ur_non_disponibile else int(zero_ur),
                            zero_meteo or "",
                            zero_note.strip(),
                            zero_batteria,
                            zero_modello_sci.strip(),
                            sessione_id,
                        ),
                    )

                classificazione = {
                    "snow_origine": _compatta_neve_sessione(zero_origine, zero_snow_options["Origine"]),
                    "snow_consistenza": _compatta_neve_sessione(zero_consistenza, zero_snow_options["Consistenza"]),
                    "snow_umidita": _compatta_neve_sessione(zero_umidita, zero_snow_options["Umidità neve"]),
                    "snow_forma_grano": _compatta_neve_sessione(zero_forma, zero_snow_options["Forma grano"]),
                    "snow_granulometria": _compatta_neve_sessione(zero_granulometria, zero_snow_options["Granulometria"]),
                    "snow_caratteristiche": _compatta_neve_sessione(zero_caratteristiche, zero_snow_options["Caratteristiche"]),
                    "zero_batteria": zero_batteria,
                }
                salva_zero_test_matrice(sessione_id, righe_da_salvare, classificazione)
                st.session_state.pop("zero_edit_session_id", None)
                st.session_state.pop("zero_insert_open", None)
                st.session_state["zero_history_notice"] = (
                    "Zero test modificato correttamente."
                    if edit_zero_session_id is not None
                    else "Zero test salvato correttamente."
                )
                cambia_pagina("Zero test")

if "pagina" not in st.session_state:
    st.session_state["pagina"] = "Dashboard"

pagina = st.session_state["pagina"]



def _product_cell_html(nome, foto_data=None, foto_mime=None):
    """Cella prodotto compatta: solo nome, con preview grande al passaggio del mouse."""
    nome_pulito = str(nome or "—").strip() or "—"
    if nome_pulito == "—":
        return '<div class="test-product-empty">—</div>'

    preview_html = ""
    valore_foto = str(foto_data or "").strip()
    if valore_foto:
        mime = str(foto_mime or "image/png").strip() or "image/png"
        src = f"data:{html_escape(mime)};base64,{valore_foto}"
        preview_html = (
            f'<div class="test-product-hover-preview"><img src="{src}" alt="{html_escape(nome_pulito)}"></div>'
        )

    return (
        '<div class="test-product-cell">'
        '<div class="test-product-hover-target">'
        f'<div class="test-product-name">{html_escape(nome_pulito)}</div>'
        f'{preview_html}'
        '</div>'
        '</div>'
    )

def _chiave_ordine_numero_sci(valore):
    """Ordine naturale per codici sci come 1A, 1B, 2A, 10B; fallback alfabetico."""
    testo = str(valore or "").strip()
    if not testo:
        return (10**9, "", "")
    match = re.match(r"^\s*(\d+)\s*([A-Za-z]*)\s*(.*)$", testo)
    if match:
        return (int(match.group(1)), match.group(2).upper(), match.group(3).upper())
    return (10**9 - 1, testo.upper(), "")



def _nome_file_pdf_test_scorrimento(test):
    data = str(test.get("data") or "test").strip().replace("/", "-")
    luogo = re.sub(r"[^A-Za-z0-9_-]+", "_", str(test.get("luogo") or "").strip()).strip("_")
    metodo = str(test.get("tipo_test") or "").replace("Test prodotti scorrimento · ", "").strip()
    metodo = re.sub(r"[^A-Za-z0-9_-]+", "_", metodo).strip("_")
    parti = ["SnowDataPro", "test_scorrimento", data]
    if luogo:
        parti.append(luogo)
    if metodo:
        parti.append(metodo)
    return "_".join(parti) + ".pdf"


def _crea_pdf_test_scorrimento(test, df_righe):
    """Crea un PDF professionale del test prodotti scorrimento."""
    from io import BytesIO
    from xml.sax.saxutils import escape as xml_escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="SnowDataPro - Test prodotti scorrimento",
        author="SnowDataPro",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SDPTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=21, textColor=colors.HexColor("#1f2933"),
        spaceAfter=5 * mm, alignment=TA_LEFT,
    )
    section_style = ParagraphStyle(
        "SDPSection", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=11, leading=14, textColor=colors.HexColor("#1f2933"),
        spaceBefore=3 * mm, spaceAfter=2 * mm,
    )
    label_style = ParagraphStyle(
        "SDPLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7.5, leading=9, textColor=colors.HexColor("#52616b"),
    )
    value_style = ParagraphStyle(
        "SDPValue", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=10.5, textColor=colors.HexColor("#263238"),
    )
    small_style = ParagraphStyle(
        "SDPSmall", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7.2, leading=8.8, textColor=colors.HexColor("#263238"),
    )
    header_style = ParagraphStyle(
        "SDPHeader", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7.4, leading=9, textColor=colors.HexColor("#37474f"), alignment=TA_CENTER,
    )

    def pv(v, default="-"):
        if v is None:
            return default
        try:
            if pd.isna(v):
                return default
        except Exception:
            pass
        txt = str(v).strip()
        return txt if txt else default

    def para(v, style=value_style):
        return Paragraph(xml_escape(pv(v)), style)

    metodo = str(test.get("tipo_test") or "Test prodotti scorrimento").replace("Test prodotti scorrimento · ", "").strip()
    taria = _formatta_temperatura_1d(test.get("temperatura_aria"))
    tneve = _formatta_temperatura_1d(test.get("temperatura_neve"))
    ur = test.get("umidita")
    ur_txt = "Non disponibile" if ur is None or (isinstance(ur, float) and pd.isna(ur)) else f"{int(round(float(ur)))} %"

    story = [
        Paragraph("SnowDataPro - Test prodotti scorrimento", title_style),
    ]

    summary = [
        [Paragraph("METODO TEST", label_style), Paragraph("PRODOTTI/COMBINAZIONI TESTATI", label_style), Paragraph("T ARIA", label_style), Paragraph("T NEVE", label_style)],
        [para(metodo), para(len(df_righe)), para(f"{taria} °C"), para(f"{tneve} °C")],
    ]
    t = Table(summary, colWidths=[55*mm, 65*mm, 45*mm, 45*mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eef1f4")),
        ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#d8dde3")),
        ("INNERGRID", (0,0), (-1,-1), 0.4, colors.HexColor("#d8dde3")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story += [t, Spacer(1, 4*mm), Paragraph("Sessione", section_style)]

    sessione = [
        [Paragraph("Data", label_style), para(test.get("data")), Paragraph("Ora", label_style), para(str(test.get("ora") or "-")[:5]), Paragraph("Luogo", label_style), para(test.get("luogo"))],
        [Paragraph("Meteo", label_style), para(test.get("meteo")), Paragraph("Umidità relativa", label_style), para(ur_txt), Paragraph("Modello sci", label_style), para(test.get("zero_modello_sci"))],
    ]
    ts = Table(sessione, colWidths=[25*mm, 45*mm, 25*mm, 35*mm, 25*mm, 55*mm], hAlign="LEFT")
    ts.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f7f9fa")),
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#d8dde3")),
        ("INNERGRID", (0,0), (-1,-1), 0.35, colors.HexColor("#e3e7eb")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story += [ts, Spacer(1, 3*mm), Paragraph("Tipologia neve", section_style)]

    snow = [
        [Paragraph("Origine", label_style), para(test.get("snow_origine")), Paragraph("Consistenza", label_style), para(test.get("snow_consistenza")), Paragraph("Umidità neve", label_style), para(test.get("snow_umidita"))],
        [Paragraph("Forma grano", label_style), para(test.get("snow_forma_grano")), Paragraph("Granulometria", label_style), para(test.get("snow_granulometria")), Paragraph("Caratteristiche", label_style), para(test.get("snow_caratteristiche"))],
    ]
    tn = Table(snow, colWidths=[25*mm, 45*mm, 25*mm, 45*mm, 25*mm, 55*mm], hAlign="LEFT")
    tn.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f7f9fa")),
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#d8dde3")),
        ("INNERGRID", (0,0), (-1,-1), 0.35, colors.HexColor("#e3e7eb")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story += [tn, Spacer(1, 3*mm), Paragraph("Dettaglio test", section_style)]

    df_pdf = df_righe.copy()
    if not df_pdf.empty:
        df_pdf["_pos"] = pd.to_numeric(df_pdf["posizione"], errors="coerce")
        df_pdf = df_pdf.sort_values(["_pos"], na_position="last", kind="stable").drop(columns=["_pos"])

    table_data = [[Paragraph(x, header_style) for x in ["Pos.", "Sci", "Base", "Paraffina", "Top coating", "Liquido", "Note"]]]
    for _, r in df_pdf.iterrows():
        pos = r.get("posizione")
        pos_txt = "-" if pos is None or (isinstance(pos, float) and pd.isna(pos)) else str(int(float(pos)))
        table_data.append([
            Paragraph(xml_escape(pos_txt), small_style),
            para(r.get("numero_sci"), small_style),
            para(r.get("base"), small_style),
            para(r.get("paraffina"), small_style),
            para(r.get("top_coating"), small_style),
            para(r.get("liquido"), small_style),
            para(r.get("note"), small_style),
        ])

    td = Table(table_data, colWidths=[13*mm, 18*mm, 42*mm, 42*mm, 45*mm, 45*mm, 50*mm], repeatRows=1, hAlign="LEFT")
    styles_table = [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eef1f4")),
        ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#d8dde3")),
        ("INNERGRID", (0,0), (-1,-1), 0.35, colors.HexColor("#d8dde3")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,1), (1,-1), "CENTER"),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]
    # Evidenzia solo il primo classificato con testo in grassetto, senza sfondi colorati.
    for idx, (_, r) in enumerate(df_pdf.iterrows(), start=1):
        try:
            if int(float(r.get("posizione"))) == 1:
                styles_table.append(("FONTNAME", (0, idx), (-1, idx), "Helvetica-Bold"))
        except Exception:
            pass
    td.setStyle(TableStyle(styles_table))
    story.append(td)

    doc.build(story)
    return buffer.getvalue()



def _normalizza_tipo_prodotti_test_scorrimento(valore):
    valore = str(valore or "").strip()
    validi = {
        "Test liquidi", "Test top coating", "Test paraffine",
        "Test basi", "Test combinazioni"
    }
    return valore if valore in validi else "Test combinazioni"


def _render_test_scorrimento_podium(df_righe, tipo_prodotti_testati=None):
    """Podio dei primi tre: mostra solo il prodotto oggetto del confronto, oppure l'intera combinazione."""
    if df_righe is None or df_righe.empty:
        return

    df_podio = df_righe.copy()
    df_podio["_pos_num"] = pd.to_numeric(df_podio.get("posizione"), errors="coerce")
    df_podio = df_podio[df_podio["_pos_num"].isin([1, 2, 3])]
    if df_podio.empty:
        return

    # Una sola riga per gradino: in caso di dati duplicati mantiene la prima registrata.
    df_podio = (
        df_podio.sort_values("_pos_num", kind="stable")
        .drop_duplicates(subset=["_pos_num"], keep="first")
    )
    records_by_pos = {
        int(r["_pos_num"]): r
        for r in df_podio.to_dict("records")
        if r.get("_pos_num") is not None and not pd.isna(r.get("_pos_num"))
    }

    def _foto_src(foto_data, foto_mime):
        valore = str(foto_data or "").strip()
        if not valore:
            return ""
        mime = str(foto_mime or "image/png").strip() or "image/png"
        return f"data:{html_escape(mime)};base64,{valore}"

    tipo_focus = _normalizza_tipo_prodotti_test_scorrimento(tipo_prodotti_testati)
    campi_focus = {
        "Test basi": {"Base"},
        "Test paraffine": {"Paraffina"},
        "Test top coating": {"Top coating"},
        "Test liquidi": {"Liquido"},
        "Test combinazioni": {"Base", "Paraffina", "Top coating", "Liquido"},
    }
    categorie_podio = campi_focus.get(tipo_focus, campi_focus["Test combinazioni"])

    def _prodotti_record(record):
        campi = [
            ("Base", "base", "base_foto", "base_mime"),
            ("Paraffina", "paraffina", "paraffina_foto", "paraffina_mime"),
            ("Top coating", "top_coating", "top_foto", "top_mime"),
            ("Liquido", "liquido", "liquido_foto", "liquido_mime"),
        ]
        prodotti = []
        for categoria, nome_key, foto_key, mime_key in campi:
            if categoria not in categorie_podio:
                continue
            nome = str(record.get(nome_key) or "").strip()
            if not nome or nome == "—":
                continue
            prodotti.append({
                "categoria": categoria,
                "nome": nome,
                "src": _foto_src(record.get(foto_key), record.get(mime_key)),
            })
        return prodotti

    def _product_tile_html(prodotto, singolo=False):
        nome = html_escape(prodotto["nome"])
        categoria = html_escape(prodotto["categoria"])
        src = prodotto["src"]
        img_class = " podium-single-image" if singolo else ""
        if src:
            visual = f'<img class="podium-product-image{img_class}" src="{src}" alt="{nome}">'
        else:
            visual = f'<div class="podium-product-placeholder{img_class}"><span>IMG</span></div>'
        return (
            '<div class="podium-product-tile">'
            f'{visual}'
            f'<div class="podium-product-category">{categoria}</div>'
            f'<div class="podium-product-name" title="{nome}">{nome}</div>'
            '</div>'
        )

    def _entry_html(pos):
        record = records_by_pos.get(pos)
        if not record:
            return '<div class="scroll-podium-entry podium-empty-slot"></div>'

        prodotti = _prodotti_record(record)
        rank_word = {1: "1°", 2: "2°", 3: "3°"}[pos]
        place_class = {1: "first", 2: "second", 3: "third"}[pos]

        if prodotti:
            singolo = len(prodotti) == 1
            products_html = ''.join(_product_tile_html(p, singolo=singolo) for p in prodotti)
        else:
            products_html = (
                '<div class="podium-no-products">'
                '<div class="podium-product-placeholder podium-single-image"><span>IMG</span></div>'
                '<div class="podium-product-name">Nessun prodotto associato</div>'
                '</div>'
            )

        return (
            f'<div class="scroll-podium-entry podium-{place_class}">'
            '<div class="podium-result-card">'
            f'<div class="podium-product-grid count-{min(len(prodotti), 4)}">{products_html}</div>'
            '</div>'
            f'<div class="podium-step podium-step-{place_class}">'
            f'<span class="podium-step-rank">{rank_word}</span>'
            '</div>'
            '</div>'
        )

    # Ordine visivo classico del podio: 2° a sinistra, 1° al centro, 3° a destra.
    podium_html = (
        '<div class="scroll-podium-wrap">'
        '<div class="scroll-podium">'
        f'{_entry_html(2)}{_entry_html(1)}{_entry_html(3)}'
        '</div>'
        '</div>'
    )

    st.markdown(
        """
        <style>
        .scroll-podium-wrap {
            margin: .35rem 0 1.1rem 0;
            padding: 1rem 1rem .15rem 1rem;
            border: 1px solid #d8dde3;
            border-radius: 14px;
            background: linear-gradient(180deg, #ffffff 0%, #f7f9fa 100%);
            overflow-x: auto;
        }
        .scroll-podium {
            min-width: 760px;
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: .8rem;
            align-items: end;
        }
        .scroll-podium-entry {
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            min-width: 0;
        }
        .podium-result-card {
            position: relative;
            background: #ffffff;
            border: 1px solid #d8dde3;
            border-radius: 12px 12px 8px 8px;
            padding: 1rem .8rem .8rem .8rem;
            box-shadow: 0 7px 18px rgba(31, 41, 51, .07);
            min-height: 222px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .podium-first .podium-result-card {
            border-color: #d8b54c;
            box-shadow: 0 9px 24px rgba(31, 41, 51, .10);
        }
        .podium-product-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: .75rem;
            align-items: start;
            width: 100%;
        }
        .podium-product-grid.count-1 {
            grid-template-columns: 1fr;
        }
        .podium-product-tile,
        .podium-no-products {
            min-width: 0;
            text-align: center;
        }
        .podium-product-image,
        .podium-product-placeholder {
            width: 100%;
            height: 92px;
            object-fit: contain;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #f7f9fa;
            border: 1px solid #e3e7eb;
            border-radius: 10px;
            margin: 0 auto .42rem auto;
            padding: .35rem;
        }
        .podium-product-image.podium-single-image,
        .podium-product-placeholder.podium-single-image {
            width: 132px;
            height: 132px;
        }
        .podium-product-placeholder span {
            color: #a5b0b8;
            font-size: .62rem;
            font-weight: 800;
            letter-spacing: .08em;
        }
        .podium-product-category {
            color: #8a98a3;
            font-size: .62rem;
            line-height: 1.08;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .04em;
            margin-bottom: .16rem;
        }
        .podium-product-name {
            color: #263238;
            font-size: .82rem;
            line-height: 1.16;
            font-weight: 700;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            overflow-wrap: anywhere;
        }
        .podium-step {
            display: flex;
            align-items: flex-start;
            justify-content: center;
            border: 1px solid #cfd6dc;
            border-top-width: 4px;
            border-radius: 5px 5px 0 0;
            background: #eef1f4;
            margin: .35rem .25rem 0 .25rem;
            padding-top: .6rem;
        }
        .podium-step-first {
            height: 108px;
            border-top-color: #d4af37;
            background: linear-gradient(180deg, #fffaf0 0%, #eef1f4 100%);
        }
        .podium-step-second {
            height: 78px;
            border-top-color: #aeb7bf;
        }
        .podium-step-third {
            height: 58px;
            border-top-color: #b97a45;
        }
        .podium-step-rank {
            color: #263238;
            font-size: 1.05rem;
            line-height: 1;
            font-weight: 850;
        }
        .podium-empty-slot {
            min-height: 1px;
        }
        @media (max-width: 900px) {
            .scroll-podium-wrap { padding-left: .7rem; padding-right: .7rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(podium_html, unsafe_allow_html=True)

def _render_test_scorrimento_detail_table(df_righe):
    """Tabella storico test scorrimento compatta con sole colonne prodotto realmente usate."""
    if df_righe is None or df_righe.empty:
        return

    # Mostra nello storico soltanto gli strati effettivamente presenti nel test.
    # Le colonne non selezionate nell'inserimento vengono salvate vuote/null e,
    # dopo le LEFT JOIN, arrivano come "—": per questo possiamo ricostruire
    # automaticamente la configurazione senza modificare lo schema del database.
    colonne_prodotto = [
        ("Base", "base", "base_foto", "base_mime", "base_id"),
        ("Paraffina", "paraffina", "paraffina_foto", "paraffina_mime", "paraffina_id"),
        ("Top coating", "top_coating", "top_foto", "top_mime", "top_coating_id"),
        ("Liquido", "liquido", "liquido_foto", "liquido_mime", "liquido_id"),
    ]

    def _id_prodotto_presente(nome_colonna_id):
        """Una colonna è attiva solo se nel test esiste almeno un ID prodotto reale."""
        if nome_colonna_id not in df_righe.columns:
            return False
        for valore in df_righe[nome_colonna_id].tolist():
            if valore is None:
                continue
            try:
                if pd.isna(valore):
                    continue
            except (TypeError, ValueError):
                pass
            testo = str(valore).strip()
            if testo and testo.lower() not in {"none", "nan", "<na>", "0", "0.0"}:
                return True
        return False

    # La scelta delle colonne si basa sugli ID salvati in test_scorrimento_aste,
    # non sui testi delle LEFT JOIN. In questo modo Base/Paraffina non vengono
    # mostrate quando non erano state selezionate nel test.
    colonne_attive = [
        dati for dati in colonne_prodotto
        if _id_prodotto_presente(dati[4])
    ]

    # Se per un vecchio test non fosse possibile ricostruire la configurazione,
    # manteniamo almeno la struttura base senza aggiungere colonne vuote.
    numero_colonne_prodotto = len(colonne_attive)
    larghezza_minima = 320 + (158 * numero_colonne_prodotto)

    st.markdown(
        f"""
        <style>
        .scroll-test-table-wrap {{
            overflow-x: auto;
            overflow-y: visible;
            border: 1px solid #d8dde3;
            border-radius: 12px;
            background: #ffffff;
            margin-top: .35rem;
            position: relative;
            z-index: 1;
        }}
        .scroll-test-table tbody tr {{
            position: relative;
            z-index: 1;
        }}
        .scroll-test-table tbody tr:has(.test-product-hover-target:hover) {{
            z-index: 2147483646 !important;
        }}
        table.scroll-test-table {{
            width: 100%;
            min-width: {larghezza_minima}px;
            border-collapse: separate;
            border-spacing: 0;
            table-layout: fixed;
            color: #263238;
            font-size: .72rem;
            font-weight: 500;
        }}
        .scroll-test-table th {{
            background: #eef1f4;
            color: #52616b;
            font-size: .72rem;
            font-weight: 650;
            text-align: left;
            padding: .38rem .34rem;
            border-bottom: 1px solid #d8dde3;
            white-space: nowrap;
            line-height: 1.15;
        }}
        .scroll-test-table td {{
            padding: .34rem .34rem;
            border-bottom: 1px solid #e3e7eb;
            vertical-align: middle;
            overflow: visible;
            position: relative;
            color: #263238;
            font-size: .72rem;
            font-weight: 500;
            line-height: 1.12;
        }}
        .scroll-test-table tr:last-child td {{ border-bottom: 0; }}
        .scroll-test-table th.col-posizione, .scroll-test-table td.col-posizione {{ width: 62px; text-align:center; }}
        .scroll-test-table th.col-sci, .scroll-test-table td.col-sci {{ width: 88px; }}
        .scroll-test-table th.col-prodotto, .scroll-test-table td.col-prodotto {{ width: 158px; }}
        .scroll-test-table th.col-note, .scroll-test-table td.col-note {{ width: 170px; }}
        .test-product-cell {{
            min-height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            position: relative;
        }}
        .test-product-hover-target {{
            position: relative;
            display: inline-block;
            max-width: 100%;
            cursor: zoom-in;
            z-index: auto;
        }}
        .scroll-test-table tr:has(.test-product-hover-target:hover),
        .scroll-test-table td:has(.test-product-hover-target:hover),
        .test-product-hover-target:hover {{
            z-index: 2147483646 !important;
        }}
        .test-product-hover-preview {{
            position: fixed;
            top: 138px;
            right: 32px;
            left: auto;
            bottom: auto;
            transform: translateY(8px) scale(.97);
            opacity: 0;
            visibility: hidden;
            width: min(410px, 30vw);
            height: min(410px, 52vh);
            padding: 14px;
            background: #ffffff;
            border: 1px solid #c8d0d7;
            border-radius: 15px;
            box-shadow: 0 24px 64px rgba(31,41,51,.34);
            pointer-events: none;
            isolation: isolate;
            z-index: 2147483647 !important;
            transition: opacity .12s ease, transform .12s ease, visibility .12s ease;
        }}
        .test-product-hover-preview img {{
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
        }}
        .test-product-hover-target:hover .test-product-hover-preview {{
            opacity: 1;
            visibility: visible;
            transform: translateY(0) scale(1);
        }}
        .test-product-name {{
            line-height: 1.08;
            font-weight: 500;
            font-size: .72rem;
            color: #263238;
            white-space: nowrap;
            overflow-wrap: normal;
            transition: color .12s ease;
        }}
        .test-product-hover-target:hover .test-product-name {{
            color: #007ea8;
        }}
        .scroll-test-table tbody tr.test-winner td {{
            background: #ffffff;
            font-weight: 750;
        }}
        .scroll-test-table tbody tr.test-winner .test-product-name,
        .scroll-test-table tbody tr.test-winner .scroll-test-note {{
            font-weight: 750;
            color: #263238;
        }}
        .winner-position {{
            font-weight: 800;
            color: #263238;
        }}
        .scroll-test-table tbody tr:not(.test-winner) td {{ background: #ffffff; }}
        .test-product-empty {{
            color: #9aa7b2;
            text-align: center;
            font-size: .72rem;
            font-weight: 500;
        }}
        .scroll-test-note {{
            color: #263238;
            line-height: 1.08;
            white-space: nowrap;
            font-size: .72rem;
            font-weight: 500;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    righe_html = []
    for record in df_righe.to_dict("records"):
        posizione = record.get("posizione")
        if posizione is None or (isinstance(posizione, float) and pd.isna(posizione)):
            pos_txt = "—"
        elif isinstance(posizione, (int, float)) and not pd.isna(posizione):
            pos_txt = str(int(posizione))
        else:
            pos_txt = str(posizione)
        note = html_escape(str(record.get("note") or "—"))

        is_winner = False
        try:
            is_winner = int(float(posizione)) == 1
        except (TypeError, ValueError):
            is_winner = str(posizione or "").strip() == "1"

        row_class = ' class="test-winner"' if is_winner else ""
        if is_winner:
            posizione_html = f'<span class="winner-position">{html_escape(pos_txt)}</span>'
        else:
            posizione_html = html_escape(pos_txt)

        celle_prodotti = "".join(
            f'<td class="col-prodotto">{_product_cell_html(record.get(campo), record.get(campo_foto), record.get(campo_mime))}</td>'
            for _, campo, campo_foto, campo_mime, _ in colonne_attive
        )

        righe_html.append(
            f"<tr{row_class}>"
            f'<td class="col-posizione">{posizione_html}</td>'
            f'<td class="col-sci">{numero_sci}</td>'
            f"{celle_prodotti}"
            f'<td class="col-note"><div class="scroll-test-note">{note}</div></td>'
            "</tr>"
        )

    intestazioni_prodotti = "".join(
        f'<th class="col-prodotto">{html_escape(etichetta)}</th>'
        for etichetta, _, _, _, _ in colonne_attive
    )

    html = (
        '<div class="scroll-test-table-wrap">'
        '<table class="scroll-test-table">'
        '<thead><tr>'
        '<th class="col-posizione">Posizione</th>'
        '<th class="col-sci">Numero sci</th>'
        + intestazioni_prodotti +
        '<th class="col-note">Note</th>'
        '</tr></thead>'
        '<tbody>' + ''.join(righe_html) + '</tbody></table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def cambia_pagina(nome):
    st.session_state["pagina"] = nome
    st.rerun()



# ============================================================
# SIDEBAR — replica grafica Sector G2 Lab
# Inserita a valle di tutti gli altri CSS per evitare override
# del tema generale di SnowDataPro sui pulsanti del menu.
# ============================================================
st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] {
        background: #191c1e !important;
        border-right: 1px solid #2b3033 !important;
    }

    section[data-testid="stSidebar"] > div {
        padding-top: 1.8rem !important;
    }

    /* Nessun riquadro attorno alle sezioni Test / Prodotti. */
    section[data-testid="stSidebar"] [data-testid="stExpander"],
    section[data-testid="stSidebar"] [data-testid="stExpander"] > details,
    section[data-testid="stSidebar"] [data-testid="stExpander"] > details[open],
    section[data-testid="stSidebar"] [data-testid="stExpander"] > details > div {
        background: transparent !important;
        border: 0 !important;
        outline: 0 !important;
        box-shadow: none !important;
        border-radius: 3px !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] {
        margin-top: 0.35rem !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
        min-height: 44px !important;
        padding-left: 0.4rem !important;
        background: transparent !important;
        color: #c9d0d4 !important;
        border: 0 !important;
        outline: 0 !important;
        box-shadow: none !important;
        border-radius: 3px !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
        background: #252a2d !important;
        color: #ffffff !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] summary p {
        color: inherit !important;
        font-weight: 400 !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
        color: #9ba6ac !important;
        fill: #9ba6ac !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] > details > div {
        padding-left: 0.65rem !important;
    }

    /* Tutte le voci hanno lo stesso aspetto neutro di Sector. */
    section[data-testid="stSidebar"] .stButton > button,
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"],
    section[data-testid="stSidebar"] button[kind="secondary"] {
        width: 100% !important;
        min-height: 44px !important;
        justify-content: flex-start !important;
        text-align: left !important;
        padding-left: 0.65rem !important;
        background: transparent !important;
        color: #c9d0d4 !important;
        border: 0 !important;
        border-radius: 3px !important;
        box-shadow: none !important;
        font-weight: 400 !important;
    }

    section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button,
    section[data-testid="stSidebar"] [data-testid="stExpander"] button[data-testid="stBaseButton-secondary"] {
        min-height: 39px !important;
        font-size: 0.90rem !important;
        padding-left: 1.25rem !important;
    }

    section[data-testid="stSidebar"] .stButton > button:hover,
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover,
    section[data-testid="stSidebar"] button[kind="secondary"]:hover {
        background: #252a2d !important;
        color: #ffffff !important;
        border: 0 !important;
        box-shadow: none !important;
    }

    /* Voce attiva: grigio scuro + sola barra azzurra a sinistra, come Sector. */
    section[data-testid="stSidebar"] .stButton > button[kind="primary"],
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"],
    section[data-testid="stSidebar"] button[kind="primary"] {
        background: #252a2d !important;
        color: #ffffff !important;
        border: 0 !important;
        border-left: 4px solid #00a7e1 !important;
        border-radius: 2px !important;
        box-shadow: none !important;
        font-weight: 500 !important;
    }

    section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
    section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover,
    section[data-testid="stSidebar"] button[kind="primary"]:hover {
        background: #252a2d !important;
        color: #ffffff !important;
        border: 0 !important;
        border-left: 4px solid #00a7e1 !important;
    }

    section[data-testid="stSidebar"] .stButton button > div {
        justify-content: flex-start !important;
        width: 100% !important;
    }

    section[data-testid="stSidebar"] .stButton button p,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {
        color: inherit !important;
        text-align: left !important;
    }

    section[data-testid="stSidebar"] ::-webkit-scrollbar {
        width: 6px !important;
    }

    section[data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
        background: #41484c !important;
        border-radius: 10px !important;
    }

    /* Mantiene il logo centrato e con la stessa gerarchia di Sector. */
    section[data-testid="stSidebar"] [data-testid="stImage"] {
        display: flex !important;
        justify-content: center !important;
        width: 100% !important;
    }

    section[data-testid="stSidebar"] [data-testid="stImage"] img {
        margin-left: auto !important;
        margin-right: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

logo_sidebar_path = os.path.join(BASE_DIR, "snowdatapro_logo_transparent.png")

if os.path.exists(logo_sidebar_path):
    # Stesse proporzioni e stessa centratura usate nella sidebar di Sector G2 Lab.
    col_logo_sx, col_logo, col_logo_dx = st.sidebar.columns([1, 4, 1])

    with col_logo:
        st.image(
            logo_sidebar_path,
            width=250,
        )

    # Stessa distanza tra branding e primo elemento del menu di Sector G2 Lab.
    st.sidebar.markdown(
        '<div style="height: 28px;"></div>',
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
    expanded=pagina in [
        "Zero test",
        "Test prodotti scorrimento",
        "Test scioline di tenuta",
        "Test rigature manuali",
    ],
    icon=":material/science:",
):
    if st.button(
        "Zero test",
        icon=":material/timer:",
        key="menu_zero_test",
        use_container_width=True,
        type="primary" if pagina == "Zero test" else "secondary",
    ):
        cambia_pagina("Zero test")

    if st.button(
        "Test prodotti scorrimento",
        icon=":material/downhill_skiing:",
        key="menu_test_scorrimento",
        use_container_width=True,
        type="primary" if pagina == "Test prodotti scorrimento" else "secondary",
        help="Sezione test prodotti scorrimento · skating",
    ):
        cambia_pagina("Test prodotti scorrimento")

    if st.button(
        "Test scioline di tenuta",
        icon=":material/nordic_walking:",
        key="menu_test_tenuta",
        use_container_width=True,
        type="primary" if pagina == "Test scioline di tenuta" else "secondary",
        help="Sezione test scioline di tenuta · tecnica classica",
    ):
        cambia_pagina("Test scioline di tenuta")

    if st.button(
        "Test rigature manuali",
        icon=":material/build:",
        key="menu_test_rigature",
        use_container_width=True,
        type="primary" if pagina == "Test rigature manuali" else "secondary",
    ):
        cambia_pagina("Test rigature manuali")


with st.sidebar.expander(
    "Prodotti",
    expanded=pagina in [
        "Prodotti di scorrimento",
        "Scioline di tenuta",
        "Rigature manuali",
    ],
    icon=":material/inventory_2:",
):
    if st.button(
        "Prodotti di scorrimento",
        icon=":material/show_chart:",
        key="menu_prodotti_scorrimento",
        use_container_width=True,
        type="primary" if pagina == "Prodotti di scorrimento" else "secondary",
    ):
        cambia_pagina("Prodotti di scorrimento")

    if st.button(
        "Scioline di tenuta",
        icon=":material/science:",
        key="menu_prodotti_tenuta",
        use_container_width=True,
        type="primary" if pagina == "Scioline di tenuta" else "secondary",
    ):
        cambia_pagina("Scioline di tenuta")

    if st.button(
        "Rigature manuali",
        icon=":material/build:",
        key="menu_prodotti_rigature",
        use_container_width=True,
        type="primary" if pagina == "Rigature manuali" else "secondary",
    ):
        cambia_pagina("Rigature manuali")


if st.sidebar.button(
    "Trova prodotto migliore",
    icon=":material/search:",
    key="menu_trova_prodotto_migliore",
    use_container_width=True,
    type="primary" if pagina == "Trova prodotto migliore" else "secondary",
):
    cambia_pagina("Trova prodotto migliore")


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
        st.markdown("### Dashboard")
        st.caption("Area lasciata volutamente libera. La costruiremo quando avremo abbastanza test e dati storici da riassumere in modo utile.")

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
                temperatura_aria_txt = st.text_input(
                    "Temperatura aria (°C)", value="0.0"
                )
                temperatura_neve_txt = st.text_input(
                    "Temperatura neve (°C)", value="0.0"
                )
                umidita = st.number_input(
                    "Umidità relativa (%)", min_value=0.0, max_value=100.0,
                    value=70.0, step=1.0
                )
            with c3:
                tipo_neve = st.selectbox(
                    "Tipo neve",
                    [
                        "Nuova", "Vecchia", "Neve trasformata", "Artificiale",
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
                meteo = st.selectbox(
                    "Meteo",
                    METEO_OPZIONI,
                    index=None,
                    placeholder="Seleziona meteo",
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
                            umidita, meteo, tipo_neve, condizione_pista, note, creato_il
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data_sessione.isoformat(),
                        ora_sessione.strftime("%H:%M"),
                        luogo.strip(),
                        _parse_temperatura_1d(temperatura_aria_txt),
                        _parse_temperatura_1d(temperatura_neve_txt),
                        float(umidita),
                        meteo or "",
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
            mostra_sessioni = df[[
                "id", "data", "ora", "luogo", "temperatura_aria",
                "temperatura_neve", "umidita", "meteo", "tipo_neve",
                "condizione_pista", "note"
            ]].copy()
            mostra_sessioni = _formatta_dataframe_temperature_ambientali(mostra_sessioni)
            st.dataframe(
                mostra_sessioni,
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


    elif pagina == "Inserimento test":
        cambia_pagina("Zero test")

    elif pagina == "Zero test":
        # ============================================================
        # STORICO ZERO TEST - stessa logica visiva dello Storico Sector
        # ============================================================
        st.markdown(
            """
            <style>
            [data-testid="stMain"] [data-testid="stExpander"] > details[open] {
                background: #edf1f4 !important;
                border-color: #cfd8df !important;
                border-radius: 14px !important;
            }

            [data-testid="stMain"] [data-testid="stExpander"] > details[open] > summary {
                background: #e8edf1 !important;
                border-radius: 14px 14px 0 0 !important;
            }

            [data-testid="stMain"]:has([data-testid="stExpander"] > details[open])
            [data-testid="stElementContainer"]:not(:has([data-testid="stExpander"] > details[open])):not(details[open] *) {
                filter: blur(9px) brightness(0.78) saturate(0.72);
                opacity: 0.38;
                transition: filter 180ms ease, opacity 180ms ease;
            }

            [data-testid="stMain"]:has([data-testid="stExpander"] > details[open])
            [data-testid="stExpander"] > details:not([open]):not(details[open] *) {
                filter: blur(9px) brightness(0.78) saturate(0.72) !important;
                opacity: 0.38 !important;
                transition: filter 180ms ease, opacity 180ms ease;
            }

            [data-testid="stMain"] [data-testid="stElementContainer"]:has(
                [data-testid="stExpander"] > details[open]
            ),
            [data-testid="stMain"] [data-testid="stExpander"]:has(> details[open]),
            [data-testid="stMain"] [data-testid="stExpander"] > details[open] {
                filter: none !important;
                opacity: 1 !important;
            }

            .zero-history-classification {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.65rem;
                margin: 0.35rem 0 1rem 0;
            }

            .zero-history-classification-item {
                background: #f7f9fa;
                border: 1px solid #d8dde3;
                border-radius: 10px;
                padding: 0.62rem 0.72rem;
                min-height: 66px;
            }

            .zero-history-classification-label {
                color: #7a8a96;
                font-size: 0.68rem;
                font-weight: 800;
                letter-spacing: 0.055em;
                text-transform: uppercase;
                margin-bottom: 0.2rem;
            }

            .zero-history-classification-value {
                color: #263238;
                font-size: 0.86rem;
                font-weight: 600;
                line-height: 1.35;
            }

            @media (max-width: 900px) {
                .zero-history-classification {
                    grid-template-columns: 1fr;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="section-title">Storico zero test</div>',
            unsafe_allow_html=True,
        )
        if st.session_state.get("zero_history_notice"):
            st.success(st.session_state.pop("zero_history_notice"))
        st.write(
            "Database cronologico degli Zero Test. Ogni test resta compatto e può essere "
            "aperto per visualizzare condizioni neve, quattro passaggi di ogni paio e "
            "analisi di similarità."
        )
        st.caption(
            "I test sono ordinati automaticamente dal più recente al più vecchio. "
            "Media, deviazione standard, paio più simile e Δ vengono calcolati dai quattro passaggi."
        )

        _stile_moduli_test()
        zero_form_open = bool(
            st.session_state.get("zero_edit_session_id") is not None
            or st.session_state.get("zero_insert_open", False)
        )
        with st.expander(
            "＋ Nuovo / modifica Zero test",
            expanded=zero_form_open,
        ):
            render_form_zero_test()

        df_zero_storico = leggi_df(
            """
            SELECT
                s.id,
                s.data,
                s.ora,
                s.luogo,
                s.temperatura_aria,
                s.temperatura_neve,
                s.umidita,
                s.meteo,
                s.snow_origine,
                s.snow_consistenza,
                s.snow_umidita,
                s.snow_forma_grano,
                s.snow_granulometria,
                s.snow_caratteristiche,
                s.zero_batteria,
                s.zero_modello_sci,
                s.note,
                s.creato_il,
                COUNT(DISTINCT z.sci_id) AS paia_testati,
                COUNT(z.id) AS passaggi_registrati
            FROM sessioni s
            JOIN zero_test z ON z.sessione_id = s.id
            GROUP BY s.id
            ORDER BY s.data DESC, COALESCE(s.ora, '') DESC, s.id DESC
            """
        )

        df_zero_prove_storico = leggi_df(
            """
            SELECT
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
            ORDER BY z.sessione_id, s.codice, z.prova_numero
            """
        )

        if df_zero_storico.empty:
            st.info("Non ci sono ancora Zero Test registrati.")
        else:
            st.markdown("#### Filtri")
            filtro1, filtro2, filtro3 = st.columns(3)

            with filtro1:
                luoghi_zero = ["Tutti"] + sorted(
                    [
                        str(v).strip()
                        for v in df_zero_storico["luogo"].dropna().unique().tolist()
                        if str(v).strip()
                    ]
                )
                storico_zero_luogo = st.selectbox(
                    "Luogo",
                    luoghi_zero,
                    key="zero_storico_filtro_luogo",
                )

            consistenze_zero = [
                "Compatta",
                "Sfarinata / Soffice",
                "Sgranata",
                "Ghiacciata",
                "Molle su fondo compatto",
                "Soffice su fondo compatto",
                "Molle",
            ]
            with filtro2:
                storico_zero_consistenza = st.selectbox(
                    "Consistenza",
                    ["Tutte"] + consistenze_zero,
                    key="zero_storico_filtro_consistenza",
                )

            with filtro3:
                storico_zero_intervallo = st.selectbox(
                    "Intervallo",
                    [
                        "Tutti",
                        "Ultimi 15 giorni",
                        "Ultimi 30 giorni",
                        "Ultimi 90 giorni",
                        "Periodo personalizzato",
                    ],
                    key="zero_storico_filtro_intervallo",
                )

            date_zero = pd.to_datetime(df_zero_storico["data"], errors="coerce").dt.normalize()
            date_valide_zero = date_zero.dropna()
            intervallo_zero_personalizzato = None

            if storico_zero_intervallo == "Periodo personalizzato":
                if not date_valide_zero.empty:
                    data_min_zero = date_valide_zero.min().date()
                    data_max_zero = date_valide_zero.max().date()
                else:
                    oggi_zero = pd.Timestamp.today().normalize().date()
                    data_min_zero = oggi_zero
                    data_max_zero = oggi_zero

                intervallo_zero_personalizzato = st.date_input(
                    "Periodo personalizzato",
                    value=(data_min_zero, data_max_zero),
                    min_value=data_min_zero,
                    max_value=data_max_zero,
                    key="zero_storico_periodo_personalizzato",
                    format="DD/MM/YYYY",
                )

            df_zero_filtrato = df_zero_storico.copy()
            df_zero_filtrato["_data_filtraggio"] = pd.to_datetime(
                df_zero_filtrato["data"], errors="coerce"
            ).dt.normalize()

            if storico_zero_luogo != "Tutti":
                df_zero_filtrato = df_zero_filtrato[
                    df_zero_filtrato["luogo"].astype(str).str.strip() == storico_zero_luogo
                ]

            if storico_zero_consistenza != "Tutte":
                def _match_consistenza_zero(valore):
                    voci = {v.strip() for v in str(valore or "").split(",") if v.strip()}
                    return "Tutte" in voci or storico_zero_consistenza in voci

                df_zero_filtrato = df_zero_filtrato[
                    df_zero_filtrato["snow_consistenza"].apply(_match_consistenza_zero)
                ]

            if storico_zero_intervallo in {
                "Ultimi 15 giorni", "Ultimi 30 giorni", "Ultimi 90 giorni"
            }:
                giorni_zero = {
                    "Ultimi 15 giorni": 15,
                    "Ultimi 30 giorni": 30,
                    "Ultimi 90 giorni": 90,
                }[storico_zero_intervallo]
                oggi_zero = pd.Timestamp.today().normalize()
                inizio_zero = oggi_zero - pd.Timedelta(days=giorni_zero - 1)
                df_zero_filtrato = df_zero_filtrato[
                    (df_zero_filtrato["_data_filtraggio"] >= inizio_zero)
                    & (df_zero_filtrato["_data_filtraggio"] <= oggi_zero)
                ]
            elif storico_zero_intervallo == "Periodo personalizzato":
                if (
                    isinstance(intervallo_zero_personalizzato, (tuple, list))
                    and len(intervallo_zero_personalizzato) == 2
                ):
                    inizio_zero = pd.Timestamp(intervallo_zero_personalizzato[0]).normalize()
                    fine_zero = pd.Timestamp(intervallo_zero_personalizzato[1]).normalize()
                    if inizio_zero > fine_zero:
                        inizio_zero, fine_zero = fine_zero, inizio_zero
                    df_zero_filtrato = df_zero_filtrato[
                        (df_zero_filtrato["_data_filtraggio"] >= inizio_zero)
                        & (df_zero_filtrato["_data_filtraggio"] <= fine_zero)
                    ]

            df_zero_filtrato = df_zero_filtrato.drop(columns=["_data_filtraggio"], errors="ignore")
            st.write(f"Zero test visualizzati: **{len(df_zero_filtrato)}**")

            if df_zero_filtrato.empty:
                st.warning("Nessuno Zero Test corrisponde ai filtri selezionati.")
            else:
                st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)

                zero_prove_per_sessione = {
                    int(sessione_id): gruppo.reset_index(drop=True)
                    for sessione_id, gruppo in df_zero_prove_storico.groupby("sessione_id", sort=False)
                }

                for _, sessione_zero in df_zero_filtrato.iterrows():
                    sessione_id_zero = int(sessione_zero["id"])
                    try:
                        data_zero_label = pd.to_datetime(sessione_zero["data"]).strftime("%d/%m/%Y")
                    except Exception:
                        data_zero_label = str(sessione_zero.get("data") or "")

                    ora_zero_label = str(sessione_zero.get("ora") or "").strip()
                    luogo_zero_label = str(sessione_zero.get("luogo") or "—").strip()
                    paia_zero_label = int(sessione_zero.get("paia_testati") or 0)
                    batteria_zero_label = str(sessione_zero.get("zero_batteria") or "").strip() or "Batteria non specificata"
                    titolo_zero = f"{data_zero_label} · {luogo_zero_label} · {batteria_zero_label}"

                    with st.expander(titolo_zero, expanded=False):
                        df_prove_sessione = zero_prove_per_sessione.get(
                            sessione_id_zero,
                            pd.DataFrame(columns=df_zero_prove_storico.columns),
                        )
                        df_tabella_zero = tabella_zero_test_da_risultati(df_prove_sessione)
                        coppia_vicina = coppia_zero_test_piu_vicina(df_tabella_zero)

                        if coppia_vicina:
                            paio_a, paio_b, delta_vicino = coppia_vicina
                            coppia_label = f"{paio_a} ↔ {paio_b} · Δ {delta_vicino:.2f} s"
                        else:
                            coppia_label = "—"

                        met1, met2, met3 = st.columns(3)
                        with met1:
                            st.metric("Paia testati", paia_zero_label)
                        with met2:
                            st.metric("Passaggi registrati", int(sessione_zero.get("passaggi_registrati") or 0))
                        with met3:
                            st.metric("Coppia più vicina", coppia_label)

                        st.markdown("##### Sessione")
                        info1, info2, info3 = st.columns(3)
                        with info1:
                            st.markdown(f"**Luogo:** {luogo_zero_label or '—'}")
                            st.markdown(f"**Data:** {data_zero_label}")
                            st.markdown(f"**Ora:** {ora_zero_label or '—'}")
                            modello_zero = str(sessione_zero.get("zero_modello_sci") or "").strip()
                            st.markdown(f"**Modello sci:** {modello_zero or '—'}")
                        with info2:
                            t_aria = sessione_zero.get("temperatura_aria")
                            t_neve = sessione_zero.get("temperatura_neve")
                            t_aria_txt = f"{float(t_aria):.1f} °C" if pd.notna(t_aria) else "—"
                            t_neve_txt = f"{float(t_neve):.1f} °C" if pd.notna(t_neve) else "—"
                            st.markdown(f"**Temperatura aria:** {t_aria_txt}")
                            st.markdown(f"**Temperatura neve:** {t_neve_txt}")
                        with info3:
                            umidita_zero = sessione_zero.get("umidita")
                            ur_txt = f"{float(umidita_zero):.0f} %" if pd.notna(umidita_zero) else "Non disponibile"
                            st.markdown(f"**Umidità relativa:** {ur_txt}")
                            meteo_zero = str(sessione_zero.get("meteo") or "").strip()
                            st.markdown(f"**Meteo:** {meteo_zero or '—'}")
                            note_zero = str(sessione_zero.get("note") or "").strip()
                            st.markdown(f"**Note:** {note_zero or '—'}")

                        st.markdown("##### Classificazione neve")
                        classificazione_zero = [
                            ("Origine", sessione_zero.get("snow_origine")),
                            ("Consistenza", sessione_zero.get("snow_consistenza")),
                            ("Umidità neve", sessione_zero.get("snow_umidita")),
                            ("Forma grano", sessione_zero.get("snow_forma_grano")),
                            ("Granulometria", sessione_zero.get("snow_granulometria")),
                            ("Caratteristiche", sessione_zero.get("snow_caratteristiche")),
                        ]
                        class_html = '<div class="zero-history-classification">'
                        for etichetta_zero, valore_zero in classificazione_zero:
                            valore_pulito = str(valore_zero or "").strip() or "—"
                            class_html += (
                                '<div class="zero-history-classification-item">'
                                f'<div class="zero-history-classification-label">{html_escape(etichetta_zero)}</div>'
                                f'<div class="zero-history-classification-value">{html_escape(valore_pulito)}</div>'
                                '</div>'
                            )
                        class_html += '</div>'
                        st.markdown(class_html, unsafe_allow_html=True)

                        st.markdown("##### Dettaglio zero test")
                        st.dataframe(
                            df_tabella_zero,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Paio": st.column_config.NumberColumn("Paio", format="%d", width="small"),
                                "P1 (s)": st.column_config.NumberColumn("P1", format="%.2f", width="small"),
                                "P2 (s)": st.column_config.NumberColumn("P2", format="%.2f", width="small"),
                                "P3 (s)": st.column_config.NumberColumn("P3", format="%.2f", width="small"),
                                "P4 (s)": st.column_config.NumberColumn("P4", format="%.2f", width="small"),
                                "Media (s)": st.column_config.NumberColumn("Media", format="%.2f", width="small"),
                                "SD (s)": st.column_config.NumberColumn("Dev. std.", format="%.2f", width="small"),
                                "Paio più simile": st.column_config.NumberColumn("Paio simile", format="%d", width="medium"),
                                "Δ dal più simile (s)": st.column_config.NumberColumn("Δ simile", format="%.2f", width="medium"),
                                "Note": st.column_config.TextColumn("Note", width="medium"),
                            },
                        )

                        st.markdown('<div style="height:0.75rem"></div>', unsafe_allow_html=True)
                        az1, az2 = st.columns(2)
                        with az1:
                            if st.button(
                                "Modifica test",
                                icon=":material/edit:",
                                use_container_width=True,
                                key=f"edit_zero_history_{sessione_id_zero}",
                            ):
                                st.session_state["zero_edit_session_id"] = int(sessione_id_zero)
                                st.session_state["zero_insert_open"] = True
                                st.rerun()
                        with az2:
                            if st.button(
                                "Elimina test",
                                icon=":material/delete:",
                                use_container_width=True,
                                key=f"delete_zero_history_{sessione_id_zero}",
                            ):
                                st.session_state[f"confirm_delete_zero_{sessione_id_zero}"] = True
                                st.rerun()

                        if st.session_state.get(f"confirm_delete_zero_{sessione_id_zero}", False):
                            st.warning(
                                "Confermi l'eliminazione di questo Zero Test? I tempi registrati verranno cancellati. "
                                "La sessione ambientale rimarrà disponibile per eventuali altri test."
                            )
                            conf1, conf2 = st.columns(2)
                            with conf1:
                                if st.button(
                                    "Conferma eliminazione",
                                    type="primary",
                                    use_container_width=True,
                                    key=f"confirm_delete_zero_yes_{sessione_id_zero}",
                                ):
                                    esegui(
                                        "DELETE FROM zero_test WHERE sessione_id = ?",
                                        (int(sessione_id_zero),),
                                    )
                                    st.session_state.pop(f"confirm_delete_zero_{sessione_id_zero}", None)
                                    st.session_state["zero_history_notice"] = "Zero test eliminato correttamente."
                                    st.rerun()
                            with conf2:
                                if st.button(
                                    "Annulla",
                                    use_container_width=True,
                                    key=f"confirm_delete_zero_no_{sessione_id_zero}",
                                ):
                                    st.session_state.pop(f"confirm_delete_zero_{sessione_id_zero}", None)
                                    st.rerun()

    elif pagina == "Test prodotti scorrimento":
        mostra_banner(
            "Test prodotti scorrimento",
            "Database cronologico dei test di scorrimento. Inserimento e storico nello stesso punto.",
        )
        _stile_moduli_test()

        st.markdown('<div class="section-title">Storico test prodotti scorrimento</div>', unsafe_allow_html=True)
        if st.session_state.get("scroll_history_notice"):
            st.success(st.session_state.pop("scroll_history_notice"))
        st.write(
            "Archivio dei test prodotti scorrimento. Apri un test per vedere condizioni, preparazioni e classifica."
        )

        scroll_edit_active = st.session_state.get("scroll_edit_session_id") is not None
        scroll_form_label = "✎ Modifica test prodotti scorrimento" if scroll_edit_active else "＋ Nuovo test prodotti scorrimento"
        with st.expander(scroll_form_label, expanded=scroll_edit_active):
            render_form_test_scorrimento()

        df_scroll_storico = leggi_df(
            """
            SELECT
                s.id, s.data, s.ora, s.luogo, s.temperatura_aria, s.temperatura_neve,
                s.umidita, s.meteo, s.snow_origine, s.snow_consistenza, s.snow_umidita,
                s.snow_forma_grano, s.snow_granulometria, s.snow_caratteristiche,
                s.zero_modello_sci, s.tipo_test, s.categoria_test_scorrimento, s.zero_riferimento_id, s.note, s.creato_il,
                COUNT(a.id) AS righe_test
            FROM sessioni s
            LEFT JOIN test_scorrimento_aste a ON a.sessione_id = s.id
            WHERE COALESCE(s.tipo_test, '') LIKE 'Test prodotti scorrimento%'
            GROUP BY s.id
            ORDER BY s.data DESC, COALESCE(s.ora, '') DESC, s.id DESC
            """
        )

        if df_scroll_storico.empty:
            st.info("Non ci sono ancora test prodotti scorrimento registrati.")
        else:
            st.markdown("#### Filtri")
            fs1, fs2, fs3 = st.columns(3)
            with fs1:
                luoghi = ["Tutti"] + sorted([str(v).strip() for v in df_scroll_storico["luogo"].dropna().unique().tolist() if str(v).strip()])
                filtro_luogo_scroll = st.selectbox("Luogo", luoghi, key="scroll_history_place")
            with fs2:
                metodi = ["Tutti"] + sorted([str(v).replace("Test prodotti scorrimento · ", "").strip() for v in df_scroll_storico["tipo_test"].dropna().unique().tolist() if str(v).strip()])
                filtro_metodo_scroll = st.selectbox("Metodo", metodi, key="scroll_history_method")
            with fs3:
                filtro_intervallo_scroll = st.selectbox("Intervallo", ["Tutti", "Ultimi 15 giorni", "Ultimi 30 giorni", "Ultimi 90 giorni"], key="scroll_history_period")

            df_scroll_filtrato = df_scroll_storico.copy()
            if filtro_luogo_scroll != "Tutti":
                df_scroll_filtrato = df_scroll_filtrato[df_scroll_filtrato["luogo"].astype(str).str.strip() == filtro_luogo_scroll]
            if filtro_metodo_scroll != "Tutti":
                df_scroll_filtrato = df_scroll_filtrato[df_scroll_filtrato["tipo_test"].astype(str).str.contains(filtro_metodo_scroll, regex=False)]
            if filtro_intervallo_scroll != "Tutti":
                giorni = {"Ultimi 15 giorni":15, "Ultimi 30 giorni":30, "Ultimi 90 giorni":90}[filtro_intervallo_scroll]
                d = pd.to_datetime(df_scroll_filtrato["data"], errors="coerce").dt.normalize()
                oggi = pd.Timestamp.today().normalize()
                df_scroll_filtrato = df_scroll_filtrato[(d >= oggi-pd.Timedelta(days=giorni-1)) & (d <= oggi)]

            st.write(f"Test visualizzati: **{len(df_scroll_filtrato)}**")

            for _, test in df_scroll_filtrato.iterrows():
                sid = int(test["id"])
                data_label = _formatta_data_storico(test.get("data")) if '_formatta_data_storico' in globals() else str(test.get("data") or "")
                luogo = str(test.get("luogo") or "—")
                metodo = str(test.get("tipo_test") or "Test prodotti scorrimento").replace("Test prodotti scorrimento · ", "")
                titolo = f"{data_label} · {luogo} · {metodo}"
                with st.expander(titolo):
                    df_righe = leggi_df(
                        """
                        SELECT a.posizione, a.numero_sci,
                               a.base_prodotto_id AS base_id,
                               a.paraffina_prodotto_id AS paraffina_id,
                               a.top_coating_prodotto_id AS top_coating_id,
                               a.liquido_prodotto_id AS liquido_id,
                               COALESCE(pb.marca || ' - ' || pb.nome, pb.nome, '—') AS base,
                               pb.foto_data AS base_foto, pb.foto_mime AS base_mime,
                               COALESCE(pp.marca || ' - ' || pp.nome, pp.nome, '—') AS paraffina,
                               pp.foto_data AS paraffina_foto, pp.foto_mime AS paraffina_mime,
                               COALESCE(pt.marca || ' - ' || pt.nome, pt.nome, '—') AS top_coating,
                               pt.foto_data AS top_foto, pt.foto_mime AS top_mime,
                               COALESCE(pl.marca || ' - ' || pl.nome, pl.nome, '—') AS liquido,
                               pl.foto_data AS liquido_foto, pl.foto_mime AS liquido_mime,
                               a.note
                        FROM test_scorrimento_aste a
                        LEFT JOIN catalogo_prodotti pb ON pb.id = a.base_prodotto_id
                        LEFT JOIN catalogo_prodotti pp ON pp.id = a.paraffina_prodotto_id
                        LEFT JOIN catalogo_prodotti pt ON pt.id = a.top_coating_prodotto_id
                        LEFT JOIN catalogo_prodotti pl ON pl.id = a.liquido_prodotto_id
                        WHERE a.sessione_id = ?
                        ORDER BY a.id
                        """, (sid,)
                    )
                    combinazioni_testate = len(df_righe) if not df_righe.empty else int(test.get("righe_test") or 0)

                    tipo_prodotti_testati_storico = _normalizza_tipo_prodotti_test_scorrimento(
                        test.get("categoria_test_scorrimento")
                    )
                    confronto_label = tipo_prodotti_testati_storico.replace("Test ", "", 1).capitalize()

                    c1, c2, c3, c4, c5 = st.columns(5)
                    with c1:
                        st.metric("Metodo test", metodo)
                    with c2:
                        st.metric("Confronto", confronto_label)
                    with c3:
                        st.metric("Prodotti/combinazioni testati", combinazioni_testate)
                    with c4:
                        st.metric("T aria °C", _formatta_temperatura_1d(test.get("temperatura_aria")))
                    with c5:
                        st.metric("T neve °C", _formatta_temperatura_1d(test.get("temperatura_neve")))

                    st.markdown("##### Sessione")
                    sc1, sc2, sc3 = st.columns(3)
                    with sc1:
                        st.write(f"**Data:** {data_label}")
                        st.write(f"**Luogo:** {luogo}")
                    with sc2:
                        st.write(f"**Ora:** {str(test.get('ora') or '—')[:5]}")
                        st.write(f"**Meteo:** {str(test.get('meteo') or '—')}")
                    with sc3:
                        ur = test.get("umidita")
                        st.write(f"**UR:** {'—' if pd.isna(ur) else str(int(round(float(ur)))) + ' %'}")
                        st.write(f"**Modello sci:** {str(test.get('zero_modello_sci') or '—')}")

                    st.markdown(
                        """
                        <style>
                        .scroll-snow-classification {
                            display: grid;
                            grid-template-columns: repeat(3, minmax(0, 1fr));
                            gap: 0.65rem;
                            margin: 0.35rem 0 1rem 0;
                        }
                        .scroll-snow-classification-item {
                            background: #f7f9fa;
                            border: 1px solid #d8dde3;
                            border-radius: 10px;
                            padding: 0.62rem 0.72rem;
                            min-height: 66px;
                        }
                        .scroll-snow-classification-label {
                            color: #7a8a96;
                            font-size: 0.68rem;
                            font-weight: 800;
                            letter-spacing: 0.055em;
                            text-transform: uppercase;
                            margin-bottom: 0.2rem;
                        }
                        .scroll-snow-classification-value {
                            color: #263238;
                            font-size: 0.86rem;
                            font-weight: 600;
                            line-height: 1.35;
                        }
                        @media (max-width: 900px) {
                            .scroll-snow-classification {
                                grid-template-columns: 1fr;
                            }
                        }
                        </style>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown("##### Tipologia neve")
                    classificazione_scroll = [
                        ("Origine", test.get("snow_origine")),
                        ("Consistenza", test.get("snow_consistenza")),
                        ("Umidità neve", test.get("snow_umidita")),
                        ("Forma grano", test.get("snow_forma_grano")),
                        ("Granulometria", test.get("snow_granulometria")),
                        ("Caratteristiche", test.get("snow_caratteristiche")),
                    ]
                    class_html_scroll = '<div class="scroll-snow-classification">'
                    for etichetta_scroll, valore_scroll in classificazione_scroll:
                        valore_pulito_scroll = str(valore_scroll or "").strip() or "—"
                        class_html_scroll += (
                            '<div class="scroll-snow-classification-item">'
                            f'<div class="scroll-snow-classification-label">{html_escape(etichetta_scroll)}</div>'
                            f'<div class="scroll-snow-classification-value">{html_escape(valore_pulito_scroll)}</div>'
                            '</div>'
                        )
                    class_html_scroll += '</div>'
                    st.markdown(class_html_scroll, unsafe_allow_html=True)

                    if not df_righe.empty:
                        st.markdown("##### Podio test")
                        if tipo_prodotti_testati_storico != "Test combinazioni":
                            st.caption(
                                "Sul podio sono mostrati solo i prodotti oggetto del confronto: "
                                f"**{confronto_label}**. La tabella sotto mantiene la preparazione completa dello sci."
                            )
                        _render_test_scorrimento_podium(
                            df_righe,
                            tipo_prodotti_testati_storico,
                        )

                        st.markdown("##### Dettaglio test")

                        ordine_key = f"scroll_history_order_{sid}"
                        if ordine_key not in st.session_state:
                            st.session_state[ordine_key] = "sci"

                        ord1, ord2, ord_spacer = st.columns([1.35, 1.15, 4.5])
                        with ord1:
                            if st.button(
                                "↕ Riordina per classifica",
                                use_container_width=True,
                                key=f"scroll_history_rank_{sid}",
                            ):
                                st.session_state[ordine_key] = "classifica"
                                st.rerun()
                        with ord2:
                            if st.button(
                                "↺ Ordine sci",
                                use_container_width=True,
                                key=f"scroll_history_ski_{sid}",
                            ):
                                st.session_state[ordine_key] = "sci"
                                st.rerun()

                        df_righe_visual = df_righe.copy()
                        if st.session_state.get(ordine_key) == "classifica":
                            df_righe_visual["_pos_sort"] = pd.to_numeric(
                                df_righe_visual["posizione"], errors="coerce"
                            )
                            df_righe_visual = df_righe_visual.sort_values(
                                by=["_pos_sort"], na_position="last", kind="stable"
                            ).drop(columns=["_pos_sort"]).reset_index(drop=True)
                        else:
                            df_righe_visual["_ski_sort"] = df_righe_visual["numero_sci"].apply(
                                _chiave_ordine_numero_sci
                            )
                            df_righe_visual = df_righe_visual.sort_values(
                                by=["_ski_sort"], kind="stable"
                            ).drop(columns=["_ski_sort"]).reset_index(drop=True)

                        stato_ordine = (
                            "Classifica per posizione"
                            if st.session_state.get(ordine_key) == "classifica"
                            else "Ordine per numero sci"
                        )
                        st.caption(f"Visualizzazione: {stato_ordine}")
                        _render_test_scorrimento_detail_table(df_righe_visual)

                    st.markdown(
                        """
                        <style>
                        /* Azioni storico test: stessa gerarchia visiva usata in Sector G2 Lab */
                        div[class*="st-key-download_scroll_test_"] button {
                            height: 48px !important;
                            background: #eef1f4 !important;
                            border: 1px solid #c8cfd6 !important;
                            border-radius: 5px !important;
                            box-shadow: none !important;
                            font-weight: 600 !important;
                        }
                        div[class*="st-key-download_scroll_test_"] button p,
                        div[class*="st-key-download_scroll_test_"] button svg {
                            color: #37474f !important;
                            fill: #37474f !important;
                            font-weight: 600 !important;
                        }
                        div[class*="st-key-download_scroll_test_"] button:hover {
                            background: #e2e7eb !important;
                            border-color: #aeb8bf !important;
                        }

                        div[class*="st-key-edit_scroll_history_"] button {
                            height: 48px !important;
                            background: #00a7e1 !important;
                            border: 1px solid #00a7e1 !important;
                            border-radius: 5px !important;
                            box-shadow: none !important;
                            font-weight: 600 !important;
                        }
                        div[class*="st-key-edit_scroll_history_"] button p,
                        div[class*="st-key-edit_scroll_history_"] button svg {
                            color: #ffffff !important;
                            fill: #ffffff !important;
                            font-weight: 600 !important;
                        }
                        div[class*="st-key-edit_scroll_history_"] button:hover {
                            background: #0095c9 !important;
                            border-color: #0095c9 !important;
                        }

                        div[class*="st-key-delete_scroll_history_"] button {
                            height: 48px !important;
                            background: #ffffff !important;
                            border: 1px solid #d9534f !important;
                            border-radius: 5px !important;
                            box-shadow: none !important;
                            font-weight: 600 !important;
                        }
                        div[class*="st-key-delete_scroll_history_"] button p,
                        div[class*="st-key-delete_scroll_history_"] button svg {
                            color: #d9534f !important;
                            fill: #d9534f !important;
                            font-weight: 600 !important;
                        }
                        div[class*="st-key-delete_scroll_history_"] button:hover {
                            background: #d9534f !important;
                            border-color: #d9534f !important;
                        }
                        div[class*="st-key-delete_scroll_history_"] button:hover p,
                        div[class*="st-key-delete_scroll_history_"] button:hover svg {
                            color: #ffffff !important;
                            fill: #ffffff !important;
                        }

                        div[class*="st-key-confirm_scroll_yes_"] button {
                            height: 46px !important;
                            background: #d9534f !important;
                            border: 1px solid #d9534f !important;
                            color: #ffffff !important;
                            border-radius: 5px !important;
                            font-weight: 600 !important;
                        }
                        div[class*="st-key-confirm_scroll_yes_"] button p,
                        div[class*="st-key-confirm_scroll_yes_"] button svg {
                            color: #ffffff !important;
                            fill: #ffffff !important;
                        }
                        </style>
                        """,
                        unsafe_allow_html=True,
                    )

                    try:
                        pdf_test_scorrimento = _crea_pdf_test_scorrimento(test, df_righe)
                        errore_pdf_test = None
                    except Exception as exc:
                        pdf_test_scorrimento = b""
                        errore_pdf_test = str(exc)

                    st.markdown('<div style="height:0.45rem"></div>', unsafe_allow_html=True)
                    download_c, edit_c, delete_c = st.columns(3)
                    with download_c:
                        st.download_button(
                            "Scarica test",
                            data=pdf_test_scorrimento,
                            file_name=_nome_file_pdf_test_scorrimento(test),
                            mime="application/pdf",
                            icon=":material/download:",
                            use_container_width=True,
                            disabled=bool(errore_pdf_test),
                            key=f"download_scroll_test_{sid}",
                        )
                    with edit_c:
                        if st.button(
                            "Modifica test",
                            icon=":material/edit:",
                            use_container_width=True,
                            key=f"edit_scroll_history_{sid}",
                        ):
                            st.session_state["scroll_edit_session_id"] = sid
                            st.session_state.pop("scroll_edit_loaded_id", None)
                            for k in ["scroll_rods_table_data", "scroll_rods_table_n"]:
                                st.session_state.pop(k, None)
                            st.rerun()
                    with delete_c:
                        if st.button(
                            "Elimina test",
                            icon=":material/delete:",
                            use_container_width=True,
                            key=f"delete_scroll_history_{sid}",
                        ):
                            st.session_state[f"confirm_delete_scroll_{sid}"] = True
                            st.rerun()

                    if errore_pdf_test:
                        st.caption(f"PDF non disponibile: {errore_pdf_test}")

                    if st.session_state.get(f"confirm_delete_scroll_{sid}", False):
                        st.warning("Confermi l'eliminazione definitiva di questo test prodotti scorrimento?")
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            if st.button(
                                "Conferma eliminazione",
                                icon=":material/delete_forever:",
                                use_container_width=True,
                                key=f"confirm_scroll_yes_{sid}",
                            ):
                                esegui("DELETE FROM test_scorrimento_aste WHERE sessione_id = ?", (sid,))
                                esegui("DELETE FROM sessioni WHERE id = ?", (sid,))
                                st.session_state.pop(f"confirm_delete_scroll_{sid}", None)
                                _invalida_cache_dati()
                                st.session_state["scroll_history_notice"] = "Test prodotti scorrimento eliminato correttamente."
                                st.rerun()
                        with dc2:
                            if st.button(
                                "Annulla",
                                icon=":material/close:",
                                use_container_width=True,
                                key=f"confirm_scroll_no_{sid}",
                            ):
                                st.session_state.pop(f"confirm_delete_scroll_{sid}", None)
                                st.rerun()

    elif pagina == "Test rigature manuali":
        mostra_banner(
            "Test rigature manuali",
            "Database dei test rigature manuali. Il modulo di inserimento verrà configurato nel prossimo passaggio.",
        )
        st.info("La struttura di inserimento dei test rigature manuali verrà definita in un passaggio successivo.")

    elif pagina == "Test scioline di tenuta":
        mostra_banner(
            "Test scioline di tenuta",
            "Database cronologico dei test di tenuta. Il nuovo modulo di inserimento verrà costruito direttamente in questa pagina.",
        )
        st.markdown('<div class="section-title">Storico test scioline di tenuta</div>', unsafe_allow_html=True)
        st.caption("Questa pagina è ora solo archivio. Quando definiamo il nuovo inserimento, comparirà in una tendina in alto come per Zero test e prodotti scorrimento.")

        df_tenuta_storico = leggi_df(
            """
            SELECT s.id, s.data, s.ora, s.luogo, s.temperatura_aria, s.temperatura_neve,
                   s.umidita, s.meteo, COUNT(t.id) AS n_test
            FROM sessioni s
            JOIN test_tenuta t ON t.sessione_id = s.id
            GROUP BY s.id
            ORDER BY s.data DESC, COALESCE(s.ora, '') DESC, s.id DESC
            """
        )
        if df_tenuta_storico.empty:
            st.info("Non ci sono ancora test scioline di tenuta registrati.")
        else:
            for _, sess in df_tenuta_storico.iterrows():
                sid = int(sess["id"])
                data_label = str(sess.get("data") or "—")
                luogo = str(sess.get("luogo") or "—")
                with st.expander(f"{data_label} · {luogo} · {int(sess.get('n_test') or 0)} prove"):
                    df_det = leggi_df(
                        """
                        SELECT t.id, COALESCE(sc.codice, '—') AS sci, t.preparazione,
                               t.tenuta, t.scorrevolezza, t.facilita_calcio, t.durata, t.note
                        FROM test_tenuta t
                        LEFT JOIN sci sc ON sc.id = t.sci_id
                        WHERE t.sessione_id = ?
                        ORDER BY t.id DESC
                        """, (sid,)
                    )
                    st.dataframe(df_det, use_container_width=True, hide_index=True)

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
            "Catalogo di basi, kick wax e klister con classificazione neve e condizioni di utilizzo.",
            ["Base kick wax", "Base klister", "Base spray", "Kick wax", "Klister"],
        )


    elif pagina == "Rigature manuali":
        pagina_catalogo_prodotti(
            "rigatura",
            "Rigature manuali",
            "Catalogo degli utensili e delle configurazioni di rigatura manuale.",
            ["Lineare", "Incrociata", "V", "Rullo", "Utensile", "Altro"],
        )



    elif pagina == "Trova prodotto migliore":
        pagina_trova_prodotto_migliore()


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
                "Consistenza": "Molle su fondo compatto",
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
            {
                "Origine": "",
                "Consistenza": "Molle",
                "Umidità": "",
                "Forma grano": "",
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
                    se.meteo,
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
                st.dataframe(_formatta_dataframe_temperature_ambientali(df), use_container_width=True, hide_index=True)

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
                    se.meteo,
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
                st.dataframe(_formatta_dataframe_temperature_ambientali(df), use_container_width=True, hide_index=True)

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
                    se.meteo,
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
                st.dataframe(_formatta_dataframe_temperature_ambientali(df), use_container_width=True, hide_index=True)


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
