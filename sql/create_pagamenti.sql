-- Tabella pagamenti: uno stato di pagamento per partecipante.
-- Da eseguire nell'editor SQL di Supabase (o via psql) sul database del progetto.

CREATE TABLE IF NOT EXISTS pagamenti (
    id SERIAL PRIMARY KEY,
    partecipante_id INTEGER REFERENCES partecipanti(id) ON DELETE CASCADE,
    importo_dovuto NUMERIC,
    importo_pagato NUMERIC,
    stato TEXT DEFAULT 'Non_pagato' CHECK (
        stato IN ('Non_pagato', 'Parzialmente_pagato', 'Pagato', 'Rimborsato')
    ),
    data_pagamento DATE,
    metodo TEXT,
    causale TEXT,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pagamenti_partecipante_id ON pagamenti(partecipante_id);
CREATE INDEX IF NOT EXISTS idx_pagamenti_stato ON pagamenti(stato);
