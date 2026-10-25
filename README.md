# Ski Material Lab

Prima versione Streamlit per catalogare:

- sessioni e condizioni neve
- catalogo sci
- zero test a fotocellule
- selezione automatica delle coppie di sci con tempi medi simili
- test di scorrimento e rigature
- modalità Aste, Parallel e Fotocellule
- test scioline di tenuta a sensazione
- storico
- backup JSON

## Avvio locale

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Database

Per default usa SQLite locale (`ski_material_lab.db`).

Se vengono configurati entrambi i secrets:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`

l'app usa Turso, seguendo la stessa logica di Sector G2 Lab.
