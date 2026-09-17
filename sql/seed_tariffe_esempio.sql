-- Template per inserire le tariffe di una nuova edizione.
-- Esegui dopo sql/reset_dati.sql, quando i prezzi ufficiali sono noti.
-- Una riga per fascia; modifica i valori con i prezzi reali dell'edizione.

INSERT INTO tariffe
    (fascia, prezzo_notte, prezzo_colazione, prezzo_pranzo, prezzo_cena,
     tetto_spesa_fascia, sconto_giovani_percentuale, valido_dal, valido_al, attivo)
VALUES
    ('Generale', 20.00, 3.00, 10.00, 12.00, 200.00, 20, '2027-08-01', '2027-08-10', TRUE),
    ('Uninord',  15.00, 3.00, 8.00,  10.00, 150.00, 20, '2027-08-01', '2027-08-10', TRUE),
    ('Unisud',   15.00, 3.00, 8.00,  10.00, 150.00, 20, '2027-08-01', '2027-08-10', TRUE);
