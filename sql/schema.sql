-- Schema completo dell'app CUN Fest Iscrizioni.
-- Fonte di verità per una installazione nuova (nuovo progetto Supabase,
-- nuovo ambiente di test, ecc.). Idempotente: puo' essere rieseguito senza
-- errori grazie a IF NOT EXISTS.
--
-- Riflette 1:1 i modelli SQLAlchemy in app/models.py.
-- Da eseguire nel SQL Editor di Supabase (o via psql) PRIMA di avviare l'app
-- su un database vuoto.

CREATE TABLE IF NOT EXISTS famiglie (
    id SERIAL PRIMARY KEY,
    referente_nome TEXT NOT NULL,
    referente_cognome TEXT NOT NULL,
    email TEXT NOT NULL,
    telefono TEXT,
    zona_provenienza TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS partecipanti (
    id SERIAL PRIMARY KEY,
    famiglia_id INTEGER REFERENCES famiglie(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    cognome TEXT NOT NULL,
    data_nascita DATE,
    luogo_nascita TEXT,
    zona_provenienza TEXT,
    data_arrivo DATE,
    data_partenza DATE,
    pasto_arrivo TEXT,
    pasto_partenza TEXT,
    flag_solo_pranzo_cun BOOLEAN DEFAULT FALSE,
    flag_bosco_domenica BOOLEAN DEFAULT FALSE,
    flag_cena_ristorante_domenica BOOLEAN,
    tipo_evento TEXT DEFAULT 'solo_cun', -- 'precun_cun' | 'campo_famiglie_cun' | 'solo_cun'
    note TEXT,
    fascia_prezzo TEXT DEFAULT 'Generale',
    stato_iscrizione TEXT DEFAULT 'Inviata',
    token_annullamento TEXT UNIQUE,
    notti_calcolate INTEGER,
    prezzo_lordo NUMERIC,
    sconto_eta NUMERIC,
    prezzo_netto NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_partecipanti_famiglia_id ON partecipanti(famiglia_id);
CREATE INDEX IF NOT EXISTS ix_partecipanti_token_annullamento ON partecipanti(token_annullamento);

CREATE TABLE IF NOT EXISTS pagamenti (
    id SERIAL PRIMARY KEY,
    partecipante_id INTEGER REFERENCES partecipanti(id) ON DELETE CASCADE,
    importo_dovuto NUMERIC,
    importo_pagato NUMERIC DEFAULT 0,
    stato TEXT DEFAULT 'Non_pagato', -- 'Non_pagato', 'Parzialmente_pagato', 'Pagato', 'Rimborsato'
    data_pagamento DATE,
    metodo TEXT,                    -- es. 'bonifico', 'carta', 'altro'
    causale TEXT,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_pagamenti_partecipante_id ON pagamenti(partecipante_id);

CREATE TABLE IF NOT EXISTS tariffe (
    id SERIAL PRIMARY KEY,
    fascia TEXT NOT NULL,           -- 'Generale', 'Uninord', 'Unisud'
    prezzo_notte NUMERIC,
    prezzo_colazione NUMERIC,
    prezzo_pranzo NUMERIC,
    prezzo_cena NUMERIC,
    tetto_spesa_fascia NUMERIC,
    sconto_giovani_percentuale NUMERIC,
    valido_dal DATE,
    valido_al DATE,
    attivo BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS operatori (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nome TEXT,
    attivo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS log_eventi (
    id SERIAL PRIMARY KEY,
    oggetto_tipo TEXT,
    oggetto_id INTEGER,
    azione TEXT,
    operatore TEXT,
    dettagli JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_log_eventi_oggetto ON log_eventi(oggetto_tipo, oggetto_id);
