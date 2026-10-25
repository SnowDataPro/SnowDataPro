# SnowDataPro

Applicazione Streamlit per catalogare e analizzare test sui materiali nello sci di fondo.

## Menu principale

### Test
- Zero test
- Test prodotti scorrimento
- Test scioline di tenuta
- Test rigature manuali

### Prodotti
- Prodotti di scorrimento
- Scioline di tenuta
- Rigature manuali

Le pagine Prodotti permettono di archiviare nome/codice, marca, tipo,
condizioni di utilizzo, descrizione e note.

## Database
Usa SQLite in locale oppure Turso online tramite:
- TURSO_DATABASE_URL
- TURSO_AUTH_TOKEN

Per Streamlit Community Cloud usare Python 3.12.

## Privacy
La protezione dell'app è gestita direttamente da Streamlit Community Cloud
tramite **Sharing → Only specific people can view this app**.

Non è richiesta alcuna password interna all'app e non è necessario configurare
`APP_PASSWORD`.
