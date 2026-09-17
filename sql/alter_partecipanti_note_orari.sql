-- Aggiunge ai partecipanti:
-- - flag arrivo dopo cena / partenza prima di colazione (aggiungono 1 notte, nessun pasto)
-- - campo note libere (preferenze stanza, restrizioni alimentari, ecc.)
-- Da eseguire nell'editor SQL di Supabase (o via psql) sul database del progetto.

ALTER TABLE partecipanti
    ADD COLUMN IF NOT EXISTS flag_arrivo_dopo_cena BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS flag_partenza_prima_colazione BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS note TEXT;
