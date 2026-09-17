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

Se i prezzi non sono ancora noti al momento dell'apertura iscrizioni, non è
un problema: l'app supporta iscrizioni con `tariffe` vuota (i prezzi restano
`None` finché un operatore non lancia il ricalcolo da `/dashboard`, che invia
automaticamente l'email di aggiornamento prezzo a tutti gli interessati).

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
- `BREVO_API_KEY` / `BREVO_SENDER_EMAIL` — se cambia il mittente ufficiale.
- `DATABASE_URL` / `SECRET_KEY` — di norma invariati tra edizioni.

## 5. Verifica finale

- Apri `/iscriviti` e invia un'iscrizione di prova.
- Fai login su `/login` e controlla `/dashboard`, `/pagamenti`,
  `/report-pasti`.
- Se le tariffe sono già note, verifica che il prezzo calcolato sia corretto.
- Cancella eventuali iscrizioni di prova con "Annulla iscrizione" o via SQL.

A questo punto il sistema è pronto per la nuova edizione.
