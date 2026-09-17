-- Migrazione: aggiunge il luogo di nascita del partecipante.
-- Da eseguire su un database già esistente (se si parte da sql/schema.sql non serve,
-- è già incluso).

ALTER TABLE partecipanti ADD COLUMN IF NOT EXISTS luogo_nascita TEXT;
