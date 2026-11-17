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
VERSIONE_DATABASE_APP = 18


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
            snow_fondo TEXT,
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
        CREATE TABLE IF NOT EXISTS test_rigature_aste (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sessione_id INTEGER NOT NULL,
            posizione INTEGER,
            numero_sci TEXT,
            note TEXT,
            creato_il TEXT NOT NULL,
            FOREIGN KEY(sessione_id) REFERENCES sessioni(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS test_rigature_componenti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_rigatura_asta_id INTEGER NOT NULL,
            colonna_numero INTEGER NOT NULL,
            rigatura_prodotto_id INTEGER,
            rigatura_prodotto_id_2 INTEGER,
            direzione TEXT,
            hand_drive INTEGER DEFAULT 0,
            tecnica_sci TEXT,
            zona_da TEXT,
            zona_a TEXT,
            FOREIGN KEY(test_rigatura_asta_id) REFERENCES test_rigature_aste(id),
            FOREIGN KEY(rigatura_prodotto_id) REFERENCES catalogo_prodotti(id),
            FOREIGN KEY(rigatura_prodotto_id_2) REFERENCES catalogo_prodotti(id)
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
            snow_fondo TEXT,
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
            materiale TEXT,
            larghezza_mm REAL,
            angolo_gradi REAL,
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
        "snow_fondo": "TEXT",
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

    colonne_test_rigature_componenti = {
        r[1] for r in conn.execute("PRAGMA table_info(test_rigature_componenti)").fetchall()
    }
    nuove_colonne_test_rigature_componenti = {
        "rigatura_prodotto_id_2": "INTEGER",
        "direzione": "TEXT",
        "hand_drive": "INTEGER DEFAULT 0",
        "tecnica_sci": "TEXT",
        "zona_da": "TEXT",
        "zona_a": "TEXT",
    }
    for nome_colonna, tipo_colonna in nuove_colonne_test_rigature_componenti.items():
        if nome_colonna not in colonne_test_rigature_componenti:
            conn.execute(
                f"ALTER TABLE test_rigature_componenti ADD COLUMN {nome_colonna} {tipo_colonna}"
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
        "snow_fondo": "TEXT",
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
        "materiale": "TEXT",
        "larghezza_mm": "REAL",
        "angolo_gradi": "REAL",
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

    # Separazione definitiva tra consistenza superficiale e fondo sottostante.
    # Migrazione idempotente: converte le vecchie voci combinate senza perdere
    # informazioni e mantiene compatibili i database gia' popolati.
    _consistency_migrations = [
        ('Molle su fondo compatto', 'Molle', 'Compatto'),
        ('Soffice su fondo compatto', 'Soffice, Sfarinata', 'Compatto'),
        ('Soffice su fondo ghiacciato', 'Soffice, Sfarinata', 'Ghiacciato'),
        ('Molle su fondo ghiacciato', 'Molle', 'Ghiacciato'),
        ('Soffice su superficie dura', 'Soffice, Sfarinata', 'Compatto'),
    ]
    for _tabella in ('catalogo_prodotti', 'sessioni'):
        for _vecchia, _superficie, _fondo in _consistency_migrations:
            conn.execute(
                f"UPDATE {_tabella} SET snow_fondo = CASE "
                f"WHEN TRIM(COALESCE(snow_fondo, '')) = '' THEN ? ELSE snow_fondo END, "
                f"snow_consistenza = REPLACE(COALESCE(snow_consistenza, ''), ?, ?) "
                f"WHERE INSTR(COALESCE(snow_consistenza, ''), ?) > 0",
                (_fondo, _vecchia, _superficie, _vecchia),
            )

    # Uniforma la vecchia etichetta invertita.
    for _tabella in ('catalogo_prodotti', 'sessioni'):
        conn.execute(
            f"UPDATE {_tabella} SET snow_consistenza = REPLACE("
            f"COALESCE(snow_consistenza, ''), 'Sfarinata / Soffice', 'Soffice, Sfarinata') "
            f"WHERE INSTR(COALESCE(snow_consistenza, ''), 'Sfarinata / Soffice') > 0"
        )
    for _tabella in ('catalogo_prodotti', 'sessioni'):
        conn.execute(
            f"UPDATE {_tabella} SET snow_consistenza = REPLACE("
            f"COALESCE(snow_consistenza, ''), 'Soffice / Sfarinata', 'Soffice, Sfarinata') "
            f"WHERE INSTR(COALESCE(snow_consistenza, ''), 'Soffice / Sfarinata') > 0"
        )

    # Aggiorna anche il riepilogo legacy usato dai filtri del catalogo.
    for _vecchia, _superficie, _fondo in _consistency_migrations:
        conn.execute(
            "UPDATE catalogo_prodotti SET tipo_neve = REPLACE(COALESCE(tipo_neve, ''), ?, ?) "
            "WHERE INSTR(COALESCE(tipo_neve, ''), ?) > 0",
            (_vecchia, f"{_superficie}, {_fondo}", _vecchia),
        )
    conn.execute(
        "UPDATE catalogo_prodotti SET tipo_neve = REPLACE(COALESCE(tipo_neve, ''), "
        "'Sfarinata / Soffice', 'Soffice, Sfarinata') "
        "WHERE INSTR(COALESCE(tipo_neve, ''), 'Sfarinata / Soffice') > 0"
    )
    conn.execute(
        "UPDATE catalogo_prodotti SET tipo_neve = REPLACE(COALESCE(tipo_neve, ''), "
        "'Soffice / Sfarinata', 'Soffice, Sfarinata') "
        "WHERE INSTR(COALESCE(tipo_neve, ''), 'Soffice / Sfarinata') > 0"
    )

    # I record universali devono restare universali anche nel nuovo campo.
    for _tabella in ('catalogo_prodotti', 'sessioni'):
        conn.execute(
            f"UPDATE {_tabella} SET snow_fondo = 'Tutte' "
            f"WHERE TRIM(COALESCE(snow_fondo, '')) = '' "
            f"AND (TRIM(COALESCE(snow_consistenza, '')) = 'Tutte' "
            f"OR TRIM(COALESCE(tipo_neve, '')) = 'Tutte')"
        )

    # I record storici che non avevano una distinzione del fondo restano
    # esplicitamente non specificati, senza inventare una condizione.
    for _tabella in ('catalogo_prodotti', 'sessioni'):
        conn.execute(
            f"UPDATE {_tabella} SET snow_fondo = 'Omogeneo / n.d.' "
            f"WHERE TRIM(COALESCE(snow_fondo, '')) = '' "
            f"AND TRIM(COALESCE(snow_consistenza, '')) NOT IN ('', 'Tutte')"
        )


    # Aggiorna le categorie delle rigature manuali secondo la nuova nomenclatura.
    _rigatura_type_migrations = [
        ('Incrociata', 'Lineare interrotta X'),
        ('V', 'Lineare interrotta V'),
        ('V cut', 'Lineare interrotta V'),
        ('X cut', 'Lineare interrotta X'),
        ('Altro', 'Special cut'),
        ('Rullo', 'Special cut'),
        ('Utensile', 'Special cut'),
        ('Special', 'Special cut'),
    ]
    for _old_tipo, _new_tipo in _rigatura_type_migrations:
        conn.execute(
            "UPDATE catalogo_prodotti SET tipo = ? "
            "WHERE categoria = 'rigatura' AND TRIM(COALESCE(tipo, '')) = ?",
            (_new_tipo, _old_tipo),
        )


    # Semplificazione definitiva della forma del grano. La migrazione e'
    # idempotente e mantiene compatibili prodotti e sessioni storiche.
    _grain_replacements = [
        ('Nuova (cristalli esagonali)', 'Nuova'),
        ('In trasformazione (forte gradiente)', 'In trasformazione'),
        ('In trasformazione (basso gradiente)', 'In trasformazione'),
        ('Trasformata (cristalli angolari)', 'Trasformata'),
        ('Trasformata (grani arrotondati)', 'Trasformata'),
        ('Mista nuova e trasformata', 'In trasformazione'),
    ]
    for _vecchio_grano, _nuovo_grano in _grain_replacements:
        conn.execute(
            "UPDATE catalogo_prodotti SET snow_forma_grano = REPLACE(COALESCE(snow_forma_grano, ''), ?, ?) "
            "WHERE INSTR(COALESCE(snow_forma_grano, ''), ?) > 0",
            (_vecchio_grano, _nuovo_grano, _vecchio_grano),
        )
        conn.execute(
            "UPDATE catalogo_prodotti SET tipo_neve = REPLACE(COALESCE(tipo_neve, ''), ?, ?) "
            "WHERE INSTR(COALESCE(tipo_neve, ''), ?) > 0",
            (_vecchio_grano, _nuovo_grano, _vecchio_grano),
        )
        conn.execute(
            "UPDATE sessioni SET snow_forma_grano = REPLACE(COALESCE(snow_forma_grano, ''), ?, ?) "
            "WHERE INSTR(COALESCE(snow_forma_grano, ''), ?) > 0",
            (_vecchio_grano, _nuovo_grano, _vecchio_grano),
        )

    # Rimuove duplicati che possono nascere quando due vecchie sottocategorie
    # convergono nella stessa nuova voce.
    for _tabella, _campo in [
        ('catalogo_prodotti', 'snow_forma_grano'),
        ('catalogo_prodotti', 'tipo_neve'),
        ('sessioni', 'snow_forma_grano'),
    ]:
        for _duplicato, _singolo in [
            ('In trasformazione, In trasformazione', 'In trasformazione'),
            ('Trasformata, Trasformata', 'Trasformata'),
            ('Nuova, Nuova', 'Nuova'),
        ]:
            conn.execute(
                f"UPDATE {_tabella} SET {_campo} = REPLACE(COALESCE({_campo}, ''), ?, ?) "
                f"WHERE INSTR(COALESCE({_campo}, ''), ?) > 0",
                (_duplicato, _singolo, _duplicato),
            )

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
    div[class*="st-key-filter_temp_produttore_group_"],
    div[class*="st-key-filter_snow_group_"] {
        background: linear-gradient(180deg, #ffffff 0%, #fbfcfd 100%) !important;
        border: 1px solid #dbe3e8 !important;
        border-radius: 16px !important;
        padding: 1rem 1.05rem 0.95rem 1.05rem !important;
        box-shadow: 0 10px 24px rgba(31, 41, 51, 0.05) !important;
        transition: box-shadow .16s ease, transform .16s ease, border-color .16s ease;
    }

    div[class*="st-key-filter_temp_aria_group_"],
    div[class*="st-key-filter_temp_neve_group_"],
    div[class*="st-key-filter_temp_produttore_group_"] {
        min-height: 196px !important;
    }

    div[class*="st-key-filter_snow_group_"] {
        min-height: 120px !important;
    }

    div[class*="st-key-filter_temp_aria_group_"] {
        border-top: 4px solid #1aa4d8 !important;
    }

    div[class*="st-key-filter_temp_nuova_group_"],
    div[class*="st-key-filter_temp_neve_group_"] {
        border-top: 4px solid #47b4e7 !important;
    }

    div[class*="st-key-filter_temp_trasformata_group_"] {
        border-top: 4px solid #607588 !important;
    }

    div[class*="st-key-filter_temp_produttore_group_"] {
        border-top: 4px solid #8ea1ad !important;
    }

    div[class*="st-key-filter_temp_aria_group_"]:hover,
    div[class*="st-key-filter_temp_neve_group_"]:hover,
    div[class*="st-key-filter_temp_produttore_group_"]:hover,
    div[class*="st-key-filter_snow_group_"]:hover {
        box-shadow: 0 14px 30px rgba(31, 41, 51, 0.08) !important;
        border-color: #cfd8de !important;
        transform: translateY(-1px);
    }

    .catalog-temperature-card-title {
        color: var(--text-main);
        font-size: 1rem;
        font-weight: 750;
        line-height: 1.2;
        margin-bottom: 0.2rem;
        display: flex;
        align-items: center;
        gap: 0.42rem;
    }

    .catalog-temperature-card-title svg {
        width: 16px;
        height: 16px;
        flex: 0 0 16px;
    }

    .catalog-temperature-card-subtitle {
        color: #70808c;
        font-size: 0.77rem;
        line-height: 1.42;
        min-height: 2.2rem;
        margin-bottom: 0.42rem;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stSlider"],
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stSlider"],
    div[class*="st-key-filter_temp_produttore_group_"] [data-testid="stSlider"],
    div[class*="st-key-filter_snow_group_"] [data-testid="stMultiSelect"] {
        margin-top: 0.22rem !important;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stToggle"],
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stToggle"],
    div[class*="st-key-filter_temp_produttore_group_"] [data-testid="stToggle"] {
        margin-bottom: 0.28rem !important;
        padding: 0.05rem 0 0.1rem 0 !important;
        border-bottom: 1px solid #edf1f3;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stToggle"] label,
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stToggle"] label,
    div[class*="st-key-filter_temp_produttore_group_"] [data-testid="stToggle"] label {
        gap: 0.55rem !important;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stToggle"] p,
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stToggle"] p,
    div[class*="st-key-filter_temp_produttore_group_"] [data-testid="stToggle"] p {
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        color: #41515d !important;
    }

    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stRadio"] {
        margin: 0.12rem 0 0.24rem 0 !important;
        padding: 0.38rem 0.5rem !important;
        background: #f7f9fb !important;
        border: 1px solid #e7edf1 !important;
        border-radius: 12px !important;
    }

    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stRadio"] p {
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        color: #4f5f6b !important;
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

    /* Slider più moderno e coerente con il layout filtri temperatura. */
    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stSlider"],
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stSlider"],
    div[class*="st-key-filter_temp_produttore_group_"] [data-testid="stSlider"] {
        padding-top: 0.12rem !important;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stSlider"] > div,
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stSlider"] > div,
    div[class*="st-key-filter_temp_produttore_group_"] [data-testid="stSlider"] > div {
        background: #f7f9fb;
        border: 1px solid #e7edf1;
        border-radius: 12px;
        padding: 0.55rem 0.7rem 0.5rem 0.7rem;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-testid="stSlider"] p,
    div[class*="st-key-filter_temp_neve_group_"] [data-testid="stSlider"] p,
    div[class*="st-key-filter_temp_produttore_group_"] [data-testid="stSlider"] p {
        font-size: 0.81rem !important;
        color: #566672 !important;
        font-weight: 600 !important;
    }

    div[class*="st-key-filter_temp_aria_group_"] [data-baseweb="slider"] [role="slider"],
    div[class*="st-key-filter_temp_neve_group_"] [data-baseweb="slider"] [role="slider"],
    div[class*="st-key-filter_temp_produttore_group_"] [data-baseweb="slider"] [role="slider"] {
        box-shadow: 0 0 0 4px rgba(24, 160, 214, 0.10) !important;
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
            SET snow_origine = ?, snow_consistenza = ?, snow_fondo = ?, snow_umidita = ?,
                snow_forma_grano = ?, snow_granulometria = ?, snow_caratteristiche = ?,
                zero_batteria = ?
            WHERE id = ?
            """,
            (
                classificazione.get("snow_origine", ""),
                classificazione.get("snow_consistenza", ""),
                classificazione.get("snow_fondo", ""),
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

# ============================================================
# CLASSIFICAZIONE NEVE STANDARDIZZATA
# ============================================================
# La forma del grano e' volutamente semplice e operativa: descrive lo stadio
# evolutivo generale. Le proprieta' funzionali (es. neve aggressiva) restano
# caratteristiche indipendenti.
SNOW_OPTION_GROUPS_STANDARD = {
    "Origine": ["Naturale", "Artificiale", "Mista"],
    "Consistenza": [
        "Soffice",
        "Sfarinata",
        "Compatta",
        "Sgranata",
        "Ghiacciata",
        "Molle",
    ],
    "Fondo sottostante": ["Omogeneo / n.d.", "Compatto", "Ghiacciato"],
    "Umidità neve": ["Secca", "Umida", "Bagnata", "Molto bagnata"],
    "Forma grano": ["Nuova", "In trasformazione", "Trasformata"],
    "Granulometria": ["Fine", "Media", "Grossa"],
    "Caratteristiche": ["Sporca", "Salata", "Ventata", "Lucida", "Cadente", "Vecchia", "Pioggia", "Variabile", "Aggressiva"],
}

SNOW_GRAIN_LEGACY_MAP = {
    "Nuova (cristalli esagonali)": "Nuova",
    "In trasformazione (forte gradiente)": "In trasformazione",
    "In trasformazione (basso gradiente)": "In trasformazione",
    "Trasformata (cristalli angolari)": "Trasformata",
    "Trasformata (grani arrotondati)": "Trasformata",
    "Mista nuova e trasformata": "In trasformazione",
}

def _snow_option_groups_standard():
    return {nome: list(valori) for nome, valori in SNOW_OPTION_GROUPS_STANDARD.items()}

def _normalizza_forma_grano_voce(voce):
    testo = str(voce or "").strip()
    return SNOW_GRAIN_LEGACY_MAP.get(testo, testo)

def _normalizza_forma_grano_valori(valori):
    risultato = []
    for voce in valori:
        normalizzata = _normalizza_forma_grano_voce(voce)
        if normalizzata and normalizzata not in risultato:
            risultato.append(normalizzata)
    return risultato

def _normalizza_forma_grano_testo(valore):
    valori = [v.strip() for v in str(valore or "").split(",") if v.strip()]
    if "Tutte" in valori:
        return "Tutte"
    return ", ".join(_normalizza_forma_grano_valori(valori))

SNOW_CONSISTENCY_LEGACY_MAP = {
    "Sfarinata / Soffice": ("Soffice, Sfarinata", "Omogeneo / n.d."),
    "Soffice / Sfarinata": ("Soffice, Sfarinata", "Omogeneo / n.d."),
    "Molle su fondo compatto": ("Molle", "Compatto"),
    "Soffice su fondo compatto": ("Soffice, Sfarinata", "Compatto"),
    "Soffice su fondo ghiacciato": ("Soffice, Sfarinata", "Ghiacciato"),
    "Molle su fondo ghiacciato": ("Molle", "Ghiacciato"),
}

def _valori_sessione_neve(valore, opzioni):
    valori = [v.strip() for v in str(valore or "").split(",") if v.strip()]
    if "Tutte" in valori:
        return list(opzioni)
    if list(opzioni) == SNOW_OPTION_GROUPS_STANDARD["Forma grano"]:
        valori = _normalizza_forma_grano_valori(valori)
    if list(opzioni) == SNOW_OPTION_GROUPS_STANDARD["Consistenza"]:
        espansi = []
        for voce in valori:
            if voce in {"Soffice / Sfarinata", "Sfarinata / Soffice", "Soffice, Sfarinata"}:
                for extra in ["Soffice", "Sfarinata"]:
                    if extra not in espansi:
                        espansi.append(extra)
            elif voce and voce not in espansi:
                espansi.append(voce)
        valori = espansi
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

    snow_option_groups = _snow_option_groups_standard()
    snow_field_map = {
        "Origine": "snow_origine",
        "Consistenza": "snow_consistenza",
        "Fondo sottostante": "snow_fondo",
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
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        selezioni["Origine"] = st.multiselect("Origine", snow_option_groups["Origine"], key="best_snow_origin")
    with c2:
        selezioni["Consistenza"] = st.multiselect("Consistenza superficiale", snow_option_groups["Consistenza"], key="best_snow_consistency")
    with c3:
        selezioni["Fondo sottostante"] = st.multiselect("Fondo sottostante", snow_option_groups["Fondo sottostante"], key="best_snow_base")
    with c4:
        selezioni["Umidità neve"] = st.multiselect("Umidità neve", snow_option_groups["Umidità neve"], key="best_snow_humidity")

    c5, c6, c7 = st.columns(3)
    with c5:
        selezioni["Forma grano"] = st.multiselect("Forma grano", snow_option_groups["Forma grano"], key="best_snow_grain")
    with c6:
        selezioni["Granulometria"] = st.multiselect("Granulometria", snow_option_groups["Granulometria"], key="best_snow_size")
    with c7:
        selezioni["Caratteristiche"] = st.multiselect("Caratteristiche", snow_option_groups["Caratteristiche"], key="best_snow_features")

    categoria = "scorrimento" if famiglia == "Prodotti di scorrimento" else "tenuta"

    prodotti = leggi_df("""
        SELECT
            id, nome, marca, tipo, categoria,
            temp_min, temp_max, tipo_temperatura,
            temp_nuova_min, temp_nuova_max,
            temp_trasformata_min, temp_trasformata_max,
            tipo_neve,
            snow_origine, snow_consistenza, snow_fondo, snow_umidita,
            snow_forma_grano, snow_granulometria, snow_caratteristiche
        FROM catalogo_prodotti
        WHERE categoria = ?
        ORDER BY marca COLLATE NOCASE, nome COLLATE NOCASE
    """, (categoria,))

    def _lista_valori(valore, nome_gruppo=None):
        valori = [
            voce.strip()
            for voce in str(valore or "").split(",")
            if voce.strip()
        ]
        if nome_gruppo == "Forma grano":
            valori = _normalizza_forma_grano_valori(valori)
        return set(valori)

    def _intervallo_riga(riga):
        tipo_ref = str(riga.get("tipo_temperatura") or "").strip().lower()
        ref_richiesto = riferimento.strip().lower()

        if ref_richiesto != "non specificato" and tipo_ref not in {ref_richiesto, "non specificato", ""}:
            return None

        if categoria == "tenuta":
            forma = set(selezioni.get("Forma grano", []))
            caratteristiche = set(selezioni.get("Caratteristiche", []))
            nuova_richiesta = bool(
                "Nuova" in forma
                or "Cadente" in caratteristiche
            )
            trasformata_richiesta = bool(
                "Trasformata" in forma
                or "In trasformazione" in forma
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
                prodotto_vals = _lista_valori(riga.get(snow_field_map[nome_gruppo]), nome_gruppo)
                if not prodotto_vals:
                    # fallback per prodotti più vecchi
                    prodotto_vals = _lista_valori(riga.get("tipo_neve"))

                if "Tutte" in prodotto_vals:
                    quota = 1.0
                else:
                    quota = len(richiesti & prodotto_vals) / max(1, len(richiesti))
                score_neve += quota
                if quota > 0:
                    dettagli_match.append(
                        "Consistenza superficiale" if nome_gruppo == "Consistenza" else nome_gruppo
                    )

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
    usa_condizioni = categoria in {"scorrimento", "tenuta", "rigatura"}
    categoria_tenuta = categoria == "tenuta"
    categoria_rigatura = categoria == "rigatura"
    label_nome_prodotto = "Nome riga *" if categoria_rigatura else "Nome prodotto *"
    placeholder_nome_prodotto = "es. LMV 1.0" if categoria_rigatura else "es. UHX Block Middle 26"
    label_tipo_prodotto = "Disegno" if categoria_rigatura else "Categoria prodotto"
    label_filtro_tipo = "Disegno" if categoria_rigatura else "Categoria"

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
                snow_origine, snow_consistenza, snow_fondo, snow_umidita,
                snow_forma_grano, snow_granulometria, snow_caratteristiche,
                umidita_min, umidita_max, temp_applicazione,
                tipo_applicazione, temp_nuova_min, temp_nuova_max,
                temp_trasformata_min, temp_trasformata_max,
                materiale, larghezza_mm, angolo_gradi,
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

    snow_option_groups = _snow_option_groups_standard()

    def _split_multi_values(valore, nome_colonna=None):
        valori = [voce.strip() for voce in str(valore or "").split(",") if voce.strip()]
        if nome_colonna == "snow_forma_grano":
            valori = _normalizza_forma_grano_valori(valori)
        return valori

    def _default_snow_values(nome_colonna, opzioni, eredita=None):
        eredita = eredita or []
        valori = []
        if modalita_modifica:
            valori_salvati = _split_multi_values(prodotto_edit.get(nome_colonna), nome_colonna)
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
        expander_label = (
            f"✏️ Modifica riga — {titolo_exp}"
            if categoria_rigatura
            else f"✏️ Modifica prodotto — {titolo_exp}"
        )
    else:
        expander_label = "➕ Inserimento riga" if categoria_rigatura else "➕ Inserimento prodotto"

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
                    ["Neve nuova/fine", "Neve vecchia/trasformata", "Tutte le tipologie di neve", "Non specificato"],
                    key=tenuta_condizioni_key,
                    placeholder="Seleziona una o più opzioni",
                    help=(
                        "Scegli se il range produttore vale per neve nuova/fine, neve vecchia/trasformata, "
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
            mostra_nuova = ("Neve nuova/fine" in condizioni_range_tenuta) and not mostra_tutte and not mostra_non_specificato
            mostra_trasformata = ("Neve vecchia/trasformata" in condizioni_range_tenuta) and not mostra_tutte and not mostra_non_specificato

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
                            f'{SNOW_ICON_NEW_SVG}<strong>Neve nuova/fine</strong>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        n1, n2, n3 = st.columns(3)
                        with n1:
                            temp_nuova_min_txt = st.text_input(
                                "Min neve nuova/fine (°C)",
                                key=tenuta_temp_nuova_min_key,
                                placeholder="-10",
                            )
                        with n2:
                            temp_nuova_max_txt = st.text_input(
                                "Max neve nuova/fine (°C)",
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
                            f'{SNOW_ICON_TRANSFORMED_SVG}<strong>Neve vecchia/trasformata</strong>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        t1, t2, t3 = st.columns(3)
                        with t1:
                            temp_trasformata_min_txt = st.text_input(
                                "Min neve vecchia/trasformata (°C)",
                                key=tenuta_temp_trasf_min_key,
                                placeholder="-15",
                            )
                        with t2:
                            temp_trasformata_max_txt = st.text_input(
                                "Max neve vecchia/trasformata (°C)",
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
                            label_nome_prodotto,
                            value=valore_nome,
                            placeholder=placeholder_nome_prodotto,
                        )
                    with c_marca:
                        marca = st.text_input(
                            "Marca",
                            value=valore_marca,
                            placeholder="es. SRB" if categoria_rigatura else "es. HWK",
                        )
                    with c_tipo:
                        tipi_form = list(tipi)
                        if categoria_rigatura and valore_tipo and valore_tipo not in tipi_form:
                            tipi_form = [valore_tipo] + tipi_form
                        tipo = st.selectbox(
                            label_tipo_prodotto,
                            tipi_form,
                            index=_indice_opzione(tipi_form, valore_tipo, 0),
                        )

                    materiale = ""
                    larghezza_mm_txt = ""
                    angolo_gradi_txt = ""
                    if categoria_rigatura:
                        materiale_default = str(prodotto_edit.get("materiale") or "") if modalita_modifica else ""
                        larghezza_default = _input_numero_da_db(prodotto_edit.get("larghezza_mm")) if modalita_modifica else ""
                        angolo_default = _input_numero_da_db(prodotto_edit.get("angolo_gradi")) if modalita_modifica else ""
                        c_materiale, c_larghezza, c_angolo = st.columns(3)
                        with c_materiale:
                            materiali = ["Acciaio", "Ottone"]
                            materiale = st.selectbox(
                                "Materiale",
                                materiali,
                                index=_indice_opzione(materiali, materiale_default, 0),
                            )
                        with c_larghezza:
                            larghezza_mm_txt = st.text_input(
                                "Larghezza (mm)",
                                value=larghezza_default,
                                placeholder="es. 1.0",
                            )
                        with c_angolo:
                            angolo_gradi_txt = st.text_input(
                                "Angolo della riga (°)",
                                value=angolo_default,
                                placeholder="es. 45",
                            )
                else:
                    materiale = ""
                    larghezza_mm_txt = ""
                    angolo_gradi_txt = ""

                tipo_neve_val = ""
                snow_origine_val = ""
                snow_consistenza_val = ""
                snow_fondo_val = ""
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
                    st.caption("Definisci il campo di utilizzo della riga e la classificazione neve di riferimento." if categoria_rigatura else "Definisci il campo di utilizzo del prodotto e la classificazione neve di riferimento.")

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
                        "Fondo sottostante": [],
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
                    fondo_default = _default_snow_values(
                        "snow_fondo",
                        snow_option_groups["Fondo sottostante"],
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

                    c_snow_1, c_snow_2, c_snow_3, c_snow_4 = st.columns(4)
                    with c_snow_1:
                        snow_selection_map["Origine"] = st.multiselect(
                            "Origine", snow_option_groups["Origine"], default=origini_default,
                            placeholder="Seleziona origine", disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_2:
                        snow_selection_map["Consistenza"] = st.multiselect(
                            "Consistenza superficiale", snow_option_groups["Consistenza"], default=consistenza_default,
                            placeholder="Seleziona consistenza", disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_3:
                        snow_selection_map["Fondo sottostante"] = st.multiselect(
                            "Fondo sottostante", snow_option_groups["Fondo sottostante"], default=fondo_default,
                            placeholder="Seleziona fondo", disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_4:
                        snow_selection_map["Umidità neve"] = st.multiselect(
                            "Umidità neve", snow_option_groups["Umidità neve"], default=umidita_neve_default,
                            placeholder="Seleziona umidità neve", disabled=compatibile_tutte_condizioni,
                        )

                    c_snow_5, c_snow_6, c_snow_7 = st.columns(3)
                    with c_snow_5:
                        snow_selection_map["Forma grano"] = st.multiselect(
                            "Forma grano", snow_option_groups["Forma grano"], default=forma_grano_default,
                            placeholder="Seleziona forma grano", disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_6:
                        snow_selection_map["Granulometria"] = st.multiselect(
                            "Granulometria", snow_option_groups["Granulometria"], default=granulometria_default,
                            placeholder="Seleziona granulometria", disabled=compatibile_tutte_condizioni,
                        )
                    with c_snow_7:
                        snow_selection_map["Caratteristiche"] = st.multiselect(
                            "Caratteristiche", snow_option_groups["Caratteristiche"], default=caratteristiche_default,
                            placeholder="Seleziona caratteristiche", disabled=compatibile_tutte_condizioni,
                        )

                    snow_origine_val = _snow_value_compact(
                        "Origine", snow_selection_map["Origine"]
                    )
                    snow_consistenza_val = _snow_value_compact(
                        "Consistenza", snow_selection_map["Consistenza"]
                    )
                    snow_fondo_val = _snow_value_compact(
                        "Fondo sottostante", snow_selection_map["Fondo sottostante"]
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
                        "Nuova foto" if modalita_modifica else ("Foto riga" if categoria_rigatura else "Foto prodotto"),
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
                            "Modifica riga" if categoria_rigatura else "Modifica prodotto",
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
                        "Salva riga" if categoria_rigatura else "Salva prodotto",
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
                                if "Neve nuova/fine" in condizioni_range_tenuta:
                                    temp_nuova_unica = _numero_opzionale(temp_nuova_unica_txt)
                                    if temp_nuova_unica is not None:
                                        temp_nuova_min = temp_nuova_max = temp_nuova_unica
                                    else:
                                        temp_nuova_min = _numero_opzionale(temp_nuova_min_txt)
                                        temp_nuova_max = _numero_opzionale(temp_nuova_max_txt)
                                if "Neve vecchia/trasformata" in condizioni_range_tenuta:
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

                    materiale_salvato = materiale.strip() if categoria_rigatura else ""
                    larghezza_mm = None
                    angolo_gradi = None
                    if categoria_rigatura:
                        try:
                            larghezza_mm = _numero_opzionale(larghezza_mm_txt)
                            angolo_gradi = _numero_opzionale(angolo_gradi_txt)
                        except ValueError:
                            errori.append("Larghezza e angolo devono essere valori numerici.")
                        if larghezza_mm is not None and larghezza_mm <= 0:
                            errori.append("La larghezza deve essere maggiore di 0 mm.")
                        if angolo_gradi is not None and not (0 <= angolo_gradi <= 180):
                            errori.append("L'angolo della riga deve essere compreso tra 0° e 180°.")

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
                                    snow_fondo = ?,
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
                                    temp_trasformata_max = ?,
                                    materiale = ?,
                                    larghezza_mm = ?,
                                    angolo_gradi = ?
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
                                snow_fondo_val if usa_condizioni else "",
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
                                materiale_salvato if categoria_rigatura else "",
                                larghezza_mm if categoria_rigatura else None,
                                angolo_gradi if categoria_rigatura else None,
                                int(edit_id),
                                categoria,
                            ))
                            st.session_state.pop(edit_state_key, None)
                            st.session_state.pop(expander_keep_key, None)
                            if categoria_tenuta:
                                for chiave_ui in tenuta_ui_keys:
                                    st.session_state.pop(chiave_ui, None)
                            st.success("Riga modificata." if categoria_rigatura else "Prodotto modificato.")
                            st.rerun()

                        else:
                            esegui("""
                                INSERT INTO catalogo_prodotti (
                                    categoria, nome, marca, tipo,
                                    descrizione, note, creato_il,
                                    foto_data, foto_mime, foto_nome,
                                    temp_min, temp_max,
                                    tipo_temperatura, tipo_neve,
                                    snow_origine, snow_consistenza, snow_fondo,
                                    snow_umidita, snow_forma_grano,
                                    snow_granulometria, snow_caratteristiche,
                                    umidita_min, umidita_max,
                                    temp_applicazione, tipo_applicazione,
                                    temp_nuova_min, temp_nuova_max,
                                    temp_trasformata_min, temp_trasformata_max,
                                    materiale, larghezza_mm, angolo_gradi
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                                snow_fondo_val if usa_condizioni else "",
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
                                materiale_salvato if categoria_rigatura else "",
                                larghezza_mm if categoria_rigatura else None,
                                angolo_gradi if categoria_rigatura else None,
                            ))
                            st.session_state.pop(expander_keep_key, None)
                            if categoria_tenuta:
                                for chiave_ui in tenuta_ui_keys:
                                    st.session_state.pop(chiave_ui, None)
                            st.success("Riga salvata." if categoria_rigatura else "Prodotto salvato.")
                            st.rerun()

    st.markdown("### Catalogo righe" if categoria_rigatura else "### Catalogo prodotti")

    df = leggi_df("""
        SELECT
            id, nome, marca, tipo,
            temp_min, temp_max, tipo_temperatura, tipo_neve,
            snow_origine, snow_consistenza, snow_fondo, snow_umidita,
            snow_forma_grano, snow_granulometria, snow_caratteristiche,
            umidita_min, umidita_max, temp_applicazione,
            tipo_applicazione, temp_nuova_min, temp_nuova_max,
            temp_trasformata_min, temp_trasformata_max,
            materiale, larghezza_mm, angolo_gradi,
            descrizione, note
        FROM catalogo_prodotti
        WHERE categoria = ?
        ORDER BY marca COLLATE NOCASE, nome COLLATE NOCASE
    """, (categoria,))

    if df.empty:
        st.info("Nessuna riga ancora inserita in questo catalogo." if categoria_rigatura else "Nessun prodotto ancora inserito in questo catalogo.")
        return

    with st.container(key=f"catalog_filter_panel_{categoria}"):
        # -----------------------------------------------------
        # Intestazione filtri + reset
        # -----------------------------------------------------
        h1, h2 = st.columns([4.2, 1], vertical_alignment="center")
        with h1:
            filtro_sottotitolo = (
                "Affina rapidamente le righe visualizzate."
                if categoria_rigatura
                else "Affina rapidamente i prodotti visualizzati."
            )
            st.markdown(
                '<div class="catalog-filter-title">Filtri catalogo</div>'
                f'<div class="catalog-filter-subtitle">{filtro_sottotitolo}</div>',
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
                label_filtro_tipo,
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
        filtro_temp_neve_tipo = "Neve nuova"
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
                    voce = _normalizza_forma_grano_voce(voce)
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
                neve_min, neve_max = _limiti_temperatura_per_riferimento("neve")

                c_aria_f, c_neve_f = st.columns(2)

                with c_aria_f:
                    with st.container(key=f"filter_temp_aria_group_{categoria}"):
                        st.markdown(
                            '<div class="catalog-temperature-card-title">'
                            'Temperatura aria'
                            '</div>'
                            '<div class="catalog-temperature-card-subtitle">'
                            'Filtra i prodotti con intervallo riferito all’aria. Se il riferimento generale non è specificato, il prodotto viene comunque mostrato.'
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

                with c_neve_f:
                    with st.container(key=f"filter_temp_neve_group_{categoria}"):
                        st.markdown(
                            '<div class="catalog-temperature-card-title">'
                            'Temperatura neve'
                            '</div>'
                            '<div class="catalog-temperature-card-subtitle">'
                            'Scegli neve nuova o trasformata. I prodotti validi per entrambe o non specificati per il tipo di neve vengono comunque mostrati.'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        filtro_temp_neve_attivo = st.toggle(
                            "Attiva filtro neve",
                            key=f"usa_temp_neve_{categoria}",
                        )
                        filtro_temp_neve_tipo = st.radio(
                            "Tipo neve",
                            ["Neve nuova", "Neve trasformata"],
                            horizontal=True,
                            disabled=not filtro_temp_neve_attivo,
                            key=f"temp_neve_tipo_catalogo_{categoria}",
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
        if categoria_tenuta and (filtro_temp_aria_attivo or filtro_temp_neve_attivo):
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

            mask_temp_base = temp_min_prod.notna() | temp_max_prod.notna()
            base_min_eff = temp_min_prod.fillna(float("-inf"))
            base_max_eff = temp_max_prod.fillna(float("inf"))
            mask_generico = tipo_temp_prod.isin(["non specificato", "range produttore", ""])
            maschera_temperatura = pd.Series(False, index=filtrato.index)

            if filtro_temp_aria_attivo and filtro_temp_aria_range is not None:
                aria_sel_min, aria_sel_max = filtro_temp_aria_range
                mask_aria = (
                    ((tipo_temp_prod == "aria") | mask_generico)
                    & mask_temp_base
                    & (base_min_eff <= float(aria_sel_max))
                    & (base_max_eff >= float(aria_sel_min))
                )
                maschera_temperatura = maschera_temperatura | mask_aria

            if filtro_temp_neve_attivo and filtro_temp_neve_range is not None:
                neve_sel_min, neve_sel_max = filtro_temp_neve_range
                if str(filtro_temp_neve_tipo or "").strip().lower() == "neve trasformata":
                    spec_min = temp_trasf_min_prod
                    spec_max = temp_trasf_max_prod
                else:
                    spec_min = temp_nuova_min_prod
                    spec_max = temp_nuova_max_prod

                spec_min_eff = spec_min.fillna(float("-inf"))
                spec_max_eff = spec_max.fillna(float("inf"))
                mask_snow_specifica = (
                    (tipo_temp_prod == "neve")
                    & (spec_min.notna() | spec_max.notna())
                    & (spec_min_eff <= float(neve_sel_max))
                    & (spec_max_eff >= float(neve_sel_min))
                )
                mask_snow_generica = (
                    (((tipo_temp_prod == "neve") & ~(spec_min.notna() | spec_max.notna())) | mask_generico)
                    & mask_temp_base
                    & (base_min_eff <= float(neve_sel_max))
                    & (base_max_eff >= float(neve_sel_min))
                )
                maschera_temperatura = (
                    maschera_temperatura | mask_snow_specifica | mask_snow_generica
                )

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
                _normalizza_forma_grano_voce(voce.strip())
                for voce in str(valore or "").split(",")
                if voce.strip()
            }
            if "Tutte" in tipi_prodotto:
                return True
            return bool(tipi_prodotto & neve_selezionate)

        filtrato = filtrato[
            filtrato["tipo_neve"].apply(_compatibile_neve)
        ]

    st.caption(f"{len(filtrato)} righe visualizzate su {len(df)}" if categoria_rigatura else f"{len(filtrato)} prodotti visualizzati su {len(df)}")

    if filtrato.empty:
        st.info("Nessuna riga corrisponde ai filtri selezionati." if categoria_rigatura else "Nessun prodotto corrisponde ai filtri selezionati.")
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

                    if categoria_rigatura:
                        dettagli_tecnici = []
                        materiale_card = str(prodotto.get("materiale") or "").strip()
                        if materiale_card:
                            dettagli_tecnici.append(materiale_card)
                        larghezza_card = prodotto.get("larghezza_mm")
                        if larghezza_card is not None and not pd.isna(larghezza_card):
                            dettagli_tecnici.append(f"{float(larghezza_card):g} mm")
                        angolo_card = prodotto.get("angolo_gradi")
                        if angolo_card is not None and not pd.isna(angolo_card):
                            dettagli_tecnici.append(f"{float(angolo_card):g}°")
                        if dettagli_tecnici:
                            st.caption(" · ".join(dettagli_tecnici))

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

                        if categoria_rigatura:
                            materiale_scheda = str(prodotto.get("materiale") or "").strip()
                            larghezza_scheda = prodotto.get("larghezza_mm")
                            angolo_scheda = prodotto.get("angolo_gradi")
                            if materiale_scheda:
                                st.markdown(f"**Materiale:** {materiale_scheda}")
                            if larghezza_scheda is not None and not pd.isna(larghezza_scheda):
                                st.markdown(f"**Larghezza:** {float(larghezza_scheda):g} mm")
                            if angolo_scheda is not None and not pd.isna(angolo_scheda):
                                st.markdown(f"**Angolo riga:** {float(angolo_scheda):g}°")

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
                                ("Consistenza superficiale", str(prodotto.get("snow_consistenza") or "").strip()),
                                ("Fondo sottostante", str(prodotto.get("snow_fondo") or "").strip()),
                                ("Umidità neve", str(prodotto.get("snow_umidita") or "").strip()),
                                ("Forma grano", _normalizza_forma_grano_testo(prodotto.get("snow_forma_grano"))),
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

                                    chiave_opzioni = {
                                        "Consistenza superficiale": "Consistenza",
                                    }.get(etichetta_campo, etichetta_campo)
                                    opzioni_complete = snow_option_groups.get(
                                        chiave_opzioni, []
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
                            "Modifica riga" if categoria_rigatura else "Modifica prodotto",
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
                                "Elimina riga" if categoria_rigatura else "Elimina prodotto",
                                key=f"delete_product_{categoria}_{prodotto_id}",
                                use_container_width=True,
                            ):
                                st.session_state[conferma_key] = True
                                st.rerun()

                        else:
                            delete_question = (
                                "Eliminare definitivamente la riga?"
                                if categoria_rigatura
                                else "Eliminare definitivamente il prodotto?"
                            )
                            st.markdown(
                                f'<div class="catalog-delete-warning">'
                                f'<strong>{delete_question}</strong><br>'
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
    snow_options_scroll = _snow_option_groups_standard()

    edit_scroll_session_id = st.session_state.get("scroll_edit_session_id")
    edit_scroll_row = None
    needs_scroll_edit_load = False
    if edit_scroll_session_id is not None:
        df_edit_scroll = leggi_df(
            """
            SELECT id, data, ora, luogo, temperatura_aria, temperatura_neve,
                   umidita, meteo, snow_origine, snow_consistenza, snow_fondo, snow_umidita,
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
        st.session_state["scroll_base_condition"] = _valori_sessione_neve(edit_scroll_row.get("snow_fondo"), snow_options_scroll["Fondo sottostante"])
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

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        scroll_origine = st.multiselect("Origine", snow_options_scroll["Origine"], key="scroll_origin")
    with s2:
        scroll_consistenza = st.multiselect("Consistenza superficiale", snow_options_scroll["Consistenza"], key="scroll_consistency")
    with s3:
        scroll_fondo = st.multiselect("Fondo sottostante", snow_options_scroll["Fondo sottostante"], key="scroll_base_condition")
    with s4:
        scroll_umidita_neve = st.multiselect("Umidità neve", snow_options_scroll["Umidità neve"], key="scroll_snow_humidity")

    s5, s6, s7 = st.columns(3)
    with s5:
        scroll_forma = st.multiselect("Forma grano", snow_options_scroll["Forma grano"], key="scroll_grain")
    with s6:
        scroll_granulometria = st.multiselect("Granulometria", snow_options_scroll["Granulometria"], key="scroll_size")
    with s7:
        scroll_caratteristiche = st.multiselect("Caratteristiche", snow_options_scroll["Caratteristiche"], key="scroll_features")

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
                                    snow_origine = ?, snow_consistenza = ?, snow_fondo = ?, snow_umidita = ?,
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
                                    _compatta_neve_sessione(scroll_fondo, snow_options_scroll["Fondo sottostante"]),
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
                                    snow_origine, snow_consistenza, snow_fondo, snow_umidita,
                                    snow_forma_grano, snow_granulometria, snow_caratteristiche,
                                    zero_modello_sci, tipo_test, categoria_test_scorrimento, zero_riferimento_id, note, creato_il
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?)
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
                                    _compatta_neve_sessione(scroll_fondo, snow_options_scroll["Fondo sottostante"]),
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



def _rigatura_catalog_label(record):
    """Etichetta compatta usata nei test: mostra solo il nome della rigatura."""
    return str(record.get("nome") or "").strip()


def _testo_pulito(valore):
    """Converte un valore in testo ignorando None/NaN/NA."""
    if valore is None:
        return ""
    try:
        if pd.isna(valore):
            return ""
    except Exception:
        pass
    testo = str(valore).strip()
    return "" if testo.lower() in {"nan", "none", "<na>"} else testo


def _rigatura_component_names(record):
    """Restituisce i nomi della singola rigatura o della coppia salvata nella stessa cella."""
    nomi = []
    nome_1 = _testo_pulito(record.get("nome"))
    nome_2 = _testo_pulito(record.get("nome_2"))
    if nome_1:
        nomi.append(nome_1)
    if nome_2:
        nomi.append(nome_2)
    return nomi


def _rigatura_component_label(record):
    """Una cella doppia viene rappresentata come V301/V302, senza segno +."""
    nomi = _rigatura_component_names(record)
    return "/".join(nomi) if nomi else "—"


def _rigatura_image_src(foto_data, foto_mime):
    """Restituisce una data-URL solo quando esiste davvero una foto valida."""
    valore = _testo_pulito(foto_data)
    if not valore:
        return ""
    mime = _testo_pulito(foto_mime) or "image/png"
    return f"data:{html_escape(mime)};base64,{valore}"


def _zone_rigatura_per_tecnica(tecnica):
    """Riferimenti longitudinali coerenti con lo schema grafico dell'utente."""
    if str(tecnica or "").strip().lower() == "classico":
        return ["Coda", "Fine ponte", "Inizio ponte", "Inizio canalina", "Punta"]
    # Nello schema skating ci sono due riferimenti 'inizio canalina':
    # li distinguiamo solo nel menu per evitare ambiguità, mantenendo la grafica originale.
    return [
        "Coda",
        "Fine attacco",
        "Inizio canalina (lato coda)",
        "Inizio canalina (lato punta)",
        "Punta",
    ]


# Asset incorporati direttamente nel sorgente: l'hover del podio non dipende
# da file statici esterni durante il deploy Streamlit.
_SCHEMA_ZONE_SKATING_DATA_URL = "data:image/png;base64,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"
_SCHEMA_ZONE_CLASSICO_DATA_URL = "data:image/png;base64,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"
_HAND_DRIVE_WHEEL_DATA_URL = "data:image/png;base64,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"


def _schema_zone_rigatura_path(tecnica):
    nome = "schema_zone_classico.png" if str(tecnica or "").strip().lower() == "classico" else "schema_zone_skating.png"
    return os.path.join(BASE_DIR, "assets", nome)


def _schema_zone_rigatura_src(tecnica):
    """Schema sci incorporato: garantisce la visualizzazione nel tooltip anche in cloud."""
    if str(tecnica or "").strip().lower() == "classico":
        return _SCHEMA_ZONE_CLASSICO_DATA_URL
    return _SCHEMA_ZONE_SKATING_DATA_URL


def _asset_image_src(path, mime="image/png"):
    """Converte un asset locale in data-URL per i tooltip HTML."""
    try:
        dati = Path(path).read_bytes()
        return f"data:{mime};base64,{base64.b64encode(dati).decode('ascii')}"
    except Exception:
        return ""


def _zona_overlay_rigatura(tecnica, zona_da, zona_a):
    """Restituisce left/width (%) per evidenziare la zona sulla soletta nello schema."""
    tecnica_norm = str(tecnica or "").strip().lower()
    if tecnica_norm == "classico":
        punti = {
            "Coda": 5.7,
            "Fine ponte": 34.6,
            "Inizio ponte": 57.6,
            "Inizio canalina": 79.1,
            "Punta": 89.9,
        }
    else:
        punti = {
            "Coda": 5.7,
            "Fine attacco": 32.6,
            "Inizio canalina (lato coda)": 52.9,
            "Inizio canalina (lato punta)": 81.3,
            "Inizio canalina": 81.3,
            "Punta": 91.6,
        }
    da = str(zona_da or "").strip()
    a = str(zona_a or "").strip()
    if da not in punti or a not in punti:
        return None
    x1, x2 = punti[da], punti[a]
    left = min(x1, x2)
    width = max(1.2, abs(x2 - x1))
    return left, width


def _zona_rigatura_testo(zona_da, zona_a):
    da = str(zona_da or "").strip()
    a = str(zona_a or "").strip()
    if not da and not a:
        return "—"
    if da and a:
        return f"{da} → {a}"
    return da or a or "—"


def render_form_test_rigature():
    """Inserimento/modifica Test rigature manuali, allineato al Test prodotti scorrimento."""
    snow_options = _snow_option_groups_standard()
    edit_id = st.session_state.get("rig_test_edit_session_id")
    edit_row = None
    needs_load = False
    if edit_id is not None:
        df_edit = leggi_df(
            """
            SELECT id, data, ora, luogo, temperatura_aria, temperatura_neve,
                   umidita, meteo, snow_origine, snow_consistenza, snow_fondo, snow_umidita,
                   snow_forma_grano, snow_granulometria, snow_caratteristiche,
                   zero_modello_sci, tipo_test, zero_riferimento_id
            FROM sessioni WHERE id = ?
            """, (int(edit_id),)
        )
        if not df_edit.empty:
            edit_row = df_edit.iloc[0]
            needs_load = st.session_state.get("rig_test_edit_loaded_id") != int(edit_id)
        else:
            st.session_state.pop("rig_test_edit_session_id", None)
            st.session_state.pop("rig_test_edit_loaded_id", None)
            edit_id = None

    if needs_load and edit_row is not None:
        metodo = str(edit_row.get("tipo_test") or "Asta").replace("Test rigature manuali · ", "").strip()
        st.session_state["rig_test_method"] = metodo if metodo in ["Asta", "Parallel", "Fotocellula"] else "Asta"
        try:
            st.session_state["rig_test_date"] = pd.to_datetime(edit_row.get("data")).date()
        except Exception:
            st.session_state["rig_test_date"] = date.today()
        try:
            st.session_state["rig_test_time"] = datetime.strptime(str(edit_row.get("ora") or "00:00")[:5], "%H:%M").time()
        except Exception:
            st.session_state["rig_test_time"] = datetime.now().time().replace(second=0, microsecond=0)
        st.session_state["rig_test_place"] = str(edit_row.get("luogo") or "")
        st.session_state["rig_test_air"] = _formatta_temperatura_1d(edit_row.get("temperatura_aria"))
        st.session_state["rig_test_snow"] = _formatta_temperatura_1d(edit_row.get("temperatura_neve"))
        ur = edit_row.get("umidita")
        st.session_state["rig_test_rh_missing"] = bool(pd.isna(ur))
        st.session_state["rig_test_rh"] = 70 if pd.isna(ur) else int(round(float(ur)))
        st.session_state["rig_test_ski_model"] = str(edit_row.get("zero_modello_sci") or "")
        meteo = str(edit_row.get("meteo") or "").strip()
        st.session_state["rig_test_weather"] = meteo if meteo in METEO_OPZIONI else None
        st.session_state["rig_test_origin"] = _valori_sessione_neve(edit_row.get("snow_origine"), snow_options["Origine"])
        st.session_state["rig_test_consistency"] = _valori_sessione_neve(edit_row.get("snow_consistenza"), snow_options["Consistenza"])
        st.session_state["rig_test_base"] = _valori_sessione_neve(edit_row.get("snow_fondo"), snow_options["Fondo sottostante"])
        st.session_state["rig_test_humidity"] = _valori_sessione_neve(edit_row.get("snow_umidita"), snow_options["Umidità neve"])
        st.session_state["rig_test_grain"] = _valori_sessione_neve(edit_row.get("snow_forma_grano"), snow_options["Forma grano"])
        st.session_state["rig_test_size"] = _valori_sessione_neve(edit_row.get("snow_granulometria"), snow_options["Granulometria"])
        st.session_state["rig_test_features"] = _valori_sessione_neve(edit_row.get("snow_caratteristiche"), snow_options["Caratteristiche"])
        df_count = leggi_df("SELECT COUNT(*) AS n FROM test_rigature_aste WHERE sessione_id = ?", (int(edit_id),))
        st.session_state["rig_test_num_rods"] = max(1, int(df_count.iloc[0]["n"] or 1)) if not df_count.empty else 1
        df_cols = leggi_df(
            """SELECT MAX(c.colonna_numero) AS n
               FROM test_rigature_componenti c
               JOIN test_rigature_aste a ON a.id = c.test_rigatura_asta_id
               WHERE a.sessione_id = ?""", (int(edit_id),)
        )
        ncols = 1
        if not df_cols.empty and not pd.isna(df_cols.iloc[0]["n"]):
            ncols = max(1, int(df_cols.iloc[0]["n"]))
        st.session_state["rig_test_num_columns"] = ncols
        df_tecnica = leggi_df(
            """SELECT c.tecnica_sci
               FROM test_rigature_componenti c
               JOIN test_rigature_aste a ON a.id = c.test_rigatura_asta_id
               WHERE a.sessione_id = ? AND TRIM(COALESCE(c.tecnica_sci, '')) <> ''
               ORDER BY c.id LIMIT 1""", (int(edit_id),)
        )
        tecnica_edit = "Skating"
        if not df_tecnica.empty:
            val = str(df_tecnica.iloc[0].get("tecnica_sci") or "").strip()
            if val in ["Skating", "Classico"]:
                tecnica_edit = val
        st.session_state["rig_test_technique"] = tecnica_edit

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="insert-test-title">Test rigature manuali</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="insert-test-caption">Stessa struttura del Test prodotti scorrimento: registra metodo, condizioni, classificazione neve e combinazioni di rigature utilizzate su ogni sci.</div>',
        unsafe_allow_html=True,
    )

    if edit_id is not None:
        ce1, ce2 = st.columns([4, 1.25])
        with ce1:
            st.info("Modalità modifica attiva: stai aggiornando un test rigature manuali già presente nello storico.")
        with ce2:
            if st.button("Annulla modifica", use_container_width=True, key="cancel_rig_test_edit"):
                for k in ["rig_test_edit_session_id", "rig_test_edit_loaded_id", "rig_test_table_data", "rig_test_table_n", "rig_test_table_cols"]:
                    st.session_state.pop(k, None)
                st.rerun()

    st.markdown("#### Impostazione test")
    c_metodo, c_zero = st.columns([1, 1.6])
    with c_metodo:
        metodo_test = st.selectbox(
            "Metodo test", ["Asta", "Parallel", "Fotocellula"],
            key="rig_test_method",
            help="Seleziona il metodo con cui hai effettuato il test rigature.",
        )

    df_zero = leggi_df(
        """
        SELECT s.id, s.data, s.ora, s.luogo, s.zero_batteria, s.zero_modello_sci
        FROM sessioni s JOIN zero_test z ON z.sessione_id = s.id
        WHERE COALESCE(s.zero_batteria, '') = 'Batteria rigature manuali'
        GROUP BY s.id
        ORDER BY s.data DESC, COALESCE(s.ora, '') DESC, s.id DESC
        """
    )
    labels = ["Nessuno"]
    ref_map = {"Nessuno": None}
    for _, ref in df_zero.iterrows():
        lab = f"{str(ref.get('data') or '')} · {str(ref.get('luogo') or '—')}"
        mod = str(ref.get("zero_modello_sci") or "").strip()
        if mod:
            lab += f" · {mod}"
        labels.append(lab)
        ref_map[lab] = int(ref["id"])
    if needs_load and edit_row is not None:
        rid = edit_row.get("zero_riferimento_id")
        ref_label = "Nessuno"
        if rid is not None and not pd.isna(rid):
            for lab, val in ref_map.items():
                if val == int(rid):
                    ref_label = lab
                    break
        st.session_state["rig_test_zero_reference"] = ref_label
    with c_zero:
        zero_label = st.selectbox(
            "Zero Test di riferimento", labels, key="rig_test_zero_reference",
            help="Solo riferimento informativo; non modifica i risultati del test.",
        )
    zero_ref_id = ref_map.get(zero_label)

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### Dati sessione")
    st.caption("Inserisci le condizioni effettive rilevate durante il test rigature.")
    c1, c2, c3 = st.columns(3)
    with c1:
        data_test = st.date_input("Data", value=date.today(), key="rig_test_date")
        luogo = st.text_input("Luogo *", key="rig_test_place", placeholder="es. Davos (SUI)")
    with c2:
        ora = st.time_input("Ora", value=datetime.now().time().replace(second=0, microsecond=0), key="rig_test_time")
        taria_txt = st.text_input("Temperatura aria (°C)", value="0.0", key="rig_test_air")
    with c3:
        tneve_txt = st.text_input("Temperatura neve (°C)", value="0.0", key="rig_test_snow")
        if "rig_test_rh_missing" not in st.session_state:
            st.session_state["rig_test_rh_missing"] = False
        ur = st.number_input("Umidità relativa (%)", 0, 100, 70, 1, disabled=bool(st.session_state.get("rig_test_rh_missing", False)), key="rig_test_rh")
        ur_missing = st.checkbox("Umidità non disponibile", key="rig_test_rh_missing")
    c4, c5 = st.columns(2)
    with c4:
        modello_sci = st.text_input("Modello sci", key="rig_test_ski_model", placeholder="es. Speedmax 3D")
    with c5:
        meteo = st.selectbox("Meteo", METEO_OPZIONI, index=None, placeholder="Seleziona meteo", key="rig_test_weather")

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### Classificazione neve")
    st.caption("Usa la stessa classificazione indipendente adottata nel catalogo e nei test di scorrimento.")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        origine = st.multiselect("Origine", snow_options["Origine"], key="rig_test_origin")
    with s2:
        consistenza = st.multiselect("Consistenza superficiale", snow_options["Consistenza"], key="rig_test_consistency")
    with s3:
        fondo = st.multiselect("Fondo sottostante", snow_options["Fondo sottostante"], key="rig_test_base")
    with s4:
        umidita_neve = st.multiselect("Umidità neve", snow_options["Umidità neve"], key="rig_test_humidity")
    s5, s6, s7 = st.columns(3)
    with s5:
        forma = st.multiselect("Forma grano", snow_options["Forma grano"], key="rig_test_grain")
    with s6:
        granulometria = st.multiselect("Granulometria", snow_options["Granulometria"], key="rig_test_size")
    with s7:
        caratteristiche = st.multiselect("Caratteristiche", snow_options["Caratteristiche"], key="rig_test_features")

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### Rigature testate")

    if metodo_test != "Asta":
        st.info(f"La struttura di inserimento per il test {metodo_test} segue la stessa logica della pagina prodotti scorrimento e verrà definita quando userai questo metodo.")
        return

    st.caption("Imposta il numero di aste e quante rigature compongono ciascuno sci. Per ogni rigatura selezioni nome, direzione, Hand drive e zona dello sci su cui è stata applicata.")

    tecnica_sci = st.selectbox(
        "Tecnica sci",
        ["Skating", "Classico"],
        key="rig_test_technique",
        help="La suddivisione delle zone cambia tra sci da skating e sci da classico.",
    )
    zone_tecnica = _zone_rigatura_per_tecnica(tecnica_sci)
    schema_path = _schema_zone_rigatura_path(tecnica_sci)
    st.markdown("##### Schema zone dello sci")
    if os.path.exists(schema_path):
        st.image(schema_path, use_container_width=True)
    st.caption(
        "Usa lo schema come riferimento e indica, per ogni rigatura, il punto di inizio e il punto di fine dell'applicazione."
    )

    cc1, cc2 = st.columns(2)
    with cc1:
        numero_aste = st.number_input("Numero di aste", min_value=1, max_value=30, value=10, step=1, format="%d", key="rig_test_num_rods")
    with cc2:
        numero_colonne = st.number_input(
            "Numero di rigature per sci", min_value=1, max_value=6, value=1, step=1, format="%d", key="rig_test_num_columns",
            help="1 = una sola riga per sci. Aumenta il numero per testare combinazioni di più rigature sullo stesso sci.",
        )

    df_catalogo = leggi_df(
        """SELECT id, nome, marca, tipo, materiale, larghezza_mm, angolo_gradi
           FROM catalogo_prodotti WHERE categoria = 'rigatura'
           ORDER BY COALESCE(marca, ''), nome"""
    )
    opzioni = ["—"]
    ids_da_label = {"—": (None, None)}
    label_da_id = {}
    rigature_catalogo = []
    if not df_catalogo.empty:
        conteggi_nome = df_catalogo["nome"].fillna("").astype(str).str.strip().value_counts().to_dict()
        for _, prod in df_catalogo.iterrows():
            nome_riga = _rigatura_catalog_label(prod)
            if not nome_riga:
                continue
            label = nome_riga
            # In caso raro di nomi duplicati, aggiunge solo la marca per poterli distinguere.
            if conteggi_nome.get(nome_riga, 0) > 1:
                marca = str(prod.get("marca") or "").strip()
                label = f"{nome_riga} ({marca})" if marca else f"{nome_riga} #{int(prod['id'])}"
            prod_id = int(prod["id"])
            rigature_catalogo.append((prod_id, label))
            opzioni.append(label)
            ids_da_label[label] = (prod_id, None)
            label_da_id[prod_id] = label

        # Una singola cella può contenere una rigatura oppure una coppia di rigature.
        # Le coppie vengono mostrate con "/" e condividono direzione, Hand drive e zona.
        for idx_a in range(len(rigature_catalogo)):
            id_a, label_a = rigature_catalogo[idx_a]
            for idx_b in range(idx_a + 1, len(rigature_catalogo)):
                id_b, label_b = rigature_catalogo[idx_b]
                pair_label = f"{label_a}/{label_b}"
                opzioni.append(pair_label)
                ids_da_label[pair_label] = (id_a, id_b)

    n_aste = int(numero_aste)
    n_cols = int(numero_colonne)
    col_rig = [f"Rigatura {i}" for i in range(1, n_cols + 1)]

    if needs_load and edit_id is not None:
        df_rows = leggi_df("SELECT id, posizione, numero_sci, note FROM test_rigature_aste WHERE sessione_id = ? ORDER BY id", (int(edit_id),))
        comp = leggi_df(
            """SELECT c.test_rigatura_asta_id, c.colonna_numero, c.direzione, c.hand_drive,
                      c.tecnica_sci, c.zona_da, c.zona_a,
                      p.id AS prodotto_id, p.nome, p.marca, p.tipo, p.materiale, p.larghezza_mm, p.angolo_gradi,
                      p2.id AS prodotto_id_2, p2.nome AS nome_2, p2.marca AS marca_2
               FROM test_rigature_componenti c
               LEFT JOIN catalogo_prodotti p ON p.id = c.rigatura_prodotto_id
               LEFT JOIN catalogo_prodotti p2 ON p2.id = c.rigatura_prodotto_id_2
               JOIN test_rigature_aste a ON a.id = c.test_rigatura_asta_id
               WHERE a.sessione_id = ? ORDER BY c.test_rigatura_asta_id, c.colonna_numero""", (int(edit_id),)
        )
        comp_map = {}
        for _, c in comp.iterrows():
            key_comp = (int(c["test_rigatura_asta_id"]), int(c["colonna_numero"]))
            prod_id = None if pd.isna(c.get("prodotto_id")) else int(c.get("prodotto_id"))
            prod_id_2 = None if pd.isna(c.get("prodotto_id_2")) else int(c.get("prodotto_id_2"))
            if prod_id is None:
                label_comp = "—"
            elif prod_id_2 is not None:
                label_comp = f"{label_da_id.get(prod_id, _testo_pulito(c.get('nome')))}/{label_da_id.get(prod_id_2, _testo_pulito(c.get('nome_2')))}"
            else:
                label_comp = label_da_id.get(prod_id, _rigatura_catalog_label(c))
            comp_map[key_comp] = {
                "label": label_comp,
                "direzione": str(c.get("direzione") or "—").strip() or "—",
                "hand_drive": bool(int(c.get("hand_drive") or 0)),
                "zona_da": str(c.get("zona_da") or "—").strip() or "—",
                "zona_a": str(c.get("zona_a") or "—").strip() or "—",
            }
        righe = []
        for idx, r in df_rows.reset_index(drop=True).iterrows():
            rr = {"_ordine_inserimento": idx, "Posizione": None if pd.isna(r.get("posizione")) else int(r.get("posizione")), "Numero sci": str(r.get("numero_sci") or ""), "Note": str(r.get("note") or "")}
            rid = int(r["id"])
            for i in range(1, n_cols + 1):
                comp_val = comp_map.get((rid, i), {"label": "—", "direzione": "—", "hand_drive": False, "zona_da": "—", "zona_a": "—"})
                rr[f"Rigatura {i}"] = comp_val["label"]
                rr[f"Direzione {i}"] = comp_val["direzione"]
                rr[f"Hand drive {i}"] = comp_val["hand_drive"]
                rr[f"Da {i}"] = comp_val["zona_da"] if comp_val["zona_da"] in zone_tecnica else "—"
                rr[f"A {i}"] = comp_val["zona_a"] if comp_val["zona_a"] in zone_tecnica else "—"
            righe.append(rr)
        if righe:
            st.session_state["rig_test_table_data"] = pd.DataFrame(righe)
            st.session_state["rig_test_table_n"] = len(righe)
            st.session_state["rig_test_table_cols"] = n_cols
            st.session_state["rig_test_table_version"] = st.session_state.get("rig_test_table_version", 0) + 1
        st.session_state["rig_test_edit_loaded_id"] = int(edit_id)

    def _tabella_vuota(n, nc):
        d = {"_ordine_inserimento": list(range(n)), "Posizione": [None] * n, "Numero sci": [""] * n}
        for i in range(1, nc + 1):
            d[f"Rigatura {i}"] = ["—"] * n
            d[f"Direzione {i}"] = ["—"] * n
            d[f"Hand drive {i}"] = [False] * n
            d[f"Da {i}"] = ["—"] * n
            d[f"A {i}"] = ["—"] * n
        d["Note"] = [""] * n
        return pd.DataFrame(d)

    state_key = "rig_test_table_data"
    if "rig_test_table_version" not in st.session_state:
        st.session_state["rig_test_table_version"] = 0
    prev_n = st.session_state.get("rig_test_table_n")
    prev_cols = st.session_state.get("rig_test_table_cols")
    if state_key not in st.session_state or prev_n != n_aste or prev_cols != n_cols:
        nuova = _tabella_vuota(n_aste, n_cols)
        old = st.session_state.get(state_key)
        if isinstance(old, pd.DataFrame) and not old.empty:
            old = old.copy().reset_index(drop=True)
            if "_ordine_inserimento" in old.columns:
                old = old.sort_values("_ordine_inserimento", kind="stable").reset_index(drop=True)
            for idx in range(min(len(old), n_aste)):
                for col in nuova.columns:
                    if col in old.columns:
                        nuova.at[idx, col] = old.at[idx, col]
        st.session_state[state_key] = nuova
        st.session_state["rig_test_table_n"] = n_aste
        st.session_state["rig_test_table_cols"] = n_cols
        st.session_state["rig_test_table_version"] += 1

    df_tab = st.session_state[state_key].copy()

    # Compatibilità con session_state creati da versioni precedenti dell'app.
    # Un redeploy Streamlit può mantenere nel browser una tabella già esistente
    # priva delle nuove colonne Da/A: le creiamo sempre prima del data_editor.
    colonne_richieste = {
        "_ordine_inserimento": list(range(len(df_tab))),
        "Posizione": [None] * len(df_tab),
        "Numero sci": [""] * len(df_tab),
        "Note": [""] * len(df_tab),
    }
    for i in range(1, n_cols + 1):
        colonne_richieste[f"Rigatura {i}"] = ["—"] * len(df_tab)
        colonne_richieste[f"Direzione {i}"] = ["—"] * len(df_tab)
        colonne_richieste[f"Hand drive {i}"] = [False] * len(df_tab)
        colonne_richieste[f"Da {i}"] = ["—"] * len(df_tab)
        colonne_richieste[f"A {i}"] = ["—"] * len(df_tab)

    colonne_aggiunte = False
    for nome_colonna, valori_default in colonne_richieste.items():
        if nome_colonna not in df_tab.columns:
            df_tab[nome_colonna] = valori_default
            colonne_aggiunte = True

    # Mantiene solo il numero di righe richiesto e completa eventuali righe mancanti.
    if len(df_tab) != n_aste:
        nuova = _tabella_vuota(n_aste, n_cols)
        old = df_tab.copy().reset_index(drop=True)
        if "_ordine_inserimento" in old.columns:
            old = old.sort_values("_ordine_inserimento", kind="stable").reset_index(drop=True)
        for idx in range(min(len(old), n_aste)):
            for col in nuova.columns:
                if col in old.columns:
                    nuova.at[idx, col] = old.at[idx, col]
        df_tab = nuova
        colonne_aggiunte = True

    if colonne_aggiunte:
        st.session_state["rig_test_table_version"] += 1

    # Se la tecnica viene cambiata, elimina solo le zone non compatibili con il nuovo schema.
    zone_valide = set(["—"] + zone_tecnica)
    for i in range(1, n_cols + 1):
        for prefisso in ["Da", "A"]:
            col_zona = f"{prefisso} {i}"
            if col_zona in df_tab.columns:
                df_tab[col_zona] = df_tab[col_zona].apply(
                    lambda v: str(v).strip() if str(v).strip() in zone_valide else "—"
                )
    st.session_state[state_key] = df_tab.copy()

    config = {
        "_ordine_inserimento": None,
        "Posizione": st.column_config.NumberColumn("Posizione", min_value=1, max_value=n_aste, step=1, format="%d", width="small"),
        "Numero sci": st.column_config.TextColumn("Numero sci", width="small"),
        "Note": st.column_config.TextColumn("Note", width="large"),
    }
    visible_cols = ["_ordine_inserimento", "Posizione", "Numero sci"]
    for i, col in enumerate(col_rig, start=1):
        config[col] = st.column_config.SelectboxColumn(col, options=opzioni, width="medium", required=False)
        dir_col = f"Direzione {i}"
        hd_col = f"Hand drive {i}"
        da_col = f"Da {i}"
        a_col = f"A {i}"
        config[dir_col] = st.column_config.SelectboxColumn(dir_col, options=["—", "V", "Λ", "VΛ"], width="small", required=False, help="V = un verso, Λ = verso opposto, VΛ = applicata in entrambi i sensi.")
        config[hd_col] = st.column_config.CheckboxColumn(hd_col, width="small", default=False, help="Attiva se la rigatura è stata trascinata con il rotellone SRB Hand drive.")
        config[da_col] = st.column_config.SelectboxColumn(da_col, options=["—"] + zone_tecnica, width="medium", required=False, help="Punto da cui inizia la rigatura sullo sci.")
        config[a_col] = st.column_config.SelectboxColumn(a_col, options=["—"] + zone_tecnica, width="medium", required=False, help="Punto in cui termina la rigatura sullo sci.")
        visible_cols.extend([col, dir_col, hd_col, da_col, a_col])
    visible_cols.append("Note")
    edited = st.data_editor(
        df_tab[visible_cols], hide_index=True, use_container_width=True,
        height=min(650, 38 + n_aste * 36), column_config=config,
        key=f"rig_test_editor_{n_aste}_{n_cols}_{st.session_state['rig_test_table_version']}",
    )
    st.session_state[state_key] = edited.copy()

    co1, co2, _ = st.columns([1.4, 1.4, 4])
    with co1:
        if st.button("↕ Riordina per classifica", use_container_width=True, key="rig_test_sort_rank"):
            tab = st.session_state[state_key].copy()
            tab["_pos_sort"] = pd.to_numeric(tab["Posizione"], errors="coerce")
            tab = tab.sort_values(["_pos_sort", "_ordine_inserimento"], na_position="last", kind="stable").drop(columns=["_pos_sort"]).reset_index(drop=True)
            st.session_state[state_key] = tab
            st.session_state["rig_test_table_version"] += 1
            st.rerun()
    with co2:
        if st.button("↺ Ripristina ordine inserimento", use_container_width=True, key="rig_test_reset_order"):
            tab = st.session_state[state_key].copy().sort_values("_ordine_inserimento", kind="stable").reset_index(drop=True)
            st.session_state[state_key] = tab
            st.session_state["rig_test_table_version"] += 1
            st.rerun()

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    salva = st.button(
        "Salva modifiche test" if edit_id is not None else "Salva test rigature manuali",
        type="primary", use_container_width=True, key="save_rig_test",
    )
    if not salva:
        return
    if not str(luogo or "").strip():
        st.error("Inserisci il luogo del test.")
        return
    try:
        taria = _parse_temperatura_1d(taria_txt)
        tneve = _parse_temperatura_1d(tneve_txt)
    except Exception:
        st.error("Controlla temperatura aria e temperatura neve. Usa valori come -3.0 o 0.0.")
        return

    righe_salva = []
    for _, r in st.session_state[state_key].iterrows():
        numero_sci = str(r.get("Numero sci") or "").strip()
        note = str(r.get("Note") or "").strip()
        pos_raw = r.get("Posizione")
        pos = None if pos_raw is None or pd.isna(pos_raw) or not str(pos_raw).strip() else int(float(pos_raw))
        componenti = []
        for i, col in enumerate(col_rig, start=1):
            lab = str(r.get(col) or "—").strip()
            prod_id, prod_id_2 = ids_da_label.get(lab, (None, None))
            direzione = str(r.get(f"Direzione {i}") or "—").strip() or "—"
            hand_drive = bool(r.get(f"Hand drive {i}") or False)
            zona_da = str(r.get(f"Da {i}") or "—").strip() or "—"
            zona_a = str(r.get(f"A {i}") or "—").strip() or "—"
            componenti.append({
                "prod_id": prod_id,
                "prod_id_2": prod_id_2,
                "direzione": direzione,
                "hand_drive": hand_drive,
                "tecnica_sci": tecnica_sci,
                "zona_da": zona_da,
                "zona_a": zona_a,
            })
        if not numero_sci and not any(c["prod_id"] for c in componenti) and not note:
            continue
        righe_salva.append({"posizione": pos, "numero_sci": numero_sci, "componenti": componenti, "note": note})
    if not righe_salva:
        st.error("Compila almeno una riga della tabella prima di salvare il test.")
        return

    conn = apri_connessione_database()
    try:
        if edit_id is not None:
            sid = int(edit_id)
            conn.execute(
                """UPDATE sessioni SET data=?, ora=?, luogo=?, temperatura_aria=?, temperatura_neve=?, umidita=?, meteo=?,
                   snow_origine=?, snow_consistenza=?, snow_fondo=?, snow_umidita=?, snow_forma_grano=?, snow_granulometria=?, snow_caratteristiche=?,
                   zero_modello_sci=?, tipo_test=?, zero_riferimento_id=? WHERE id=?""",
                (data_test.isoformat(), ora.strftime("%H:%M"), str(luogo).strip(), taria, tneve,
                 None if ur_missing else int(ur), meteo or "",
                 _compatta_neve_sessione(origine, snow_options["Origine"]),
                 _compatta_neve_sessione(consistenza, snow_options["Consistenza"]),
                 _compatta_neve_sessione(fondo, snow_options["Fondo sottostante"]),
                 _compatta_neve_sessione(umidita_neve, snow_options["Umidità neve"]),
                 _compatta_neve_sessione(forma, snow_options["Forma grano"]),
                 _compatta_neve_sessione(granulometria, snow_options["Granulometria"]),
                 _compatta_neve_sessione(caratteristiche, snow_options["Caratteristiche"]),
                 str(modello_sci or "").strip(), f"Test rigature manuali · {metodo_test}",
                 int(zero_ref_id) if zero_ref_id is not None else None, sid)
            )
            ids_old = [int(x[0]) for x in conn.execute("SELECT id FROM test_rigature_aste WHERE sessione_id = ?", (sid,)).fetchall()]
            for rid in ids_old:
                conn.execute("DELETE FROM test_rigature_componenti WHERE test_rigatura_asta_id = ?", (rid,))
            conn.execute("DELETE FROM test_rigature_aste WHERE sessione_id = ?", (sid,))
        else:
            cur = conn.execute(
                """INSERT INTO sessioni (data, ora, luogo, temperatura_aria, temperatura_neve, umidita, meteo, tipo_neve, condizione_pista,
                   snow_origine, snow_consistenza, snow_fondo, snow_umidita, snow_forma_grano, snow_granulometria, snow_caratteristiche,
                   zero_modello_sci, tipo_test, zero_riferimento_id, note, creato_il)
                   VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?)""",
                (data_test.isoformat(), ora.strftime("%H:%M"), str(luogo).strip(), taria, tneve,
                 None if ur_missing else int(ur), meteo or "",
                 _compatta_neve_sessione(origine, snow_options["Origine"]),
                 _compatta_neve_sessione(consistenza, snow_options["Consistenza"]),
                 _compatta_neve_sessione(fondo, snow_options["Fondo sottostante"]),
                 _compatta_neve_sessione(umidita_neve, snow_options["Umidità neve"]),
                 _compatta_neve_sessione(forma, snow_options["Forma grano"]),
                 _compatta_neve_sessione(granulometria, snow_options["Granulometria"]),
                 _compatta_neve_sessione(caratteristiche, snow_options["Caratteristiche"]),
                 str(modello_sci or "").strip(), f"Test rigature manuali · {metodo_test}",
                 int(zero_ref_id) if zero_ref_id is not None else None, datetime.now().isoformat(timespec="seconds"))
            )
            sid = int(cur.lastrowid)
        for rr in righe_salva:
            cur = conn.execute(
                "INSERT INTO test_rigature_aste (sessione_id, posizione, numero_sci, note, creato_il) VALUES (?, ?, ?, ?, ?)",
                (sid, rr["posizione"], rr["numero_sci"], rr["note"], datetime.now().isoformat(timespec="seconds"))
            )
            asta_id = int(cur.lastrowid)
            for idx, componente in enumerate(rr["componenti"], start=1):
                prod_id = componente.get("prod_id")
                if prod_id is not None:
                    conn.execute(
                        """INSERT INTO test_rigature_componenti
                           (test_rigatura_asta_id, colonna_numero, rigatura_prodotto_id, rigatura_prodotto_id_2, direzione, hand_drive, tecnica_sci, zona_da, zona_a)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            asta_id, idx, int(prod_id),
                            int(componente.get("prod_id_2")) if componente.get("prod_id_2") is not None else None,
                            str(componente.get("direzione") or "—"),
                            1 if componente.get("hand_drive") else 0,
                            str(componente.get("tecnica_sci") or tecnica_sci),
                            str(componente.get("zona_da") or "—"),
                            str(componente.get("zona_a") or "—"),
                        )
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    _invalida_cache_dati()
    st.session_state["rig_test_history_notice"] = (
        f"Test rigature manuali aggiornato correttamente · {len(righe_salva)} righe registrate."
        if edit_id is not None else
        f"Test rigature manuali salvato correttamente · {len(righe_salva)} righe registrate."
    )
    for k in ["rig_test_edit_session_id", "rig_test_edit_loaded_id", "rig_test_table_data", "rig_test_table_n", "rig_test_table_cols"]:
        st.session_state.pop(k, None)
    st.rerun()


def _carica_righe_test_rigature(sessione_id):
    df_rows = leggi_df(
        "SELECT id, posizione, numero_sci, note FROM test_rigature_aste WHERE sessione_id = ? ORDER BY id",
        (int(sessione_id),)
    )
    df_comp = leggi_df(
        """SELECT c.test_rigatura_asta_id, c.colonna_numero, c.direzione, c.hand_drive,
                  c.tecnica_sci, c.zona_da, c.zona_a,
                  p.id AS prodotto_id, p.nome, p.marca, p.tipo, p.materiale, p.larghezza_mm, p.angolo_gradi,
                  p.foto_data, p.foto_mime,
                  p2.id AS prodotto_id_2, p2.nome AS nome_2, p2.marca AS marca_2,
                  p2.tipo AS tipo_2, p2.materiale AS materiale_2, p2.larghezza_mm AS larghezza_mm_2,
                  p2.angolo_gradi AS angolo_gradi_2, p2.foto_data AS foto_data_2, p2.foto_mime AS foto_mime_2
           FROM test_rigature_componenti c
           JOIN test_rigature_aste a ON a.id = c.test_rigatura_asta_id
           LEFT JOIN catalogo_prodotti p ON p.id = c.rigatura_prodotto_id
           LEFT JOIN catalogo_prodotti p2 ON p2.id = c.rigatura_prodotto_id_2
           WHERE a.sessione_id = ? ORDER BY c.test_rigatura_asta_id, c.colonna_numero""",
        (int(sessione_id),)
    )
    return df_rows, df_comp


def _render_podio_rigature(df_rows, df_comp):
    if df_rows.empty:
        return
    st.markdown(
        """
        <style>
        .rig-podium-wrap { margin:.35rem 0 1.1rem 0; padding:1rem 1rem .15rem 1rem; border:1px solid #d8dde3; border-radius:14px; background:linear-gradient(180deg,#fff 0%,#f7f9fa 100%); overflow-x:auto; }
        .rig-podium { min-width:800px; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.8rem; align-items:end; }
        .rig-podium-entry { display:flex; flex-direction:column; justify-content:flex-end; min-width:0; }
        .rig-podium-card { position:relative; background:#fff; border:1px solid #d8dde3; border-radius:12px 12px 8px 8px; padding:1rem .75rem .8rem; box-shadow:0 7px 18px rgba(31,41,51,.07); min-height:260px; display:flex; align-items:center; justify-content:center; }
        .rig-podium-first .rig-podium-card { border-color:#d8b54c; box-shadow:0 9px 24px rgba(31,41,51,.10); }
        .rig-work-row { display:flex; align-items:center; justify-content:center; gap:.45rem; width:100%; min-width:0; }
        .rig-work-block { flex:1 1 0; min-width:0; text-align:center; }
        .rig-work-plus { flex:0 0 auto; color:#1f2a33; font-size:1.7rem; line-height:1; font-weight:850; padding:0 .05rem; transform:translateY(-10px); }
        .rig-pair-images { display:flex; align-items:center; justify-content:center; gap:.25rem; width:100%; min-height:118px; margin:0 auto .38rem; }
        .rig-pair-images img { width:min(105px,46%); height:112px; object-fit:contain; display:block; }
        .rig-pair-images.single img { width:148px; max-width:92%; height:148px; }
        .rig-image-placeholder { width:90px; height:112px; display:flex; align-items:center; justify-content:center; color:#a5b0b8; font-size:.65rem; font-weight:700; }
        .rig-work-name-wrap { position:relative; display:inline-flex; justify-content:center; max-width:100%; }
        .rig-work-name { color:#263238; font-size:.86rem; line-height:1.15; font-weight:780; overflow-wrap:anywhere; cursor:help; border-bottom:1px dotted rgba(38,50,56,.32); }
        .rig-work-tooltip { position:fixed; top:150px; right:32px; width:min(560px,42vw); padding:1rem 1.05rem; background:#fff; color:#263238; border:1px solid #d7dee4; border-radius:16px; box-shadow:0 22px 58px rgba(25,39,52,.26); text-align:left; white-space:normal; opacity:0; visibility:hidden; transform:translateY(8px) scale(.985); pointer-events:none; transition:opacity .14s ease, transform .14s ease, visibility .14s ease; z-index:2147483647; }
        .rig-tooltip-title { font-size:1rem; line-height:1.2; font-weight:850; margin:0 0 .65rem 0; color:#1f2a33; }
        .rig-tooltip-ski { position:relative; width:100%; min-height:122px; overflow:hidden; border-radius:10px; background:#fff; }
        .rig-tooltip-ski img { display:block; width:100%; min-height:122px; height:auto; object-fit:contain; }
        .rig-tooltip-zone { position:absolute; top:32.4%; height:8.8%; background:rgba(0,174,239,.50); border-top:2px solid #00aeea; border-bottom:2px solid #00aeea; box-shadow:0 0 0 1px rgba(0,174,239,.12); border-radius:4px; }
        .rig-tooltip-divider { height:1px; background:#e5eaee; margin:.8rem 0 .7rem; }
        .rig-tooltip-meta-row { display:flex; align-items:center; gap:.75rem; min-height:44px; }
        .rig-tooltip-wheel { width:74px; height:74px; flex:0 0 74px; object-fit:contain; border-radius:10px; background:#fff; }
        .rig-tooltip-meta { min-width:0; color:#3f4d57; font-size:.78rem; line-height:1.4; font-weight:650; }
        .rig-tooltip-handdrive { display:inline-flex; align-items:center; gap:.3rem; margin-bottom:.28rem; padding:.24rem .48rem; border-radius:8px; background:#eaf5ff; color:#1879b5; font-size:.72rem; font-weight:800; }
        .rig-tooltip-detail { color:#3f4d57; font-size:.78rem; font-weight:650; }
        .rig-work-name-wrap:hover .rig-work-tooltip { opacity:1; visibility:visible; transform:translateY(0) scale(1); }
        @media (max-width: 980px) { .rig-work-tooltip { right:12px; width:min(520px,76vw); top:120px; } }
        .rig-podium-step { display:flex; align-items:flex-start; justify-content:center; border:1px solid #cfd6dc; border-top-width:4px; border-radius:5px 5px 0 0; background:#eef1f4; margin:.35rem .25rem 0; padding-top:.6rem; }
        .rig-podium-step-first { height:108px; border-top-color:#d4af37; background:linear-gradient(180deg,#fffaf0 0%,#eef1f4 100%); }
        .rig-podium-step-second { height:78px; border-top-color:#aeb7bf; }
        .rig-podium-step-third { height:58px; border-top-color:#b97a45; }
        .rig-podium-rank { color:#263238; font-size:1.05rem; line-height:1; font-weight:850; }
        </style>
        """, unsafe_allow_html=True
    )

    comp_by_row = {}
    for _, c in df_comp.iterrows():
        comp_by_row.setdefault(int(c["test_rigatura_asta_id"]), []).append(c.to_dict())
    for rid in comp_by_row:
        comp_by_row[rid].sort(key=lambda x: int(x.get("colonna_numero") or 0))

    by_pos = {}
    for _, r in df_rows.iterrows():
        try:
            pos = int(float(r.get("posizione")))
        except Exception:
            continue
        if pos in (1, 2, 3) and pos not in by_pos:
            by_pos[pos] = r.to_dict()

    def work_html(c):
        label = _rigatura_component_label(c)
        imgs = []
        src1 = _rigatura_image_src(c.get("foto_data"), c.get("foto_mime"))
        src2 = _rigatura_image_src(c.get("foto_data_2"), c.get("foto_mime_2"))
        for src, alt in [(src1, _testo_pulito(c.get("nome"))), (src2, _testo_pulito(c.get("nome_2")))]:
            if src:
                imgs.append(f'<img src="{src}" alt="{html_escape(alt)}">')
        if not imgs:
            imgs_html = '<div class="rig-image-placeholder">Nessuna foto</div>'
        else:
            imgs_html = "".join(imgs)
        pair_class = "single" if len(imgs) <= 1 and not _testo_pulito(c.get("nome_2")) else ""
        direzione = str(c.get("direzione") or "—").strip() or "—"
        hd = bool(int(c.get("hand_drive") or 0))
        tecnica = str(c.get("tecnica_sci") or "Skating").strip() or "Skating"
        zona_da = c.get("zona_da")
        zona_a = c.get("zona_a")
        zona = _zona_rigatura_testo(zona_da, zona_a)

        schema_src = _schema_zone_rigatura_src(tecnica)
        overlay = _zona_overlay_rigatura(tecnica, zona_da, zona_a)
        overlay_html = ""
        if overlay is not None:
            left, width = overlay
            overlay_html = f'<div class="rig-tooltip-zone" style="left:{left:.2f}%;width:{width:.2f}%;"></div>'
        ski_html = (
            f'<div class="rig-tooltip-ski"><img src="{schema_src}" alt="Schema zone {html_escape(tecnica)}">{overlay_html}</div>'
            if schema_src else ""
        )

        dettagli = []
        if direzione != "—":
            dettagli.append(direzione)
        if zona != "—":
            dettagli.append(zona)
        dettaglio_html = " · ".join(html_escape(x) for x in dettagli) if dettagli else "Dettagli non specificati"

        wheel_html = ""
        handdrive_badge = ""
        if hd:
            wheel_src = _HAND_DRIVE_WHEEL_DATA_URL
            if wheel_src:
                wheel_html = f'<img class="rig-tooltip-wheel" src="{wheel_src}" alt="Rotella Hand drive">'
            handdrive_badge = '<div class="rig-tooltip-handdrive">⚙ Hand drive</div>'

        tooltip_html = (
            f'<div class="rig-work-tooltip">'
            f'<div class="rig-tooltip-title">{html_escape(label)}</div>'
            f'{ski_html}'
            f'<div class="rig-tooltip-divider"></div>'
            f'<div class="rig-tooltip-meta-row">{wheel_html}'
            f'<div class="rig-tooltip-meta">{handdrive_badge}<div class="rig-tooltip-detail">{dettaglio_html}</div></div>'
            f'</div></div>'
        )
        return (
            '<div class="rig-work-block">'
            f'<div class="rig-pair-images {pair_class}">{imgs_html}</div>'
            '<div class="rig-work-name-wrap">'
            f'<div class="rig-work-name">{html_escape(label)}</div>'
            f'{tooltip_html}'
            '</div>'
            '</div>'
        )

    def entry(pos):
        r = by_pos.get(pos)
        cls = {1:"first",2:"second",3:"third"}[pos]
        if not r:
            return f'<div class="rig-podium-entry rig-podium-{cls}"><div class="rig-podium-card"></div><div class="rig-podium-step rig-podium-step-{cls}"><span class="rig-podium-rank">{pos}°</span></div></div>'
        comps = comp_by_row.get(int(r["id"]), [])
        works = []
        for idx, c in enumerate(comps):
            if idx > 0:
                # + SOLO tra celle/lavorazioni diverse. Una coppia dentro la stessa cella usa "/" nel nome.
                works.append('<div class="rig-work-plus">+</div>')
            works.append(work_html(c))
        content = "".join(works) if works else '<div class="rig-work-block"><div class="rig-work-name">—</div></div>'
        return (
            f'<div class="rig-podium-entry rig-podium-{cls}">'
            f'<div class="rig-podium-card"><div class="rig-work-row">{content}</div></div>'
            f'<div class="rig-podium-step rig-podium-step-{cls}"><span class="rig-podium-rank">{pos}°</span></div>'
            '</div>'
        )

    st.markdown(
        '<div class="rig-podium-wrap"><div class="rig-podium">' + entry(2) + entry(1) + entry(3) + '</div></div>',
        unsafe_allow_html=True,
    )


def _render_tabella_rigature(df_rows, df_comp):
    """Tabella rigature con nome compatto e preview foto al passaggio del mouse."""
    if df_rows.empty:
        return

    max_col = 0
    comp_map = {}
    for _, c in df_comp.iterrows():
        rid = int(c["test_rigatura_asta_id"])
        n = int(c["colonna_numero"])
        max_col = max(max_col, n)
        comp_map[(rid, n)] = c.to_dict()

    def hover_cell(c):
        if not c:
            return '<div class="rig-table-empty">—</div>'
        label = _rigatura_component_label(c)
        if label == "—":
            return '<div class="rig-table-empty">—</div>'
        previews = []
        for foto_key, mime_key, nome_key in [
            ("foto_data", "foto_mime", "nome"),
            ("foto_data_2", "foto_mime_2", "nome_2"),
        ]:
            src = _rigatura_image_src(c.get(foto_key), c.get(mime_key))
            if src:
                previews.append(f'<img src="{src}" alt="{html_escape(_testo_pulito(c.get(nome_key)))}">')
        preview_html = ""
        if previews:
            preview_html = '<div class="rig-hover-preview"><div class="rig-hover-images">' + "".join(previews) + '</div></div>'
        return (
            '<div class="rig-hover-target">'
            f'<span class="rig-table-name">{html_escape(label)}</span>'
            f'{preview_html}'
            '</div>'
        )

    headers = ['<th class="col-pos">Posizione</th>', '<th class="col-sci">Numero sci</th>']
    for i in range(1, max_col + 1):
        headers += [
            f'<th class="col-rig">Rigatura {i}</th>',
            f'<th class="col-dir">Direzione {i}</th>',
            f'<th class="col-hand">Hand drive {i}</th>',
            f'<th class="col-zone">Zona {i}</th>',
        ]
    headers.append('<th class="col-note">Note</th>')

    rows_html = []
    for _, r in df_rows.iterrows():
        rid = int(r["id"])
        cells = [
            f'<td class="col-pos">{html_escape(str(r.get("posizione") if not pd.isna(r.get("posizione")) else "—"))}</td>',
            f'<td class="col-sci">{html_escape(str(r.get("numero_sci") or "—"))}</td>',
        ]
        for i in range(1, max_col + 1):
            c = comp_map.get((rid, i))
            if c:
                direzione = str(c.get("direzione") or "—").strip() or "—"
                hand = "Sì" if bool(int(c.get("hand_drive") or 0)) else "—"
                zona = _zona_rigatura_testo(c.get("zona_da"), c.get("zona_a"))
            else:
                direzione, hand, zona = "—", "—", "—"
            cells += [
                f'<td class="col-rig">{hover_cell(c)}</td>',
                f'<td class="col-dir">{html_escape(direzione)}</td>',
                f'<td class="col-hand">{html_escape(hand)}</td>',
                f'<td class="col-zone">{html_escape(zona)}</td>',
            ]
        cells.append(f'<td class="col-note">{html_escape(str(r.get("note") or "—"))}</td>')
        rows_html.append('<tr>' + ''.join(cells) + '</tr>')

    min_width = 300 + max_col * 560
    st.markdown(
        f"""
        <style>
        .rig-detail-wrap {{ overflow-x:auto; overflow-y:visible; border:1px solid #dbe1e6; border-radius:14px; background:#fff; margin-top:.45rem; box-shadow:0 8px 24px rgba(31,41,51,.05); }}
        table.rig-detail-table {{ width:100%; min-width:{min_width}px; border-collapse:separate; border-spacing:0; table-layout:fixed; color:#263238; font-size:.74rem; }}
        .rig-detail-table th {{ background:#f3f6f8; color:#51606b; font-size:.73rem; font-weight:700; text-align:center; padding:.58rem .42rem; border-bottom:1px solid #dbe1e6; white-space:nowrap; }}
        .rig-detail-table td {{ padding:.54rem .42rem; border-bottom:1px solid #e7ebef; vertical-align:middle; position:relative; text-align:center; background:#fff; }}
        .rig-detail-table tbody tr:nth-child(even) td {{ background:#fbfcfd; }}
        .rig-detail-table tr:last-child td {{ border-bottom:0; }}
        .rig-detail-table .col-pos {{ width:70px; }} .rig-detail-table .col-sci {{ width:90px; }}
        .rig-detail-table .col-rig {{ width:150px; }} .rig-detail-table .col-dir {{ width:85px; }}
        .rig-detail-table .col-hand {{ width:95px; }} .rig-detail-table .col-zone {{ width:205px; }} .rig-detail-table .col-note {{ width:150px; }}
        .rig-hover-target {{ position:relative; display:inline-block; max-width:100%; cursor:zoom-in; }}
        .rig-table-name {{ font-weight:600; line-height:1.18; overflow-wrap:anywhere; transition:color .12s ease; }}
        .rig-hover-target:hover .rig-table-name {{ color:#007ea8; }}
        .rig-hover-preview {{ position:fixed; top:138px; right:32px; width:min(430px,32vw); height:min(390px,52vh); padding:14px; background:#fff; border:1px solid #c8d0d7; border-radius:15px; box-shadow:0 24px 64px rgba(31,41,51,.34); opacity:0; visibility:hidden; transform:translateY(8px) scale(.97); pointer-events:none; z-index:2147483647!important; transition:opacity .12s ease,transform .12s ease,visibility .12s ease; }}
        .rig-hover-images {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center; gap:12px; }}
        .rig-hover-images img {{ max-width:48%; width:auto; height:100%; object-fit:contain; display:block; }}
        .rig-hover-images img:only-child {{ max-width:100%; }}
        .rig-hover-target:hover .rig-hover-preview {{ opacity:1; visibility:visible; transform:translateY(0) scale(1); }}
        .rig-table-empty {{ color:#9aa5ad; }}
        </style>
        <div class="rig-detail-wrap">
            <table class="rig-detail-table">
                <thead><tr>{''.join(headers)}</tr></thead>
                <tbody>{''.join(rows_html)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _nome_file_pdf_test_rigature(test):
    data=str(test.get("data") or "test").replace("/","-")
    luogo=re.sub(r"[^A-Za-z0-9_-]+","_",str(test.get("luogo") or "")).strip("_")
    return f"SnowDataPro_test_rigature_{data}" + (f"_{luogo}" if luogo else "") + ".pdf"


def _crea_pdf_test_rigature(test, df_rows, df_comp):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    buf=BytesIO(); doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm,title="SnowDataPro - Test rigature manuali")
    styles=getSampleStyleSheet(); story=[Paragraph("SnowDataPro - Test rigature manuali",styles["Title"]),Spacer(1,4*mm)]
    metodo=str(test.get("tipo_test") or "").replace("Test rigature manuali · ","")
    story.append(Paragraph(f"{test.get('data','')} · {test.get('luogo','')} · {metodo}",styles["Heading2"]))
    comp_map={}; max_col=0
    for _,c in df_comp.iterrows():
        rid=int(c["test_rigatura_asta_id"]); n=int(c["colonna_numero"]); max_col=max(max_col,n)
        comp_map[(rid,n)] = {
            "nome": _rigatura_component_label(c) or "-",
            "direzione": str(c.get("direzione") or "—").strip() or "—",
            "hand_drive": bool(int(c.get("hand_drive") or 0)),
            "zona": _zona_rigatura_testo(c.get("zona_da"), c.get("zona_a")),
        }
    header=["Pos.","Sci"]
    for i in range(1,max_col+1):
        header += [f"Rigatura {i}", f"Dir. {i}", f"Hand drive {i}", f"Zona {i}"]
    header += ["Note"]
    data=[header]
    for _,r in df_rows.iterrows():
        rid=int(r["id"]); row=[str(r.get("posizione") or "-"),str(r.get("numero_sci") or "-")]
        for i in range(1,max_col+1):
            comp=comp_map.get((rid,i), {"nome":"-", "direzione":"-", "hand_drive":False, "zona":"-"})
            row += [comp["nome"], comp["direzione"], "Sì" if comp["hand_drive"] else "-", comp["zona"]]
        row += [str(r.get("note") or "-")]
        data.append(row)
    tab=Table(data,repeatRows=1); tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eef1f4")),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#d8dde3")),("FONTSIZE",(0,0),(-1,-1),7),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,0),(-1,-1),"CENTER")]))
    story.append(tab); doc.build(story); return buf.getvalue()

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
    zero_snow_options = _snow_option_groups_standard()

    st.markdown('<div class="insert-test-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="insert-test-title">Classificazione neve</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="insert-test-caption">Usa la stessa classificazione indipendente già adottata nel catalogo scioline.</div>',
        unsafe_allow_html=True,
    )

    z1, z2, z3, z4 = st.columns(4)
    with z1:
        zero_origine = st.multiselect(
            "Origine", zero_snow_options["Origine"],
            default=_valori_sessione_neve(riga_sessione.get("snow_origine") if riga_sessione is not None else "", zero_snow_options["Origine"]),
            key=f"insert_zero_origin_{suffix_zero}", placeholder="Seleziona origine",
        )
    with z2:
        zero_consistenza = st.multiselect(
            "Consistenza superficiale", zero_snow_options["Consistenza"],
            default=_valori_sessione_neve(riga_sessione.get("snow_consistenza") if riga_sessione is not None else "", zero_snow_options["Consistenza"]),
            key=f"insert_zero_consistency_{suffix_zero}", placeholder="Seleziona consistenza",
        )
    with z3:
        zero_fondo = st.multiselect(
            "Fondo sottostante", zero_snow_options["Fondo sottostante"],
            default=_valori_sessione_neve(riga_sessione.get("snow_fondo") if riga_sessione is not None else "", zero_snow_options["Fondo sottostante"]),
            key=f"insert_zero_base_condition_{suffix_zero}", placeholder="Seleziona fondo",
        )
    with z4:
        zero_umidita = st.multiselect(
            "Umidità neve", zero_snow_options["Umidità neve"],
            default=_valori_sessione_neve(riga_sessione.get("snow_umidita") if riga_sessione is not None else "", zero_snow_options["Umidità neve"]),
            key=f"insert_zero_humidity_{suffix_zero}", placeholder="Seleziona umidità neve",
        )

    z5, z6, z7 = st.columns(3)
    with z5:
        zero_forma = st.multiselect(
            "Forma grano", zero_snow_options["Forma grano"],
            default=_valori_sessione_neve(riga_sessione.get("snow_forma_grano") if riga_sessione is not None else "", zero_snow_options["Forma grano"]),
            key=f"insert_zero_grain_{suffix_zero}", placeholder="Seleziona forma grano",
        )
    with z6:
        zero_granulometria = st.multiselect(
            "Granulometria", zero_snow_options["Granulometria"],
            default=_valori_sessione_neve(riga_sessione.get("snow_granulometria") if riga_sessione is not None else "", zero_snow_options["Granulometria"]),
            key=f"insert_zero_size_{suffix_zero}", placeholder="Seleziona granulometria",
        )
    with z7:
        zero_caratteristiche = st.multiselect(
            "Caratteristiche", zero_snow_options["Caratteristiche"],
            default=_valori_sessione_neve(riga_sessione.get("snow_caratteristiche") if riga_sessione is not None else "", zero_snow_options["Caratteristiche"]),
            key=f"insert_zero_features_{suffix_zero}", placeholder="Seleziona caratteristiche",
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
                    "snow_fondo": _compatta_neve_sessione(zero_fondo, zero_snow_options["Fondo sottostante"]),
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
        [Paragraph("Origine", label_style), para(test.get("snow_origine")), Paragraph("Consistenza sup.", label_style), para(test.get("snow_consistenza")), Paragraph("Fondo", label_style), para(test.get("snow_fondo"))],
        [Paragraph("Umidità neve", label_style), para(test.get("snow_umidita")), Paragraph("Forma grano", label_style), para(_normalizza_forma_grano_testo(test.get("snow_forma_grano"))), Paragraph("Granulometria", label_style), para(test.get("snow_granulometria"))],
        [Paragraph("Caratteristiche", label_style), para(test.get("snow_caratteristiche")), "", "", "", ""],
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
            min-height: 238px;
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
            gap: .82rem;
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
            height: 108px;
            object-fit: contain;
            display: flex;
            align-items: center;
            justify-content: center;
            background: transparent;
            border: none;
            border-radius: 0;
            box-shadow: none;
            margin: 0 auto .45rem auto;
            padding: 0;
        }
        .podium-product-image.podium-single-image,
        .podium-product-placeholder.podium-single-image {
            width: 152px;
            height: 152px;
        }
        .podium-product-placeholder span {
            color: #a5b0b8;
            font-size: .62rem;
            font-weight: 800;
            letter-spacing: .08em;
        }
        .podium-product-category {
            color: #8a98a3;
            font-size: .64rem;
            line-height: 1.08;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: .04em;
            margin-bottom: .18rem;
        }
        .podium-product-name {
            color: #263238;
            font-size: .86rem;
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
            border: 1px solid #dbe1e6;
            border-radius: 14px;
            background: #ffffff;
            margin-top: .45rem;
            position: relative;
            z-index: 1;
            box-shadow: 0 8px 24px rgba(31, 41, 51, .05);
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
            font-size: .74rem;
            font-weight: 500;
        }}
        .scroll-test-table th {{
            background: #f3f6f8;
            color: #51606b;
            font-size: .73rem;
            font-weight: 700;
            text-align: center;
            padding: .58rem .42rem;
            border-bottom: 1px solid #dbe1e6;
            white-space: nowrap;
            line-height: 1.15;
        }}
        .scroll-test-table td {{
            padding: .54rem .42rem;
            border-bottom: 1px solid #e7ebef;
            vertical-align: middle;
            overflow: visible;
            position: relative;
            color: #263238;
            font-size: .74rem;
            font-weight: 500;
            line-height: 1.18;
            text-align: center;
        }}
        .scroll-test-table tr:last-child td {{ border-bottom: 0; }}
        .scroll-test-table tbody tr:nth-child(even) td {{ background: #fbfcfd; }}
        .scroll-test-table th.col-posizione, .scroll-test-table td.col-posizione {{ width: 62px; text-align:center; }}
        .scroll-test-table th.col-sci, .scroll-test-table td.col-sci {{ width: 88px; text-align:center; }}
        .scroll-test-table th.col-prodotto, .scroll-test-table td.col-prodotto {{ width: 158px; text-align:center; }}
        .scroll-test-table th.col-note, .scroll-test-table td.col-note {{ width: 170px; text-align:center; }}
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
            line-height: 1.18;
            font-weight: 500;
            font-size: .74rem;
            color: #263238;
            white-space: normal;
            overflow-wrap: anywhere;
            text-align: center;
            transition: color .12s ease;
        }}
        .test-product-hover-target:hover .test-product-name {{
            color: #007ea8;
        }}
        .scroll-test-table tbody tr.test-winner td {{
            background: #fdfefe;
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
            line-height: 1.18;
            white-space: normal;
            font-size: .74rem;
            font-weight: 500;
            text-align: center;
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
        numero_sci = html_escape(str(record.get("numero_sci") or "—"))
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
                s.snow_fondo,
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
            filtro1, filtro2, filtro3, filtro4 = st.columns(4)

            with filtro1:
                luoghi_zero = ["Tutti"] + sorted(
                    [
                        str(v).strip()
                        for v in df_zero_storico["luogo"].dropna().unique().tolist()
                        if str(v).strip()
                    ]
                )
                storico_zero_luogo = st.selectbox(
                    "Luogo", luoghi_zero, key="zero_storico_filtro_luogo"
                )

            with filtro2:
                storico_zero_consistenza = st.selectbox(
                    "Consistenza superficiale",
                    ["Tutte"] + _snow_option_groups_standard()["Consistenza"],
                    key="zero_storico_filtro_consistenza",
                )

            with filtro3:
                storico_zero_fondo = st.selectbox(
                    "Fondo sottostante",
                    ["Tutti"] + _snow_option_groups_standard()["Fondo sottostante"],
                    key="zero_storico_filtro_fondo",
                )

            with filtro4:
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

            if storico_zero_fondo != "Tutti":
                def _match_fondo_zero(valore):
                    voci = {v.strip() for v in str(valore or "").split(",") if v.strip()}
                    return "Tutte" in voci or storico_zero_fondo in voci

                df_zero_filtrato = df_zero_filtrato[
                    df_zero_filtrato["snow_fondo"].apply(_match_fondo_zero)
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
                            ("Consistenza superficiale", sessione_zero.get("snow_consistenza")),
                            ("Fondo sottostante", sessione_zero.get("snow_fondo")),
                            ("Umidità neve", sessione_zero.get("snow_umidita")),
                            ("Forma grano", _normalizza_forma_grano_testo(sessione_zero.get("snow_forma_grano"))),
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
                s.umidita, s.meteo, s.snow_origine, s.snow_consistenza, s.snow_fondo, s.snow_umidita,
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
                        ("Consistenza superficiale", test.get("snow_consistenza")),
                        ("Fondo sottostante", test.get("snow_fondo")),
                        ("Umidità neve", test.get("snow_umidita")),
                        ("Forma grano", _normalizza_forma_grano_testo(test.get("snow_forma_grano"))),
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
            "Database cronologico dei test rigature manuali. Inserimento e storico nello stesso punto.",
        )
        _stile_moduli_test()

        st.markdown('<div class="section-title">Storico test rigature manuali</div>', unsafe_allow_html=True)
        if st.session_state.get("rig_test_history_notice"):
            st.success(st.session_state.pop("rig_test_history_notice"))
        st.write("Archivio dei test rigature manuali. Apri un test per vedere condizioni, combinazioni e classifica.")

        rig_edit_active = st.session_state.get("rig_test_edit_session_id") is not None
        rig_form_label = "✎ Modifica test rigature manuali" if rig_edit_active else "＋ Nuovo test rigature manuali"
        with st.expander(rig_form_label, expanded=rig_edit_active):
            render_form_test_rigature()

        df_rig_storico = leggi_df(
            """
            SELECT s.id, s.data, s.ora, s.luogo, s.temperatura_aria, s.temperatura_neve,
                   s.umidita, s.meteo, s.snow_origine, s.snow_consistenza, s.snow_fondo, s.snow_umidita,
                   s.snow_forma_grano, s.snow_granulometria, s.snow_caratteristiche,
                   s.zero_modello_sci, s.tipo_test, s.zero_riferimento_id, s.note, s.creato_il,
                   COUNT(a.id) AS righe_test
            FROM sessioni s
            LEFT JOIN test_rigature_aste a ON a.sessione_id = s.id
            WHERE COALESCE(s.tipo_test, '') LIKE 'Test rigature manuali%'
            GROUP BY s.id
            ORDER BY s.data DESC, COALESCE(s.ora, '') DESC, s.id DESC
            """
        )

        if df_rig_storico.empty:
            st.info("Non ci sono ancora test rigature manuali registrati.")
        else:
            st.markdown("#### Filtri")
            fr1, fr2, fr3 = st.columns(3)
            with fr1:
                luoghi = ["Tutti"] + sorted([str(v).strip() for v in df_rig_storico["luogo"].dropna().unique().tolist() if str(v).strip()])
                filtro_luogo_rig = st.selectbox("Luogo", luoghi, key="rig_test_history_place")
            with fr2:
                metodi = ["Tutti"] + sorted([str(v).replace("Test rigature manuali · ", "").strip() for v in df_rig_storico["tipo_test"].dropna().unique().tolist() if str(v).strip()])
                filtro_metodo_rig = st.selectbox("Metodo", metodi, key="rig_test_history_method")
            with fr3:
                filtro_periodo_rig = st.selectbox("Intervallo", ["Tutti", "Ultimi 15 giorni", "Ultimi 30 giorni", "Ultimi 90 giorni"], key="rig_test_history_period")

            df_rig_filtrato = df_rig_storico.copy()
            if filtro_luogo_rig != "Tutti":
                df_rig_filtrato = df_rig_filtrato[df_rig_filtrato["luogo"].astype(str).str.strip() == filtro_luogo_rig]
            if filtro_metodo_rig != "Tutti":
                df_rig_filtrato = df_rig_filtrato[df_rig_filtrato["tipo_test"].astype(str).str.contains(filtro_metodo_rig, regex=False)]
            if filtro_periodo_rig != "Tutti":
                giorni = {"Ultimi 15 giorni":15, "Ultimi 30 giorni":30, "Ultimi 90 giorni":90}[filtro_periodo_rig]
                dd = pd.to_datetime(df_rig_filtrato["data"], errors="coerce").dt.normalize()
                oggi = pd.Timestamp.today().normalize()
                df_rig_filtrato = df_rig_filtrato[(dd >= oggi-pd.Timedelta(days=giorni-1)) & (dd <= oggi)]

            st.write(f"Test visualizzati: **{len(df_rig_filtrato)}**")
            for _, test in df_rig_filtrato.iterrows():
                sid = int(test["id"])
                data_label = _formatta_data_storico(test.get("data")) if '_formatta_data_storico' in globals() else str(test.get("data") or "")
                luogo = str(test.get("luogo") or "—")
                metodo = str(test.get("tipo_test") or "Test rigature manuali").replace("Test rigature manuali · ", "")
                with st.expander(f"{data_label} · {luogo} · {metodo}"):
                    df_rows, df_comp = _carica_righe_test_rigature(sid)
                    max_cols = int(df_comp["colonna_numero"].max()) if not df_comp.empty else 0
                    c1,c2,c3,c4,c5 = st.columns(5)
                    with c1: st.metric("Metodo test", metodo)
                    with c2: st.metric("Combinazioni testate", len(df_rows))
                    with c3: st.metric("Rigature per sci", max_cols if max_cols else "—")
                    with c4: st.metric("T aria °C", _formatta_temperatura_1d(test.get("temperatura_aria")))
                    with c5: st.metric("T neve °C", _formatta_temperatura_1d(test.get("temperatura_neve")))

                    st.markdown("##### Sessione")
                    sc1,sc2,sc3=st.columns(3)
                    with sc1:
                        st.write(f"**Data:** {data_label}"); st.write(f"**Luogo:** {luogo}")
                    with sc2:
                        st.write(f"**Ora:** {str(test.get('ora') or '—')[:5]}"); st.write(f"**Meteo:** {str(test.get('meteo') or '—')}")
                    with sc3:
                        ur=test.get("umidita")
                        st.write(f"**UR:** {'—' if pd.isna(ur) else str(int(round(float(ur)))) + ' %'}")
                        st.write(f"**Modello sci:** {str(test.get('zero_modello_sci') or '—')}")

                    st.markdown("##### Tipologia neve")
                    classif=[("Origine",test.get("snow_origine")),("Consistenza",test.get("snow_consistenza")),("Fondo",test.get("snow_fondo")),("Umidità",test.get("snow_umidita")),("Forma grano",test.get("snow_forma_grano")),("Granulometria",test.get("snow_granulometria")),("Caratteristiche",test.get("snow_caratteristiche"))]
                    cc=st.columns(4)
                    for idx,(lab,val) in enumerate(classif):
                        with cc[idx%4]:
                            st.caption(lab.upper()); st.write(str(val or "—"))

                    if not df_rows.empty:
                        st.markdown("##### Podio test")
                        _render_podio_rigature(df_rows, df_comp)
                        st.markdown("##### Dettaglio test")
                        order_key=f"rig_test_history_order_{sid}"
                        if order_key not in st.session_state: st.session_state[order_key]="sci"
                        o1,o2,_=st.columns([1.35,1.15,4.5])
                        with o1:
                            if st.button("↕ Riordina per classifica",use_container_width=True,key=f"rig_hist_rank_{sid}"):
                                st.session_state[order_key]="classifica"; st.rerun()
                        with o2:
                            if st.button("↺ Ordine sci",use_container_width=True,key=f"rig_hist_ski_{sid}"):
                                st.session_state[order_key]="sci"; st.rerun()
                        df_vis=df_rows.copy()
                        if st.session_state[order_key]=="classifica":
                            df_vis["_sort"]=pd.to_numeric(df_vis["posizione"],errors="coerce")
                            df_vis=df_vis.sort_values("_sort",na_position="last",kind="stable").drop(columns=["_sort"]).reset_index(drop=True)
                        else:
                            df_vis["_sort"]=df_vis["numero_sci"].apply(_chiave_ordine_numero_sci)
                            df_vis=df_vis.sort_values("_sort",kind="stable").drop(columns=["_sort"]).reset_index(drop=True)
                        _render_tabella_rigature(df_vis, df_comp)

                    st.markdown(
                        """
                        <style>
                        div[class*="st-key-download_rig_test_"] button {height:48px!important;background:#eef1f4!important;border:1px solid #c8cfd6!important;border-radius:5px!important;font-weight:600!important;}
                        div[class*="st-key-edit_rig_history_"] button {height:48px!important;background:#00a7e1!important;border:1px solid #00a7e1!important;border-radius:5px!important;font-weight:600!important;}
                        div[class*="st-key-edit_rig_history_"] button p, div[class*="st-key-edit_rig_history_"] button svg {color:#fff!important;fill:#fff!important;}
                        div[class*="st-key-delete_rig_history_"] button {height:48px!important;background:#fff!important;border:1px solid #d9534f!important;border-radius:5px!important;font-weight:600!important;}
                        div[class*="st-key-delete_rig_history_"] button p, div[class*="st-key-delete_rig_history_"] button svg {color:#d9534f!important;fill:#d9534f!important;}
                        </style>
                        """, unsafe_allow_html=True
                    )

                    try:
                        pdf_rig=_crea_pdf_test_rigature(test,df_rows,df_comp); pdf_err=None
                    except Exception as exc:
                        pdf_rig=b""; pdf_err=str(exc)
                    st.markdown('<div style="height:0.45rem"></div>',unsafe_allow_html=True)
                    d1,d2,d3=st.columns(3)
                    with d1:
                        st.download_button("Scarica test",data=pdf_rig,file_name=_nome_file_pdf_test_rigature(test),mime="application/pdf",icon=":material/download:",use_container_width=True,disabled=bool(pdf_err),key=f"download_rig_test_{sid}")
                    with d2:
                        if st.button("Modifica test",icon=":material/edit:",use_container_width=True,key=f"edit_rig_history_{sid}"):
                            st.session_state["rig_test_edit_session_id"]=sid
                            st.session_state.pop("rig_test_edit_loaded_id",None)
                            for k in ["rig_test_table_data","rig_test_table_n","rig_test_table_cols"]: st.session_state.pop(k,None)
                            st.rerun()
                    with d3:
                        if st.button("Elimina test",icon=":material/delete:",use_container_width=True,key=f"delete_rig_history_{sid}"):
                            st.session_state[f"confirm_delete_rig_{sid}"]=True; st.rerun()
                    if pdf_err: st.caption(f"PDF non disponibile: {pdf_err}")
                    if st.session_state.get(f"confirm_delete_rig_{sid}",False):
                        st.warning("Confermi l'eliminazione definitiva di questo test rigature manuali?")
                        q1,q2=st.columns(2)
                        with q1:
                            if st.button("Conferma eliminazione",icon=":material/delete_forever:",use_container_width=True,key=f"confirm_rig_yes_{sid}"):
                                conn=apri_connessione_database()
                                try:
                                    ids=[int(x[0]) for x in conn.execute("SELECT id FROM test_rigature_aste WHERE sessione_id=?",(sid,)).fetchall()]
                                    for rid in ids: conn.execute("DELETE FROM test_rigature_componenti WHERE test_rigatura_asta_id=?",(rid,))
                                    conn.execute("DELETE FROM test_rigature_aste WHERE sessione_id=?",(sid,)); conn.execute("DELETE FROM sessioni WHERE id=?",(sid,)); conn.commit()
                                finally: conn.close()
                                _invalida_cache_dati(); st.session_state.pop(f"confirm_delete_rig_{sid}",None); st.session_state["rig_test_history_notice"]="Test rigature manuali eliminato correttamente."; st.rerun()
                        with q2:
                            if st.button("Annulla",icon=":material/close:",use_container_width=True,key=f"confirm_rig_no_{sid}"):
                                st.session_state.pop(f"confirm_delete_rig_{sid}",None); st.rerun()

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
            "Catalogo tecnico delle righe manuali con geometria, materiale e condizioni di utilizzo.",
            [
                "Lineare",
                "Lineare interrotta V",
                "Lineare interrotta X",
                "Screw left",
                "Screw right",
                "Double screw",
                "Special cut",
            ],
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
            "Ogni parametro descrive un aspetto indipendente. La consistenza riguarda solo lo strato superficiale; "
            "il fondo sottostante viene descritto separatamente, così le condizioni di transizione restano facili da catalogare."
        )

        gruppi_neve = _snow_option_groups_standard()
        headers = ["Origine", "Consistenza superficiale", "Fondo sottostante", "Umidità", "Forma grano", "Granulometria", "Caratteristiche"]
        valori_per_header = {
            "Origine": gruppi_neve["Origine"],
            "Consistenza superficiale": gruppi_neve["Consistenza"],
            "Fondo sottostante": gruppi_neve["Fondo sottostante"],
            "Umidità": gruppi_neve["Umidità neve"],
            "Forma grano": gruppi_neve["Forma grano"],
            "Granulometria": gruppi_neve["Granulometria"],
            "Caratteristiche": gruppi_neve["Caratteristiche"],
        }
        n_righe = max(len(v) for v in valori_per_header.values())
        html_rows = []
        for i in range(n_righe):
            celle = "".join(
                f"<td>{valori_per_header[col][i] if i < len(valori_per_header[col]) else ''}</td>"
                for col in headers
            )
            html_rows.append(f"<tr>{celle}</tr>")
        html_rows_render = "".join(html_rows)

        st.markdown(
            f"""
            <div class="snow-reference-card">
                <div class="snow-reference-header">
                    <div class="snow-reference-grid">
                        <div class="snow-reference-mini">
                            <div class="snow-reference-mini-title">Superficie e fondo separati</div>
                            <div class="snow-reference-mini-text">Una neve può essere soffice, sgranata o molle in superficie e avere contemporaneamente un fondo compatto o ghiacciato.</div>
                        </div>
                        <div class="snow-reference-mini">
                            <div class="snow-reference-mini-title">Condizioni di transizione</div>
                            <div class="snow-reference-mini-text">Esempio: neve nuova su pista battuta = Soffice o Sfarinata + Fondo compatto. Neve che molla sopra ghiaccio = Molle + Fondo ghiacciato.</div>
                        </div>
                        <div class="snow-reference-mini">
                            <div class="snow-reference-mini-title">Uso nel motore prodotti</div>
                            <div class="snow-reference-mini-text">Trova prodotto migliore valuta separatamente superficie e fondo, evitando categorie troppo specifiche e rendendo confrontabili più test.</div>
                        </div>
                    </div>
                </div>
                <div class="snow-reference-table-wrap">
                    <table class="snow-reference-table">
                        <thead><tr>{''.join(f'<th>{col}</th>' for col in headers)}</tr></thead>
                        <tbody>{html_rows_render}</tbody>
                    </table>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### Come leggere la classificazione")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("**Origine**")
            st.caption("Provenienza della neve: naturale, artificiale o mista.")
            st.markdown("**Consistenza superficiale**")
            st.caption("Come si presenta lo strato su cui scorre direttamente lo sci.")
        with c2:
            st.markdown("**Fondo sottostante**")
            st.caption("Strato portante sotto la superficie: non specificato/omogeneo, compatto o ghiacciato.")
            st.markdown("**Umidità**")
            st.caption("Presenza di acqua liquida nella neve.")
        with c3:
            st.markdown("**Forma grano**")
            st.caption("Stadio evolutivo: nuova, in trasformazione o trasformata.")
            st.markdown("**Granulometria**")
            st.caption("Dimensione prevalente dei grani.")
        with c4:
            st.markdown("**Caratteristiche**")
            st.caption("Proprietà aggiuntive come sporca, salata, ventata, lucida, cadente, vecchia, pioggia, variabile o aggressiva.")



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
