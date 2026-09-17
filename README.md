# CUN Fest Iscrizioni

App FastAPI per la gestione delle iscrizioni al CUN Fest: form pubblico di iscrizione, calcolo prezzi, pagamenti, comunicazioni email e dashboard per gli operatori.

## Stack

Python 3, FastAPI, SQLAlchemy, PostgreSQL (Supabase), Jinja2 + Bootstrap, SMTP Google (email transazionali).

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
| `SMTP_USER` | Indirizzo Gmail mittente, usato anche per il login SMTP |
| `SMTP_PASSWORD` | Password per le app di Google (vedi https://myaccount.google.com/apppasswords) |
| `SMTP_SENDER_EMAIL` | Facoltativa: mittente mostrato, se diverso da `SMTP_USER` |
| `BASE_URL` | URL base dell'app (usato nei link email) |

## Database

Lo schema è definito in `sql/schema.sql` (idempotente, unica fonte di verità
per una installazione nuova). Migrazioni incrementali successive sono in
`sql/*.sql` con nome descrittivo, da eseguire nel SQL Editor di Supabase.

Per il reset annuale (nuova edizione del festival) vedi
[NUOVA_EDIZIONE.md](NUOVA_EDIZIONE.md).

## Funzionalità principali

- **Iscrizione pubblica** (`/iscriviti`): form famiglia + partecipanti, salva `Famiglia`/`Partecipante`.
- **Login operatori** (`/login`): sessione via cookie firmato.
- **Dashboard** (`/dashboard`): elenco famiglie/partecipanti, azioni rapide (modifica, ricalcolo prezzo, annullamento).
- **Modifica iscrizione** (`/modifica-iscrizione/{id}`): aggiorna dati partecipante e ricalcola il prezzo.
- **Pagamenti** (`/pagamenti`): stato pagamento per partecipante, segna come pagato.
- **Comunicazioni di massa** (`/comunicazioni`): invio email filtrato per fascia/stato/zona.
- **Report pasti** (`/report-pasti`): conteggio giornaliero colazioni/pranzi/cene, export CSV.

Ogni azione rilevante viene tracciata in `log_eventi`.

## Script di supporto

- `scripts/crea_operatore.py` — crea/aggiorna un account operatore (password, nome, stato attivo).

Per i dettagli tecnici (modelli, moduli, flussi) vedi [ARCHITECTURE.md](ARCHITECTURE.md).
