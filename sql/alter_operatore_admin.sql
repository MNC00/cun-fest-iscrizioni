-- Migrazione: aggiunge il ruolo "amministratore" agli operatori, necessario
-- per accedere alla nuova sezione /configurazione (date evento, tariffe,
-- gestione operatori).
--
-- Da eseguire UNA VOLTA sul database esistente (SQL Editor di Supabase).
-- Idempotente: puo' essere rieseguita senza errori.

ALTER TABLE operatori ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

-- Promuovi il primo amministratore (necessario: senza questo passaggio
-- nessuno può accedere a /configurazione finché non lo fai da qui o con
-- `python scripts/crea_operatore.py --username <tuo_username> --admin`).
-- Sostituisci 'tuo_username' con lo username del tuo account operatore.
-- UPDATE operatori SET is_admin = TRUE WHERE username = 'tuo_username';
