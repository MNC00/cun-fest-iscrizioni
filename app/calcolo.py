from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import LogEvento, Partecipante, Tariffa

ANNO_RIFERIMENTO = 2026
ETA_LIMITE_SCONTO_GIOVANI = 30

PASTI_VALIDI = {"colazione", "pranzo", "cena"}


class CalcoloPrezzoError(Exception):
    """Errore applicativo nel calcolo del prezzo di un partecipante."""


def _conta_pasti(partecipante: Partecipante) -> dict:
    """Conta colazioni, pranzi e cene dovuti in base al soggiorno del partecipante."""
    colazioni = pranzi = cene = 0

    if partecipante.flag_solo_pranzo_cun:
        # Solo pranzi: uno per ogni giorno tra arrivo e partenza (inclusi entrambi)
        pranzi = (partecipante.data_partenza - partecipante.data_arrivo).days + 1
        return {"colazioni": 0, "pranzi": pranzi, "cene": 0}

    def incrementa(pasto: str):
        nonlocal colazioni, pranzi, cene
        if pasto == "colazione":
            colazioni += 1
        elif pasto == "pranzo":
            pranzi += 1
        elif pasto == "cena":
            cene += 1
        # "nessuno", "dopo_cena", "prima_colazione" o valori non riconosciuti: nessun incremento.
        # La notte del giorno di arrivo/partenza è già inclusa nel calcolo di "notti"
        # (basato sulla differenza di date), quindi non serve alcuna notte aggiuntiva.

    if partecipante.data_arrivo == partecipante.data_partenza:
        # Stesso giorno: si applicano sia il pasto di arrivo che quello di partenza
        incrementa(partecipante.pasto_arrivo)
        incrementa(partecipante.pasto_partenza)
        return {"colazioni": colazioni, "pranzi": pranzi, "cene": cene}

    # Giorno di arrivo
    incrementa(partecipante.pasto_arrivo)

    # Giorni interni: colazione + pranzo + cena per ciascuno
    giorno = partecipante.data_arrivo + timedelta(days=1)
    while giorno < partecipante.data_partenza:
        colazioni += 1
        pranzi += 1
        cene += 1
        giorno += timedelta(days=1)

    # Giorno di partenza
    incrementa(partecipante.pasto_partenza)

    return {"colazioni": colazioni, "pranzi": pranzi, "cene": cene}


def calcola_prezzo_partecipante(partecipante: Partecipante, db: Session) -> dict:
    """Calcola notti, pasti e prezzo netto di un partecipante, aggiorna il DB e logga l'evento.

    Ritorna un dizionario con tutti i valori calcolati.
    """
    if not partecipante.data_arrivo or not partecipante.data_partenza:
        raise CalcoloPrezzoError("Il partecipante non ha date di arrivo/partenza valide.")

    if partecipante.data_partenza < partecipante.data_arrivo:
        raise CalcoloPrezzoError("La data di partenza precede la data di arrivo.")

    notti = (partecipante.data_partenza - partecipante.data_arrivo).days

    pasti = _conta_pasti(partecipante)
    colazioni, pranzi, cene = pasti["colazioni"], pasti["pranzi"], pasti["cene"]

    tariffa = (
        db.query(Tariffa)
        .filter(Tariffa.fascia == partecipante.fascia_prezzo, Tariffa.attivo.is_(True))
        .first()
    )
    if not tariffa:
        raise CalcoloPrezzoError(
            f"Nessuna tariffa attiva trovata per la fascia '{partecipante.fascia_prezzo}'."
        )

    if partecipante.flag_solo_pranzo_cun:
        prezzo_lordo = pranzi * float(tariffa.prezzo_pranzo or 0)
    else:
        prezzo_lordo = (
            notti * float(tariffa.prezzo_notte or 0)
            + colazioni * float(tariffa.prezzo_colazione or 0)
            + pranzi * float(tariffa.prezzo_pranzo or 0)
            + cene * float(tariffa.prezzo_cena or 0)
        )

    if tariffa.tetto_spesa_fascia is not None and prezzo_lordo > float(tariffa.tetto_spesa_fascia):
        prezzo_lordo = float(tariffa.tetto_spesa_fascia)

    sconto_eta = 0.0
    eta = None
    if partecipante.data_nascita:
        eta = ANNO_RIFERIMENTO - partecipante.data_nascita.year
        if eta <= ETA_LIMITE_SCONTO_GIOVANI:
            sconto_percentuale = float(tariffa.sconto_giovani_percentuale or 0)
            sconto_eta = prezzo_lordo * (sconto_percentuale / 100)

    prezzo_netto = prezzo_lordo - sconto_eta

    partecipante.notti_calcolate = notti
    partecipante.prezzo_lordo = prezzo_lordo
    partecipante.sconto_eta = sconto_eta
    partecipante.prezzo_netto = prezzo_netto
    partecipante.stato_iscrizione = "Calcolata"

    dettagli = {
        "notti": notti,
        "colazioni": colazioni,
        "pranzi": pranzi,
        "cene": cene,
        "fascia_prezzo": partecipante.fascia_prezzo,
        "tariffa_id": tariffa.id,
        "flag_solo_pranzo_cun": partecipante.flag_solo_pranzo_cun,
        "eta": eta,
        "prezzo_lordo": prezzo_lordo,
        "sconto_eta": sconto_eta,
        "prezzo_netto": prezzo_netto,
    }

    log = LogEvento(
        oggetto_tipo="partecipante",
        oggetto_id=partecipante.id,
        azione="prezzo_calcolato",
        operatore="sistema",
        dettagli=dettagli,
    )
    db.add(log)
    db.add(partecipante)
    db.commit()
    db.refresh(partecipante)

    return dettagli


def calcola_pasti_per_giorno(partecipante: Partecipante, db: Session = None) -> dict:
    """Calcola, giorno per giorno, quali pasti sono dovuti per un partecipante.

    Ritorna un dict {data: {"colazione": bool, "pranzo": bool, "cena": bool}}.
    Riusa la stessa logica di _conta_pasti ma a granularità giornaliera.
    Il parametro db non è utilizzato nel calcolo, è mantenuto per coerenza
    con le altre funzioni che operano nel contesto di una sessione.
    """
    if not partecipante.data_arrivo or not partecipante.data_partenza:
        return {}

    risultato: dict = {}

    def imposta(giorno, pasto):
        riga = risultato.setdefault(giorno, {"colazione": False, "pranzo": False, "cena": False})
        if pasto in PASTI_VALIDI:
            riga[pasto] = True

    if partecipante.flag_solo_pranzo_cun:
        giorno = partecipante.data_arrivo
        while giorno <= partecipante.data_partenza:
            imposta(giorno, "pranzo")
            giorno += timedelta(days=1)
        return risultato

    if partecipante.data_arrivo == partecipante.data_partenza:
        imposta(partecipante.data_arrivo, partecipante.pasto_arrivo)
        imposta(partecipante.data_arrivo, partecipante.pasto_partenza)
        return risultato

    imposta(partecipante.data_arrivo, partecipante.pasto_arrivo)

    giorno = partecipante.data_arrivo + timedelta(days=1)
    while giorno < partecipante.data_partenza:
        imposta(giorno, "colazione")
        imposta(giorno, "pranzo")
        imposta(giorno, "cena")
        giorno += timedelta(days=1)

    imposta(partecipante.data_partenza, partecipante.pasto_partenza)

    return risultato


def genera_report_pasti(db: Session) -> list:
    """Genera il report giornaliero dei pasti per tutti i partecipanti attivi.

    Considera solo i partecipanti con stato_iscrizione diverso da 'Annullata'
    e con date di arrivo/partenza valorizzate. Copre l'intero intervallo tra
    la data di arrivo più vecchia e la data di partenza più recente.
    """
    partecipanti = (
        db.query(Partecipante)
        .filter(
            Partecipante.stato_iscrizione != "Annullata",
            Partecipante.data_arrivo.isnot(None),
            Partecipante.data_partenza.isnot(None),
        )
        .all()
    )

    conteggi: dict = {}
    for partecipante in partecipanti:
        pasti_giorno = calcola_pasti_per_giorno(partecipante)
        for giorno, pasti in pasti_giorno.items():
            riga = conteggi.setdefault(giorno, {"colazioni": 0, "pranzi": 0, "cene": 0})
            if pasti["colazione"]:
                riga["colazioni"] += 1
            if pasti["pranzo"]:
                riga["pranzi"] += 1
            if pasti["cena"]:
                riga["cene"] += 1

    if not conteggi:
        return []

    giorno_min = min(conteggi)
    giorno_max = max(conteggi)

    report = []
    giorno = giorno_min
    while giorno <= giorno_max:
        dati = conteggi.get(giorno, {"colazioni": 0, "pranzi": 0, "cene": 0})
        report.append({"data": giorno, **dati})
        giorno += timedelta(days=1)

    return report
