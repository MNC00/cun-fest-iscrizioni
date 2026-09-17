-- Template per inserire le tariffe di una nuova edizione.
-- Esegui dopo sql/reset_dati.sql, quando i prezzi ufficiali sono noti.
--
-- Struttura: una riga "base" per ciascun tipo di evento (fascia = NULL,
-- si applica a tutti i partecipanti di quell'evento) più, solo se serve un
-- prezzo diverso per fascia, righe di "override" con fascia = 'Nord' o
-- 'Altro'. In fase di calcolo l'app cerca prima l'override esatto
-- (tipo_evento + fascia) e ricade sulla riga base se non lo trova: NON è
-- necessario compilare tutte le combinazioni possibili.
--
-- 'pranzo_cun' ha senso valorizzare solo prezzo_pranzo (le altre colonne
-- vengono ignorate per questo tipo di evento).
--
-- Le colonne valido_dal/valido_al su questa tabella non sono più usate per
-- validare le date di iscrizione (vedi sql/alter_evento_atomico.sql e la
-- tabella periodi_evento): puoi lasciarle NULL o usarle come promemoria.

-- Tariffe base (fascia NULL, si applicano a tutte le fasce salvo override sotto)
INSERT INTO tariffe
    (tipo_evento, fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
     tetto_spesa_fascia, sconto_giovani_percentuale, attivo)
VALUES
    ('precun',         NULL, 15.00, 3.00, 8.00,  10.00, 150.00, 20, TRUE),
    ('campo_famiglie', NULL, 15.00, 3.00, 8.00,  10.00, 150.00, 20, TRUE),
    ('cun_fest',       NULL, 20.00, 3.00, 10.00, 12.00, 200.00, 20, TRUE),
    ('pranzo_cun',     NULL, NULL,  NULL, 12.00, NULL,  NULL,   20, TRUE);

-- Esempio di override: se il CunFest deve costare diversamente per chi
-- viene dal Nord rispetto al resto d'Italia, aggiungi righe come queste
-- (altrimenti non serve inserirle: si userebbe la riga base sopra per tutti):
-- INSERT INTO tariffe
--     (tipo_evento, fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
--      tetto_spesa_fascia, sconto_giovani_percentuale, attivo)
-- VALUES
--     ('cun_fest', 'Nord',  18.00, 3.00, 9.00, 11.00, 180.00, 20, TRUE),
--     ('cun_fest', 'Altro', 20.00, 3.00, 10.00, 12.00, 200.00, 20, TRUE);

-- Date di ciascun evento (obbligatorie per la validazione delle date di
-- iscrizione e per l'auto-compilazione della data del pranzo CUN):
-- UPDATE periodi_evento SET data_inizio = '2027-08-01', data_fine = '2027-08-03' WHERE tipo_evento = 'precun';
-- UPDATE periodi_evento SET data_inizio = '2027-08-01', data_fine = '2027-08-03' WHERE tipo_evento = 'campo_famiglie';
-- UPDATE periodi_evento SET data_inizio = '2027-08-03', data_fine = '2027-08-10' WHERE tipo_evento = 'cun_fest';
-- UPDATE periodi_evento SET data_inizio = '2027-08-06', data_fine = '2027-08-06' WHERE tipo_evento = 'pranzo_cun';
