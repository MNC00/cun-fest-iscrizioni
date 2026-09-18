-- Migrazione: aggiunge la gestione delle ricevute di pagamento caricate
-- dalle famiglie (bonifici) e verificate manualmente dagli operatori.
--
-- Da eseguire UNA VOLTA sul database esistente (SQL Editor di Supabase).
-- Idempotente: puo' essere rieseguita senza errori.
--
-- ATTENZIONE: richiede anche la creazione di un bucket di Supabase Storage
-- (vedi app/storage_service.py per le variabili d'ambiente necessarie):
--   1. Supabase → Storage → New bucket → nome "ricevute-pagamento" (o quello
--      che imposti in SUPABASE_STORAGE_BUCKET) → Public bucket = NO (privato:
--      l'accesso ai file passa sempre dal backend, mai direttamente dal
--      browser dell'utente).
--   2. Recupera Project Settings → API → "service_role" key (segreta!) e
--      impostala come SUPABASE_SERVICE_ROLE_KEY nelle variabili d'ambiente
--      dell'app (Render + .env locale), insieme a SUPABASE_URL (Project URL).

ALTER TABLE famiglie ADD COLUMN IF NOT EXISTS token_ricevute TEXT UNIQUE;
CREATE INDEX IF NOT EXISTS ix_famiglie_token_ricevute ON famiglie(token_ricevute);

CREATE TABLE IF NOT EXISTS ricevute_pagamento (
    id SERIAL PRIMARY KEY,
    famiglia_id INTEGER REFERENCES famiglie(id) ON DELETE CASCADE NOT NULL,
    nome_file_originale TEXT NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    content_type TEXT,
    dimensione_bytes INTEGER,
    note TEXT,
    verificata BOOLEAN DEFAULT FALSE,
    verificata_da TEXT,
    verificata_il TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ricevute_pagamento_famiglia_id ON ricevute_pagamento(famiglia_id);

CREATE TABLE IF NOT EXISTS ricevuta_partecipanti (
    ricevuta_id INTEGER REFERENCES ricevute_pagamento(id) ON DELETE CASCADE,
    partecipante_id INTEGER REFERENCES partecipanti(id) ON DELETE CASCADE,
    PRIMARY KEY (ricevuta_id, partecipante_id)
);

CREATE INDEX IF NOT EXISTS ix_ricevuta_partecipanti_partecipante_id ON ricevuta_partecipanti(partecipante_id);

-- Le famiglie già esistenti non hanno ancora un token_ricevute: l'app lo
-- genera automaticamente al primo accesso necessario (invio email o
-- apertura della pagina di upload), non serve backfillarlo manualmente qui.
