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
  email_service.py  invio email via Gmail API (OAuth2) + builder HTML
  storage_service.py upload/download ricevute di pagamento via Supabase Storage
  drive_service.py  copia ricevute su Google Drive via OAuth2
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
- **ImpostazioneApp**: valori applicativi configurabili dagli amministratori, inclusa la cartella Google Drive delle ricevute.
- **RicevutaPagamento** / **RicevutaPartecipante**: ricevute di bonifico caricate dalle famiglie (file su Supabase Storage, metadati su Postgres); relazione N:N con `Partecipante` perché una ricevuta può coprire uno, alcuni o tutti i partecipanti dello stesso nucleo. Verifica manuale dell'operatore (`verificata`/`verificata_da`/`verificata_il`), mai automatica.
- **LogEvento**: audit log generico (`oggetto_tipo`, `oggetto_id`, `azione`, `operatore`, `dettagli` JSON) scritto ad ogni azione rilevante.

## Flussi principali

**Iscrizione** (`POST /iscriviti`)
Crea `Famiglia` + `Partecipante`(i), poi calcola i prezzi applicabili e riallinea i pagamenti. Un errore tariffario per un partecipante non annulla l'iscrizione del nucleo; viene comunicato nel riepilogo. Invia una sola email per invio, con tutti i partecipanti e i rispettivi importi disponibili.

**Calcolo prezzo** (`calcola_prezzo_partecipante`, in `calcolo.py`)
Da date arrivo/partenza + pasti dovuti + tariffa attiva della fascia → `prezzo_lordo`, sconto età, `prezzo_netto`. Applica il tetto di spesa della fascia. Scrive un `LogEvento` e fa il commit. Ogni chiamata è seguita da `sincronizza_pagamento()` per allineare l'importo dovuto.

**Report pasti** (`genera_report_pasti`, in `calcolo.py`)
Per ogni partecipante attivo, `calcola_pasti_per_giorno()` determina i pasti dovuti giorno per giorno (stessa logica del calcolo prezzo, a granularità giornaliera); i conteggi vengono aggregati sull'intero intervallo di date del festival.

**Email** (`app/email_service.py`)
Funzioni `costruisci_email_*` generano `{oggetto, html, testo}` per i vari casi, fedeli nei contenuti al vecchio sistema Apps Script. La conferma d'iscrizione è aggregata per invio; gli aggiornamenti prezzo restano per singolo partecipante. `invia_email()` usa la Gmail API con OAuth. Il consenso richiesto include `gmail.send` e `drive.file`; il refresh token si ottiene con `scripts/gmail_oauth_setup.py`. Errori email vengono loggati senza bloccare l'operazione DB già commit-ata.

**Annullamento self-service** (`GET/POST /annulla/{token}`)
Ogni partecipante riceve un `token_annullamento` univoco alla creazione, usato in un link incluso nelle email di conferma/aggiornamento (nessun login richiesto). Da quella pagina può annullare solo la propria iscrizione (indicando un nuovo referente per il nucleo, se restano altri iscritti) oppure annullare in un'unica soluzione tutto il nucleo familiare (un'unica email di recap con l'elenco di chi è stato annullato).

**Ricevute di pagamento** (`GET/POST /ricevute/{token}`, `app/storage_service.py`)
Ogni `Famiglia` ha un `token_ricevute` univoco usato nel link pubblico alle conferme email. La famiglia carica file PDF/JPG/PNG (max 8MB), associandoli ai partecipanti coperti. La copia canonica resta nel bucket privato Supabase; `app/drive_service.py` ne carica una copia nella cartella scelta in Configurazione dagli amministratori (con `GOOGLE_DRIVE_FOLDER_ID` come fallback). La cartella viene creata con `scripts/gdrive_folder_setup.py` e condivisa manualmente da Drive; l'app non abilita accesso pubblico. ID e stato della copia sono registrati su `RicevutaPagamento`. In caso di errore, l'originale resta disponibile su Supabase e gli operatori possono riprovare da `/pagamenti`. Note, stato e verifica manuale sono visibili agli operatori; il download continua a passare dal backend.

**Interfaccia responsive**
Tutti i template pubblici e operatore usano Bootstrap e gli stili condivisi in `static/css/style.css`. Le tabelle dense sono contenute in wrapper `table-responsive`; le navigazioni si riadattano agli schermi stretti senza richiedere nuovi framework.

**Autenticazione operatori** (`app/auth.py`)
Password hashate con bcrypt. Sessione: token firmato (`itsdangerous`, scadenza 8h) salvato in cookie httponly. `get_current_operatore_username(request)` legge il cookie in ogni rotta protetta; se assente/non valido → redirect a `/login`.

## Convenzioni

- Tutte le rotte operatore verificano il login manualmente a inizio funzione (nessun middleware/dependency dedicato ad oggi).
- I template protetti includono `_nav.html` (menu operatore); le pagine pubbliche includono `_nav_pubblica.html`.
- Le azioni con effetti (pagamento, annullamento, email di massa, modifica iscrizione) scrivono sempre un `LogEvento` nella stessa transazione.
