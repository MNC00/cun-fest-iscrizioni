-- Sostituisce il vecchio flag "Parliamo solo lunedì" (mai collegato a una logica
-- di calcolo) con il suo significato reale: chi partecipa solo all'incontro
-- "Parliamone" del lunedì arriva la domenica sera e dorme a Bosco (+1 notte nel
-- prezzo), e sceglie se cenare al ristorante organizzato dalla festa oppure
-- autonomamente (informativo, nessun impatto sul prezzo).
--
-- Aggiunge anche tipo_evento per distinguere i tre pacchetti (PreCunFest+CunFest,
-- Campo Famiglie+CunFest, solo CunFest): stesso periodo per tutti, usato solo
-- per la reportistica/i filtri lato operatori, non per il calcolo del prezzo.
--
-- Da eseguire nell'editor SQL di Supabase (o via psql) sul database del progetto.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'partecipanti' AND column_name = 'flag_parliamo_solo_lunedi'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'partecipanti' AND column_name = 'flag_bosco_domenica'
    ) THEN
        ALTER TABLE partecipanti RENAME COLUMN flag_parliamo_solo_lunedi TO flag_bosco_domenica;
    END IF;
END $$;

ALTER TABLE partecipanti
    ADD COLUMN IF NOT EXISTS flag_bosco_domenica BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS flag_cena_ristorante_domenica BOOLEAN,
    ADD COLUMN IF NOT EXISTS tipo_evento TEXT DEFAULT 'solo_cun';
