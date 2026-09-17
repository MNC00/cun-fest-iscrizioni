# Architettura

## Struttura progetto

```
app/
  main.py           rotte FastAPI (pagine + API)
  auth.py           hashing password, sessione cookie firmata (itsdangerous)
  database.py       engine SQLAlchemy, SessionLocal, get_db()
  models.py         modelli ORM (tabelle DB)
  schemas.py        Pydantic models per l'API di iscrizione
  calcolo.py        calcolo prezzo/pasti per partecipante
  pagamenti.py       sincronizzazione pagamento <-> prezzo
  email_service.py  invio email via SMTP Google + builder HTML
templates/          viste Jinja2 (Bootstrap)
static/             CSS/JS
sql/                script SQL da applicare manualmente su Supabase
```

Non è usato un ORM migration tool: le modifiche di schema sono script SQL in `sql/`, da eseguire a mano.

## Modelli (`app/models.py`)

- **Famiglia**: referente iscrizione (nome, cognome, email, telefono) — 1:N con `Partecipante`.
- **Partecipante**: dati soggiorno (date, pasti, fascia prezzo), stato iscrizione, prezzo calcolato.
- **Tariffa**: listino prezzi per fascia, con validità temporale.
- **Pagamento**: 1:1 con `Partecipante`, importo dovuto/pagato, stato pagamento.
- **Operatore**: utenti che accedono alla dashboard.
- **LogEvento**: audit log generico (`oggetto_tipo`, `oggetto_id`, `azione`, `operatore`, `dettagli` JSON) scritto ad ogni azione rilevante.

## Flussi principali

**Iscrizione** (`POST /iscriviti`)
Crea `Famiglia` + `Partecipante`(i) → `sincronizza_pagamento()` crea il `Pagamento` collegato (dovuto = 0 finché il prezzo non è calcolato).

**Calcolo prezzo** (`calcola_prezzo_partecipante`, in `calcolo.py`)
Da date arrivo/partenza + pasti dovuti + tariffa attiva della fascia → `prezzo_lordo`, sconto età, `prezzo_netto`. Applica il tetto di spesa della fascia. Scrive un `LogEvento` e fa il commit. Ogni chiamata è seguita da `sincronizza_pagamento()` per allineare l'importo dovuto.

**Report pasti** (`genera_report_pasti`, in `calcolo.py`)
Per ogni partecipante attivo, `calcola_pasti_per_giorno()` determina i pasti dovuti giorno per giorno (stessa logica del calcolo prezzo, a granularità giornaliera); i conteggi vengono aggregati sull'intero intervallo di date del festival.

**Email** (`app/email_service.py`)
Funzioni `costruisci_email_*` generano `{oggetto, html, testo}` per ogni caso (conferma, aggiornamento prezzo, annullamento singolo, annullamento nucleo, comunicazione di massa), fedeli nei contenuti al vecchio sistema Apps Script. `invia_email()` invia via SMTP (smtplib, SSL) usando le credenziali Google (`SMTP_USER`/`SMTP_PASSWORD`, App Password). Conferma e aggiornamento prezzo sono per singolo partecipante (non per nucleo). Errori di invio sollevano `EmailServiceError`, loggato ma senza bloccare l'operazione DB già commit-ata.

**Annullamento self-service** (`GET/POST /annulla/{token}`)
Ogni partecipante riceve un `token_annullamento` univoco alla creazione, usato in un link incluso nelle email di conferma/aggiornamento (nessun login richiesto). Da quella pagina può annullare solo la propria iscrizione (indicando un nuovo referente per il nucleo, se restano altri iscritti) oppure annullare in un'unica soluzione tutto il nucleo familiare (un'unica email di recap con l'elenco di chi è stato annullato).

**Autenticazione operatori** (`app/auth.py`)
Password hashate con bcrypt. Sessione: token firmato (`itsdangerous`, scadenza 8h) salvato in cookie httponly. `get_current_operatore_username(request)` legge il cookie in ogni rotta protetta; se assente/non valido → redirect a `/login`.

## Convenzioni

- Tutte le rotte operatore verificano il login manualmente a inizio funzione (nessun middleware/dependency dedicato ad oggi).
- I template protetti includono `_nav.html` (menu operatore); le pagine pubbliche includono `_nav_pubblica.html`.
- Le azioni con effetti (pagamento, annullamento, email di massa, modifica iscrizione) scrivono sempre un `LogEvento` nella stessa transazione.
