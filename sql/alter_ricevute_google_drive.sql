ALTER TABLE ricevute_pagamento
    ADD COLUMN IF NOT EXISTS drive_file_id TEXT,
    ADD COLUMN IF NOT EXISTS drive_copia_stato TEXT NOT NULL DEFAULT 'non_configurata',
    ADD COLUMN IF NOT EXISTS drive_errore TEXT;