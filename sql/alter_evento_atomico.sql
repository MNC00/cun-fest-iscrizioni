-- Migrazione: modello "eventi atomici" per i partecipanti, tariffe per
-- tipo di evento, tabella periodi_evento dedicata alle date, rinomina fasce.
--
-- Da eseguire UNA VOLTA sul database esistente (SQL Editor di Supabase),
-- dopo aver aggiornato il codice dell'app. Idempotente dove possibile.
--
-- ATTENZIONE - assunzioni fatte in questa migrazione (verificare prima di
-- eseguirla se non corrispondono al caso reale):
--   1) La colonna partecipanti.tipo_evento (valori 'precun_cun',
--      'campo_famiglie_cun', 'solo_cun') viene mappata sui 3 nuovi flag
--      booleani come segue:
--        precun_cun         -> flag_precun = TRUE, flag_cun_fest = TRUE
--        campo_famiglie_cun -> flag_campo_famiglie = TRUE, flag_cun_fest = TRUE
--        solo_cun           -> flag_cun_fest = TRUE
--   2) Le fasce tariffarie vengono rinominate: 'Uninord' -> 'Nord',
--      'Unisud' -> 'Altro', ed eventuali righe/partecipanti con fascia
--      'Generale' (ormai eliminata) vengono spostati su 'Altro'.

-- 1) Partecipanti: nuovi flag evento
ALTER TABLE partecipanti ADD COLUMN IF NOT EXISTS flag_precun BOOLEAN DEFAULT FALSE;
ALTER TABLE partecipanti ADD COLUMN IF NOT EXISTS flag_campo_famiglie BOOLEAN DEFAULT FALSE;
ALTER TABLE partecipanti ADD COLUMN IF NOT EXISTS flag_cun_fest BOOLEAN DEFAULT FALSE;

UPDATE partecipanti SET flag_precun = TRUE, flag_cun_fest = TRUE
    WHERE tipo_evento = 'precun_cun';
UPDATE partecipanti SET flag_campo_famiglie = TRUE, flag_cun_fest = TRUE
    WHERE tipo_evento = 'campo_famiglie_cun';
UPDATE partecipanti SET flag_cun_fest = TRUE
    WHERE tipo_evento = 'solo_cun' OR tipo_evento IS NULL;

ALTER TABLE partecipanti DROP COLUMN IF EXISTS tipo_evento;

-- 2) Fasce prezzo: Uninord -> Nord, Unisud/Generale -> Altro
UPDATE partecipanti SET fascia_prezzo = 'Nord' WHERE fascia_prezzo = 'Uninord';
UPDATE partecipanti SET fascia_prezzo = 'Altro' WHERE fascia_prezzo IN ('Unisud', 'Generale');
ALTER TABLE partecipanti ALTER COLUMN fascia_prezzo SET DEFAULT 'Altro';

-- 3) Tariffe: aggiunge tipo_evento, permette fascia NULL (tariffa base
--    dell'evento), rinomina le fasce esistenti.
ALTER TABLE tariffe ADD COLUMN IF NOT EXISTS tipo_evento TEXT;
ALTER TABLE tariffe ALTER COLUMN fascia DROP NOT NULL;

UPDATE tariffe SET fascia = 'Nord' WHERE fascia = 'Uninord';
UPDATE tariffe SET fascia = 'Altro' WHERE fascia IN ('Unisud', 'Generale');

-- Le tariffe esistenti (create prima di questa migrazione) valevano per
-- tutti gli eventi indistintamente: qui vengono clonate come tariffa base
-- per ciascuno dei 4 tipi di evento. Rivedi/adatta i prezzi manualmente
-- in base alle esigenze reali (specialmente per 'pranzo_cun', dove ha senso
-- solo prezzo_pranzo).
INSERT INTO tariffe (tipo_evento, fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
                      tetto_spesa_fascia, sconto_giovani_percentuale, valido_dal, valido_al, attivo)
SELECT 'precun', fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
       tetto_spesa_fascia, sconto_giovani_percentuale, valido_dal, valido_al, attivo
FROM tariffe WHERE tipo_evento IS NULL;

INSERT INTO tariffe (tipo_evento, fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
                      tetto_spesa_fascia, sconto_giovani_percentuale, valido_dal, valido_al, attivo)
SELECT 'campo_famiglie', fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
       tetto_spesa_fascia, sconto_giovani_percentuale, valido_dal, valido_al, attivo
FROM tariffe WHERE tipo_evento IS NULL;

INSERT INTO tariffe (tipo_evento, fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
                      tetto_spesa_fascia, sconto_giovani_percentuale, valido_dal, valido_al, attivo)
SELECT 'pranzo_cun', fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
       tetto_spesa_fascia, sconto_giovani_percentuale, valido_dal, valido_al, attivo
FROM tariffe WHERE tipo_evento IS NULL;

-- Le righe originali (tipo_evento ancora NULL) diventano la tariffa di 'cun_fest'.
UPDATE tariffe SET tipo_evento = 'cun_fest' WHERE tipo_evento IS NULL;

ALTER TABLE tariffe ALTER COLUMN tipo_evento SET NOT NULL;

-- 4) Nuova tabella periodi_evento (date di ciascun evento, indipendenti
--    dalle tariffe). Popola le date reali per ogni edizione: finché restano
--    NULL, l'app non applica alcun vincolo di data per quell'evento.
CREATE TABLE IF NOT EXISTS periodi_evento (
    id SERIAL PRIMARY KEY,
    tipo_evento TEXT NOT NULL UNIQUE,
    data_inizio DATE,
    data_fine DATE
);

INSERT INTO periodi_evento (tipo_evento, data_inizio, data_fine)
VALUES ('precun', NULL, NULL), ('campo_famiglie', NULL, NULL),
       ('cun_fest', NULL, NULL), ('pranzo_cun', NULL, NULL)
ON CONFLICT (tipo_evento) DO NOTHING;
