# CUN Fest Iscrizioni

App FastAPI per la gestione delle iscrizioni al CUN Fest: form pubblico di iscrizione, calcolo prezzi, pagamenti, comunicazioni email e dashboard per gli operatori.

## Stack

Python 3, FastAPI, SQLAlchemy, PostgreSQL (Supabase), Jinja2 + Bootstrap, Brevo (email transazionali).

## Setup locale

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # compila le variabili (vedi sotto)
uvicorn app.main:app --reload
```

App su `http://127.0.0.1:8000`.

## Variabili d'ambiente (`.env`)

| Variabile | Descrizione |
|---|---|
| `DATABASE_URL` | Connection string PostgreSQL (Supabase) |
| `SECRET_KEY` | Chiave per firmare i cookie di sessione operatore |
| `BREVO_API_KEY` | API key Brevo per l'invio email |
| `BREVO_SENDER_EMAIL` | Mittente delle email transazionali |
| `BASE_URL` | URL base dell'app (usato nei link email) |

## Database

Gli schemi sono gestiti a mano tramite script in `sql/`. Dopo aver clonato o aggiornato il progetto, esegui gli script mancanti nel SQL Editor di Supabase (es. `sql/create_pagamenti.sql`).

## Funzionalità principali

- **Iscrizione pubblica** (`/iscriviti`): form famiglia + partecipanti, salva `Famiglia`/`Partecipante`.
- **Login operatori** (`/login`): sessione via cookie firmato.
- **Dashboard** (`/dashboard`): elenco famiglie/partecipanti, azioni rapide (modifica, ricalcolo prezzo, annullamento).
- **Modifica iscrizione** (`/modifica-iscrizione/{id}`): aggiorna dati partecipante e ricalcola il prezzo.
- **Pagamenti** (`/pagamenti`): stato pagamento per partecipante, segna come pagato.
- **Comunicazioni di massa** (`/comunicazioni`): invio email filtrato per fascia/stato/zona.
- **Report pasti** (`/report-pasti`): conteggio giornaliero colazioni/pranzi/cene, export CSV.

Ogni azione rilevante viene tracciata in `log_eventi`.

Per i dettagli tecnici (modelli, moduli, flussi) vedi [ARCHITECTURE.md](ARCHITECTURE.md).
