# CUN Fest Iscrizioni

App FastAPI per la gestione delle iscrizioni al CUN Fest: form pubblico di iscrizione, calcolo prezzi, pagamenti, comunicazioni email e dashboard per gli operatori.

## Stack

Python 3, FastAPI, SQLAlchemy, PostgreSQL (Supabase) + Supabase Storage (ricevute di pagamento), Jinja2 + Bootstrap, Gmail API via OAuth2 (email transazionali).

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
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` | Credenziali OAuth create su Google Cloud Console (vedi `scripts/gmail_oauth_setup.py`) |
| `GMAIL_REFRESH_TOKEN` | Ottenuto eseguendo `scripts/gmail_oauth_setup.py` con gli scope Gmail e Drive |
| `GMAIL_SENDER_EMAIL` | Mittente, es. `CUN Fest <iscrizionicunfest@gmail.com>` |
| `BASE_URL` | URL base dell'app (usato nei link email) |
| `SUPABASE_URL` | URL del progetto Supabase (Project Settings → API), per le ricevute di pagamento |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key del progetto Supabase (segreta: bypassa le RLS, va usata solo dal backend) |
| `SUPABASE_STORAGE_BUCKET` | Nome del bucket di Storage per le ricevute (default `ricevute-pagamento`, va creato come bucket **privato** su Supabase) |
| `GOOGLE_DRIVE_FOLDER_ID` | ID cartella Drive usato come fallback se non è stata scelta dalla configurazione amministrativa |

## Database

Lo schema è definito in `sql/schema.sql` (idempotente, unica fonte di verità
per una installazione nuova). Migrazioni incrementali successive sono in
`sql/*.sql` con nome descrittivo, da eseguire nel SQL Editor di Supabase.

Per il reset annuale (nuova edizione del festival) vedi
[NUOVA_EDIZIONE.md](NUOVA_EDIZIONE.md).

## Storage (ricevute di pagamento)

Render (piano free) ha un filesystem effimero: i file caricati non
sopravvivono a un riavvio/deploy. Le ricevute vengono quindi salvate su
**Supabase Storage** (incluso nello stesso progetto/piano gratuito del DB):

1. Supabase → Storage → New bucket → nome uguale a `SUPABASE_STORAGE_BUCKET`
   (default `ricevute-pagamento`) → **Public bucket = NO** (privato: l'accesso
   passa sempre dal backend con la service role key, mai direttamente dal
   browser).
2. Recupera `SUPABASE_URL` e la **service role key** (Project Settings → API,
   non la `anon` key) e impostale nelle variabili d'ambiente.

Su un'installazione esistente, esegui anche `sql/alter_ricevute_pagamento.sql`.

### Copia condivisibile su Google Drive

1. Esegui nuovamente `python scripts/gmail_oauth_setup.py` e autorizza l'account Google. Il consenso include `gmail.send` e `drive.file`; aggiorna `GMAIL_REFRESH_TOKEN` negli ambienti di esecuzione con il nuovo token.
2. Esegui `python scripts/gdrive_folder_setup.py` con le credenziali aggiornate per creare la cartella e ottenere ID/link.
3. In **Configurazione → Google Drive**, un amministratore può incollare l'ID o il link della cartella. In alternativa, imposta `GOOGLE_DRIVE_FOLDER_ID` come fallback.
4. Condividi la cartella da Google Drive con le persone o gli account esterni desiderati. L'app non rende pubblici i file né genera link anonimi.
5. Su database esistenti, esegui `sql/alter_ricevute_google_drive.sql` e `sql/create_impostazioni_app.sql` prima di distribuire la versione aggiornata.

Supabase resta lo storage privato usato dall'app. Se la copia Drive fallisce, il caricamento originale resta disponibile e l'operatore può riprovare da `/pagamenti`.

## Funzionalità principali

- **Iscrizione pubblica** (`/iscriviti`): form famiglia + partecipanti, salva `Famiglia`/`Partecipante`.
- **Login operatori** (`/login`): sessione via cookie firmato.
- **Dashboard** (`/dashboard`): elenco famiglie/partecipanti, azioni rapide (modifica, ricalcolo prezzo, annullamento).
- **Modifica iscrizione** (`/modifica-iscrizione/{id}`): aggiorna dati partecipante e ricalcola il prezzo.
- **Pagamenti** (`/pagamenti`): stato pagamento per partecipante, segna come pagato.
- **Comunicazioni di massa** (`/comunicazioni`): invio email filtrato per fascia/stato/zona.
- **Report pasti** (`/report-pasti`): conteggio giornaliero colazioni/pranzi/cene, export CSV.
- **Ricevute di pagamento** (`/ricevute/{token}`, pubblica): le famiglie caricano le ricevute dei bonifici (uno o più file per un unico bonifico dell'intero nucleo, oppure ricevute separate per bonifici parziali); il link è incluso nelle email di conferma/aggiornamento prezzo. I file sono salvati su Supabase Storage privato e copiati nella cartella Drive configurata. Gli operatori vedono note, stato copia e verifica da `/pagamenti`; la verifica dell'importo resta manuale.
- **Configurazione** (`/configurazione`, solo operatori amministratori — flag `Operatore.is_admin`): gestione di date evento, tariffe e account operatore da interfaccia web.

Ogni azione rilevante viene tracciata in `log_eventi`.

## Script di supporto

- `scripts/crea_operatore.py` — crea/aggiorna un account operatore (password, nome, stato attivo).
- `scripts/gmail_oauth_setup.py` — da eseguire una tantum in locale per ottenere `GMAIL_REFRESH_TOKEN` (vedi commenti nello script per il setup su Google Cloud Console).
- `scripts/gdrive_folder_setup.py` — crea la cartella Drive da usare per le ricevute e stampa l'ID da configurare.

Per i dettagli tecnici (modelli, moduli, flussi) vedi [ARCHITECTURE.md](ARCHITECTURE.md).
