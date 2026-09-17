-- Aggiunge ai partecipanti il campo note libere (preferenze stanza, restrizioni
-- alimentari, ecc.). Gli orari "dopo cena" / "prima di colazione" non sono più
-- flag separati: sono semplicemente valori validi delle colonne pasto_arrivo e
-- pasto_partenza (già di tipo testo, nessuna modifica di schema necessaria).
-- Da eseguire nell'editor SQL di Supabase (o via psql) sul database del progetto.

ALTER TABLE partecipanti
    ADD COLUMN IF NOT EXISTS note TEXT;

-- Se in un tentativo precedente erano state create le colonne flag, si possono rimuovere:
ALTER TABLE partecipanti
    DROP COLUMN IF EXISTS flag_arrivo_dopo_cena,
    DROP COLUMN IF EXISTS flag_partenza_prima_colazione;
