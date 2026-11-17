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

    # Normalizza i vecchi riferimenti dello schema Skating alla nuova nomenclatura.
    # Nel nuovo schema esiste un solo punto "Inizio canalina" e il riferimento
    # intermedio è correttamente denominato "Inizio attacco".
    for _colonna_zona in ("zona_da", "zona_a"):
        conn.execute(
            f"UPDATE test_rigature_componenti SET {_colonna_zona} = 'Inizio canalina' "
            f"WHERE TRIM(COALESCE({_colonna_zona}, '')) IN "
            f"('Inizio canalina (lato coda)', 'Inizio canalina (lato punta)')"
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
    return [
        "Coda",
        "Fine attacco",
        "Inizio attacco",
        "Inizio canalina",
        "Punta",
    ]


# Asset incorporati direttamente nel sorgente: l'hover del podio non dipende
# da file statici esterni durante il deploy Streamlit.
_SCHEMA_ZONE_SKATING_DATA_URL = "data:image/png;base64,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"
_SCHEMA_ZONE_CLASSICO_DATA_URL = "data:image/png;base64,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"
_HAND_DRIVE_WHEEL_DATA_URL = "data:image/png;base64,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"


_DIRECTION_LAMBDA_DATA_URL = 'data:image/png;base64,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'
_DIRECTION_V_DATA_URL = 'data:image/png;base64,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'
_DIRECTION_LAMBDAV_DATA_URL = 'data:image/png;base64,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'


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


def _direzione_rigatura_src(direzione):
    """Restituisce la direzione incorporata nel sorgente, così funziona anche su Streamlit Cloud."""
    valore = _testo_pulito(direzione).strip().replace(" ", "")
    # Accetta sia il simbolo lambda maiuscolo sia eventuali varianti salvate in precedenza.
    valore = valore.replace("∧", "Λ").replace("λ", "Λ")
    if valore == "Λ":
        return _DIRECTION_LAMBDA_DATA_URL
    if valore == "V":
        return _DIRECTION_V_DATA_URL
    if valore in {"ΛV", "VΛ"}:
        return _DIRECTION_LAMBDAV_DATA_URL
    return ""


def _normalizza_zona_rigatura(zona):
    """Compatibilità con i vecchi nomi usati nello schema Skating."""
    valore = str(zona or "").strip()
    if valore in {"Inizio canalina (lato coda)", "Inizio canalina (lato punta)"}:
        return "Inizio canalina"
    return valore


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
            "Inizio attacco": 52.9,
            "Inizio canalina": 81.3,
            "Punta": 91.6,
        }
    da = _normalizza_zona_rigatura(zona_da)
    a = _normalizza_zona_rigatura(zona_a)
    if da not in punti or a not in punti:
        return None
    x1, x2 = punti[da], punti[a]
    left = min(x1, x2)
    width = max(1.2, abs(x2 - x1))
    return left, width


def _zona_rigatura_testo(zona_da, zona_a):
    da = _normalizza_zona_rigatura(zona_da)
    a = _normalizza_zona_rigatura(zona_a)
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

    test_a_coppie = metodo_test in ["Parallel", "Fotocellula"]
    if test_a_coppie:
        st.caption(
            "Imposta il numero di coppie testate e quante rigature compongono ciascuna coppia. "
            "La logica è identica al test Asta; nel campo Numero sci inserisci solo il numero della coppia "
            "(es. 10 per la coppia 10A/10B)."
        )
    else:
        st.caption(
            "Imposta il numero di aste e quante rigature compongono ciascuno sci. Per ogni rigatura "
            "selezioni nome, direzione, Hand drive e zona dello sci su cui è stata applicata."
        )

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
        numero_aste = st.number_input(
            "Numero di coppie" if test_a_coppie else "Numero di aste",
            min_value=1,
            max_value=30,
            value=10,
            step=1,
            format="%d",
            key="rig_test_num_rods",
            help=(
                "Numero di coppie di sci confrontate nel test. Ogni riga rappresenta una coppia completa, ad esempio 10 = 10A/10B."
                if test_a_coppie
                else "Numero di aste/sci singoli registrati nel test."
            ),
        )
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
                "zona_da": _normalizza_zona_rigatura(c.get("zona_da")) or "—",
                "zona_a": _normalizza_zona_rigatura(c.get("zona_a")) or "—",
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

    # Parallel e Fotocellula lavorano sulla coppia completa: Numero sci è quindi il numero
    # della coppia (es. 10 = 10A/10B), non il codice della singola asta.
    def _numero_coppia_rigature(valore):
        if valore is None or (isinstance(valore, float) and pd.isna(valore)):
            return None
        testo = str(valore).strip()
        if not testo or testo.lower() in {"nan", "none", "—"}:
            return None
        match = re.search(r"\d+", testo)
        return int(match.group(0)) if match else None

    def _numero_asta_rigature(valore):
        if valore is None or (isinstance(valore, float) and pd.isna(valore)):
            return ""
        testo = str(valore).strip()
        if not testo or testo.lower() in {"nan", "none", "—"}:
            return ""
        # Evita che numeri passati da una NumberColumn diventino 10.0 quando si torna ad Asta.
        try:
            numero = float(testo)
            if numero.is_integer():
                return str(int(numero))
        except Exception:
            pass
        return testo

    if "Numero sci" in df_tab.columns:
        if test_a_coppie:
            df_tab["Numero sci"] = df_tab["Numero sci"].apply(_numero_coppia_rigature)
        else:
            df_tab["Numero sci"] = df_tab["Numero sci"].apply(_numero_asta_rigature)

    st.session_state[state_key] = df_tab.copy()

    config = {
        "_ordine_inserimento": None,
        "Posizione": st.column_config.NumberColumn("Posizione", min_value=1, max_value=n_aste, step=1, format="%d", width="small"),
        "Numero sci": (
            st.column_config.NumberColumn(
                "Numero sci",
                min_value=1,
                step=1,
                format="%d",
                width="small",
                help="Numero della coppia completa: es. 10 indica 10A/10B.",
            )
            if test_a_coppie
            else st.column_config.TextColumn(
                "Numero sci",
                width="small",
                help="Codice della singola asta/sci, ad esempio 10A o 10B.",
            )
        ),
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
        numero_sci_raw = r.get("Numero sci")
        if test_a_coppie:
            numero_coppia = _numero_coppia_rigature(numero_sci_raw)
            numero_sci = "" if numero_coppia is None else str(numero_coppia)
        else:
            numero_sci = _numero_asta_rigature(numero_sci_raw)
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
        .rig-tooltip-divider { display:none; }
        .rig-tooltip-tech-row { display:flex; align-items:center; justify-content:center; gap:2.4rem; width:100%; min-height:106px; margin-top:.34rem; padding:.12rem .35rem .18rem; box-sizing:border-box; }
        .rig-tooltip-direction-row { display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto; min-width:108px; min-height:96px; margin:0; padding:0; box-sizing:border-box; }
        .rig-tooltip-direction-img { display:block !important; width:auto !important; max-width:142px !important; height:96px !important; object-fit:contain !important; border:0 !important; background:#fff !important; box-shadow:none !important; opacity:1 !important; visibility:visible !important; }
        .rig-tooltip-handdrive-row { display:inline-flex; align-items:center; justify-content:center; gap:.62rem; flex:0 0 auto; min-height:72px; margin:0; padding:0; box-sizing:border-box; }
        .rig-tooltip-wheel { width:66px; height:66px; flex:0 0 66px; object-fit:contain; display:block; border:0; border-radius:0; background:transparent; box-shadow:none; }
        .rig-tooltip-handdrive-text { color:#1f2a33; font-size:.86rem; line-height:1.15; font-weight:600; letter-spacing:0; white-space:nowrap; }
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

        direction_html = ""
        direction_src = _direzione_rigatura_src(direzione)
        if direction_src:
            direction_html = (
                f'<div class="rig-tooltip-direction-row">'
                f'<img class="rig-tooltip-direction-img" src="{direction_src}" alt="Direzione {html_escape(direzione)}">'
                f'</div>'
            )

        handdrive_html = ""
        if hd:
            wheel_src = _HAND_DRIVE_WHEEL_DATA_URL
            wheel_html = (
                f'<img class="rig-tooltip-wheel" src="{wheel_src}" alt="Rotella Hand drive">'
                if wheel_src else ""
            )
            handdrive_html = (
                f'<div class="rig-tooltip-handdrive-row">{wheel_html}'
                f'<div class="rig-tooltip-handdrive-text">Hand drive</div></div>'
            )

        tech_html = ""
        if direction_html or handdrive_html:
            tech_html = f'<div class="rig-tooltip-tech-row">{handdrive_html}{direction_html}</div>'

        tooltip_html = (
            f'<div class="rig-work-tooltip">'
            f'<div class="rig-tooltip-title">{html_escape(label)}</div>'
            f'{ski_html}'
            f'{tech_html}'
            f'</div>'
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
