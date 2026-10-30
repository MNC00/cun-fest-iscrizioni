-- Riduce gli stati di un'iscrizione a: Attiva | Annullata | Da_calcolare.
-- Idempotente. I vecchi valori (Inviata, Calcolata, Confermata) vengono
-- riclassificati in base al prezzo: calcolato -> Attiva, altrimenti Da_calcolare.

BEGIN;

ALTER TABLE partecipanti DROP CONSTRAINT IF EXISTS ck_partecipanti_stato_iscrizione;

UPDATE partecipanti
SET stato_iscrizione = CASE
    WHEN stato_iscrizione = 'Annullata' THEN 'Annullata'
    WHEN prezzo_netto IS NOT NULL THEN 'Attiva'
    ELSE 'Da_calcolare'
END;

ALTER TABLE partecipanti
    ALTER COLUMN stato_iscrizione SET DEFAULT 'Da_calcolare',
    ALTER COLUMN stato_iscrizione SET NOT NULL;

ALTER TABLE partecipanti
    ADD CONSTRAINT ck_partecipanti_stato_iscrizione
    CHECK (stato_iscrizione IN ('Attiva', 'Annullata', 'Da_calcolare'));

COMMIT;
