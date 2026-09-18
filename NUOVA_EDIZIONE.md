# Procedura: nuova edizione / reset annuale

Guida operativa per azzerare il gestionale e prepararlo per una nuova
edizione del festival. Da seguire quando l'edizione corrente è chiusa
(pagamenti saldati, comunicazioni finali inviate).

## 0. Backup (consigliato)

Prima di cancellare qualsiasi dato, esporta un backup dal pannello Supabase
(Database → Backups) o con `pg_dump`, utile per storico/contabilità.

## 1. Reset dei dati

Nel SQL Editor di Supabase esegui, in ordine:

1. `sql/reset_dati.sql` — svuota iscrizioni, partecipanti, pagamenti, log
   eventi e tariffe (mantiene gli account operatore).
2. Se serve ripartire anche da capo con gli account operatore, decommenta
   la riga finale dello stesso script prima di eseguirlo.

Se invece stai facendo una **installazione nuova** (nuovo progetto Supabase,
mai avviato prima), esegui `sql/schema.sql` per creare tutte le tabelle da
zero (è idempotente, può essere rieseguito senza rischi).

## 2. Configura le tariffe e i periodi della nuova edizione

**Novità: sezione "Configurazione" per operatori amministratori.** Da
`/configurazione` (visibile in menu solo agli operatori con ruolo
amministratore) puoi ora gestire date evento, tariffe e account operatore
direttamente da interfaccia web, senza toccare SQL a mano. Le istruzioni SQL
qui sotto restano valide come alternativa/fallback (es. per bulk-insert
iniziali più comodi da script) ma per la gestione ordinaria conviene usare la
UI.

Quando i prezzi ufficiali sono noti, inseriscili in `tariffe` (dalla UI in
`/configurazione?sezione=tariffe`, oppure adattando `sql/seed_tariffe_esempio.sql`):
una riga base per ciascun tipo di evento (`precun`, `campo_famiglie`,
`cun_fest`, `pranzo_cun`, con fascia "Base (tutte le fasce)" = `NULL`) più,
solo se serve un prezzo diverso, righe di override con fascia `Nord` o `Altro`.

**Sconto giovani — aggiorna `ANNO_RIFERIMENTO`:** in `app/calcolo.py` la
costante `ANNO_RIFERIMENTO` (in cima al file) definisce l'anno rispetto al
quale si calcola l'età di un partecipante (`ANNO_RIFERIMENTO - anno di nascita
<= 30` → si applica `sconto_giovani_percentuale` della tariffa). Va aggiornata
a mano ad ogni edizione con l'anno del festival, altrimenti lo sconto verrà
calcolato con l'età sbagliata. Questa è l'unica impostazione pivotale rimasta
nel codice (non in UI), perché richiede una modifica di file e deploy.

**Date dell'evento — tabella `periodi_evento`:** ogni riga (`precun`,
`campo_famiglie`, `cun_fest`, `pranzo_cun`) ha una propria `data_inizio`/
`data_fine`, indipendente dalle tariffe. L'app rifiuta lato server le
iscrizioni con data di arrivo/partenza fuori dall'unione dei periodi degli
eventi selezionati dal partecipante (es. chi fa PreCunFest+CunFest deve stare
nell'unione dei due periodi). Per "Solo pranzo CUN" la data non viene chiesta
all'utente: viene impostata automaticamente da `periodi_evento.pranzo_cun`
(deve avere `data_inizio` valorizzata, `data_fine` opzionale se il pranzo dura
un solo giorno). Aggiorna le date da `/configurazione?sezione=periodi`, oppure via SQL:

```sql
UPDATE periodi_evento SET data_inizio = '2027-08-01', data_fine = '2027-08-03' WHERE tipo_evento = 'precun';
UPDATE periodi_evento SET data_inizio = '2027-08-03', data_fine = '2027-08-10' WHERE tipo_evento = 'cun_fest';
-- ecc. (vedi sql/seed_tariffe_esempio.sql per tutti gli esempi)
```

Finché una riga di `periodi_evento` ha le date a `NULL`, l'app non applica
alcun vincolo sulle date per quell'evento (utile se apri le iscrizioni prima
di aver deciso le date definitive) — eccetto per `pranzo_cun`, per cui la
data è obbligatoria (senza di essa il calcolo del prezzo fallisce con errore
esplicito).

Se i prezzi non sono ancora noti al momento dell'apertura iscrizioni, non è
un problema: l'app supporta iscrizioni con `tariffe` vuota (i prezzi restano
`None` finché un operatore non lancia il ricalcolo da `/dashboard`, che invia
automaticamente l'email di aggiornamento prezzo a tutti gli interessati).

## 3. Account operatori

- Se gli account restano invariati, non serve fare nulla.
- **Novità: ruolo amministratore.** Un operatore con `is_admin = TRUE` vede
  in menu la voce "Configurazione" (date evento, tariffe, gestione altri
  operatori); un operatore normale no. Una volta che esiste almeno un
  amministratore, la gestione ordinaria di operatori/tariffe/date può
  avvenire tutta da `/configurazione`, senza più bisogno di questo script o
  di SQL manuale.
- **Bootstrap del primo amministratore** (necessario su un'installazione
  nuova, o dopo aver eseguito `sql/alter_operatore_admin.sql` su un DB
  esistente, perché nessun operatore parte come admin automaticamente):

  ```bash
  python scripts/crea_operatore.py --username tuo_username --password "..." --admin
  ```

  (oppure `UPDATE operatori SET is_admin = TRUE WHERE username = '...';` via SQL)

- Per aggiungere un nuovo operatore o resettare una password da riga di
  comando (alternativa alla UI):

  ```bash
  python scripts/crea_operatore.py
  ```

  (accetta anche `--username`, `--password`, `--nome`, `--admin` per uso non
  interattivo; **attenzione**: `--disattiva` e `--admin` vanno ripassati ad
  ogni esecuzione sullo stesso operatore, altrimenti vengono azzerati)

- Per disattivare un operatore che non fa più parte dello staff, ri-esegui lo
  script con `--disattiva` sullo stesso username (oppure usa il pulsante
  "Attivo" in `/configurazione?sezione=operatori`).

## 4. Variabili d'ambiente

Verifica/aggiorna in `.env` (locale) e nelle Environment Variables di Render
(produzione):

- `BASE_URL` — se cambia il dominio dell'edizione.
- `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` / `GMAIL_SENDER_EMAIL` — se cambia il mittente ufficiale (rigenerare il refresh token con `scripts/gmail_oauth_setup.py` per il nuovo account).
- `DATABASE_URL` / `SECRET_KEY` — di norma invariati tra edizioni.

## 5. Verifica finale

- Apri `/iscriviti` e invia un'iscrizione di prova.
- Fai login su `/login` e controlla `/dashboard`, `/pagamenti`,
  `/report-pasti`.
- Se le tariffe sono già note, verifica che il prezzo calcolato sia corretto.
- Cancella eventuali iscrizioni di prova con "Annulla iscrizione" o via SQL.

A questo punto il sistema è pronto per la nuova edizione.
