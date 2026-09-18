-- Reset dei dati di edizione per il CUN Fest.
-- Da eseguire nel SQL Editor di Supabase quando si chiude un'edizione e si
-- vuole ripartire puliti per quella successiva.
--
-- ATTENZIONE: operazione distruttiva e IRREVERSIBILE. Prima di eseguirla,
-- fare un backup/export dei dati (es. Supabase > Database > Backups, oppure
-- un pg_dump manuale) se servono a fini storici/contabili.

-- 1) Iscrizioni, partecipanti, pagamenti e log dell'edizione corrente.
--    RESTART IDENTITY azzera anche i contatori id (si riparte da 1).
--    CASCADE elimina automaticamente anche le ricevute di pagamento collegate
--    (tabelle ricevute_pagamento/ricevuta_partecipanti, via famiglie) — ma
--    NON i file già caricati su Supabase Storage: svuota manualmente il
--    bucket (Supabase → Storage → bucket ricevute-pagamento → seleziona
--    tutto → elimina) se vuoi liberare spazio per la nuova edizione.
TRUNCATE TABLE partecipanti, pagamenti, famiglie, log_eventi
    RESTART IDENTITY CASCADE;

-- 2) Tariffe: i prezzi cambiano ad ogni edizione, quindi si azzerano anch'esse.
--    Andranno reinserite quando note (vedi sql/seed_tariffe_esempio.sql).
TRUNCATE TABLE tariffe RESTART IDENTITY;

-- 2b) Periodi degli eventi (date valide per iscrizione/pranzo CUN): si
--     azzerano e si ricreano vuoti, da valorizzare per la nuova edizione
--     (vedi i commenti in sql/seed_tariffe_esempio.sql).
TRUNCATE TABLE periodi_evento RESTART IDENTITY;
INSERT INTO periodi_evento (tipo_evento, data_inizio, data_fine)
VALUES ('precun', NULL, NULL), ('campo_famiglie', NULL, NULL),
       ('cun_fest', NULL, NULL), ('pranzo_cun', NULL, NULL);

-- 3) Operatori: NON vengono toccati di default (lo staff spesso è lo stesso
--    tra un'edizione e l'altra). Se invece si vuole ripartire anche da zero
--    con gli account operatore, scommentare la riga seguente:
-- TRUNCATE TABLE operatori RESTART IDENTITY;
