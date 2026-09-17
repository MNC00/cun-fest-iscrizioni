-- Migrazione: aggiunge il token per l'annullamento self-service dell'iscrizione.
-- Da eseguire su un database già esistente (se si parte da sql/schema.sql non serve,
-- è già incluso).

ALTER TABLE partecipanti ADD COLUMN IF NOT EXISTS token_annullamento TEXT UNIQUE;
CREATE INDEX IF NOT EXISTS ix_partecipanti_token_annullamento ON partecipanti(token_annullamento);

-- Valorizza il token per le iscrizioni già esistenti che ne sono prive.
UPDATE partecipanti SET token_annullamento = gen_random_uuid()::text WHERE token_annullamento IS NULL;
