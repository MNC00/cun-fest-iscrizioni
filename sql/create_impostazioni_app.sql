CREATE TABLE IF NOT EXISTS impostazioni_app (
    chiave TEXT PRIMARY KEY,
    valore TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);