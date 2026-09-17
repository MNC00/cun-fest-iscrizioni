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

## 2. Configura le tariffe della nuova edizione

Quando i prezzi ufficiali sono noti, inseriscili in `tariffe` adattando
`sql/seed_tariffe_esempio.sql` (fasce Generale/Uninord/Unisud, prezzi
notte/pasti, tetto di spesa, sconto giovani, date di validità).

**Sconto giovani — aggiorna `ANNO_RIFERIMENTO`:** in `app/calcolo.py` la
costante `ANNO_RIFERIMENTO` (in cima al file) definisce l'anno rispetto al
quale si calcola l'età di un partecipante (`ANNO_RIFERIMENTO - anno di nascita
<= 30` → si applica `sconto_giovani_percentuale` della tariffa). Va aggiornata
a mano ad ogni edizione con l'anno del festival, altrimenti lo sconto verrà
calcolato con l'età sbagliata.

**Importante:** le colonne `valido_dal`/`valido_al` di `tariffe` non sono solo
informative: l'app le usa anche per calcolare il periodo valido dell'evento
(minimo di `valido_dal` e massimo di `valido_al` tra le tariffe attive) e
rifiuta lato server le iscrizioni con data di arrivo/partenza fuori da
quell'intervallo. È lo stesso periodo per tutti e tre i pacchetti
(PreCunFest+CunFest, Campo Famiglie+CunFest, solo CunFest): assicurati che
`valido_dal`/`valido_al` coprano l'intero arco dell'edizione (dal primo giorno
del PreCunFest/Campo Famiglie all'ultimo giorno del CunFest).

Se i prezzi non sono ancora noti al momento dell'apertura iscrizioni, non è
un problema: l'app supporta iscrizioni con `tariffe` vuota (i prezzi restano
`None` finché un operatore non lancia il ricalcolo da `/dashboard`, che invia
automaticamente l'email di aggiornamento prezzo a tutti gli interessati); in
tal caso però non viene applicato nessun vincolo sulle date, finché almeno una
tariffa attiva non ha `valido_dal`/`valido_al` valorizzati.

## 3. Account operatori

- Se gli account restano invariati, non serve fare nulla.
- Per aggiungere un nuovo operatore o resettare una password:

  ```bash
  python scripts/crea_operatore.py
  ```

  (accetta anche `--username`, `--password`, `--nome` per uso non interattivo)

- Per disattivare un operatore che non fa più parte dello staff, ri-esegui lo
  script con `--disattiva` sullo stesso username.

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
