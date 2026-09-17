from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import LogEvento, Partecipante, PeriodoEvento, Tariffa

ANNO_RIFERIMENTO = 2026
ETA_LIMITE_SCONTO_GIOVANI = 30

PASTI_VALIDI = {"colazione", "pranzo", "cena"}

# Eventi "atomici" che un partecipante può combinare liberamente (con l'unico
# vincolo che precun e campo_famiglie sono mutuamente esclusivi, applicato in
# app/schemas.py). "pranzo_cun" è un'iscrizione a sé, gestita separatamente.
EVENTI_ATOMICI = ["precun", "campo_famiglie", "cun_fest"]

# Colonna booleana di Partecipante corrispondente a ciascun tipo di evento,
# usata per i filtri di dashboard/pagamenti/comunicazioni/report pasti.
COLONNA_EVENTO = {
    "precun": Partecipante.flag_precun,
    "campo_famiglie": Partecipante.flag_campo_famiglie,
    "cun_fest": Partecipante.flag_cun_fest,
    "pranzo_cun": Partecipante.flag_solo_pranzo_cun,
}


class CalcoloPrezzoError(Exception):
    """Errore applicativo nel calcolo del prezzo di un partecipante."""


def componenti_selezionati(partecipante: Partecipante) -> list:
    """Ritorna la lista degli eventi atomici a cui il partecipante è iscritto
    (esclude 'pranzo_cun', che è un'iscrizione a sé stante)."""
    return [
        evento
        for evento in EVENTI_ATOMICI
        if getattr(partecipante, f"flag_{evento}", False)
    ]


def categoria_tariffa(partecipante: Partecipante) -> str:
    """Determina quale tipo di evento governa il calcolo del prezzo quando un
    partecipante seleziona più eventi atomici insieme (es. precun + cun_fest).

    Semplificazione consapevole: non si dividono le notti/pasti per periodo di
    ogni singolo evento, si usa un'unica tariffa "categoria" per l'intero
    soggiorno, con priorità Campo Famiglie > PreCunFest > CunFest (i primi due
    sono programmi più specifici quando presenti in combinazione con CunFest).
    """
    if partecipante.flag_solo_pranzo_cun:
        return "pranzo_cun"
    if partecipante.flag_campo_famiglie:
        return "campo_famiglie"
    if partecipante.flag_precun:
        return "precun"
    return "cun_fest"


def ottieni_periodo_evento(db: Session, tipi_evento: list | None = None) -> tuple:
    """Ritorna (data_min, data_max) del periodo valido, unione delle finestre
    configurate in `periodi_evento` per i tipi di evento indicati (o per tutti
    i tipi configurati se tipi_evento è None).

    Se nessuna finestra è configurata per i tipi richiesti, ritorna (None, None):
    nessun vincolo applicato (coerente con lo scenario "date non ancora note").
    """
    query = db.query(PeriodoEvento.data_inizio, PeriodoEvento.data_fine)
    if tipi_evento is not None:
        query = query.filter(PeriodoEvento.tipo_evento.in_(tipi_evento))
    righe = query.all()

    date_inizio = [r.data_inizio for r in righe if r.data_inizio is not None]
    date_fine = [r.data_fine for r in righe if r.data_fine is not None]

    data_min = min(date_inizio) if date_inizio else None
    data_max = max(date_fine) if date_fine else None
    return data_min, data_max


def _trova_tariffa(db: Session, tipo_evento: str, fascia: str) -> Tariffa:
    """Cerca la tariffa attiva per (tipo_evento, fascia); se non c'è un
    override specifico per quella fascia, ricade sulla tariffa base
    dell'evento (fascia NULL)."""
    tariffa = (
        db.query(Tariffa)
        .filter(Tariffa.tipo_evento == tipo_evento, Tariffa.fascia == fascia, Tariffa.attivo.is_(True))
        .first()
    )
    if tariffa:
        return tariffa

    tariffa = (
        db.query(Tariffa)
        .filter(Tariffa.tipo_evento == tipo_evento, Tariffa.fascia.is_(None), Tariffa.attivo.is_(True))
        .first()
    )
    if not tariffa:
        raise CalcoloPrezzoError(
            f"Nessuna tariffa attiva trovata per l'evento '{tipo_evento}' (fascia '{fascia}')."
        )
    return tariffa


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


def _applica_tetto_e_sconto(prezzo_lordo: float, tariffa: Tariffa, partecipante: Partecipante) -> tuple:
    """Applica il tetto di spesa e lo sconto giovani, condivisi tra tutti i percorsi di calcolo."""
    if tariffa.tetto_spesa_fascia is not None and prezzo_lordo > float(tariffa.tetto_spesa_fascia):
        prezzo_lordo = float(tariffa.tetto_spesa_fascia)

    sconto_eta = 0.0
    eta = None
    if partecipante.data_nascita:
        eta = ANNO_RIFERIMENTO - partecipante.data_nascita.year
        if eta <= ETA_LIMITE_SCONTO_GIOVANI:
            sconto_percentuale = float(tariffa.sconto_giovani_percentuale or 0)
            sconto_eta = prezzo_lordo * (sconto_percentuale / 100)

    return prezzo_lordo, sconto_eta, eta


def _salva_e_logga(partecipante: Partecipante, db: Session, dettagli: dict) -> dict:
    partecipante.notti_calcolate = dettagli["notti"]
    partecipante.prezzo_lordo = dettagli["prezzo_lordo"]
    partecipante.sconto_eta = dettagli["sconto_eta"]
    partecipante.prezzo_netto = dettagli["prezzo_netto"]
    partecipante.stato_iscrizione = "Calcolata"

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


def _calcola_prezzo_solo_pranzo_cun(partecipante: Partecipante, db: Session) -> dict:
    """'Solo pranzo CUN' è un giorno fisso e un prezzo flat (nessuna notte, un
    solo pranzo): se le date non sono valorizzate le imposta automaticamente
    dalla finestra configurata in periodi_evento per 'pranzo_cun'."""
    if not partecipante.data_arrivo or not partecipante.data_partenza:
        data_inizio, data_fine = ottieni_periodo_evento(db, ["pranzo_cun"])
        if not data_inizio:
            raise CalcoloPrezzoError(
                "Data del pranzo CUN non ancora configurata (tabella periodi_evento)."
            )
        partecipante.data_arrivo = data_inizio
        partecipante.data_partenza = data_fine or data_inizio

    partecipante.pasto_arrivo = "pranzo"
    partecipante.pasto_partenza = "pranzo"

    tariffa = _trova_tariffa(db, "pranzo_cun", partecipante.fascia_prezzo)
    prezzo_lordo = float(tariffa.prezzo_pranzo or 0)
    prezzo_lordo, sconto_eta, eta = _applica_tetto_e_sconto(prezzo_lordo, tariffa, partecipante)
    prezzo_netto = prezzo_lordo - sconto_eta

    dettagli = {
        "notti": 0,
        "colazioni": 0,
        "pranzi": 1,
        "cene": 0,
        "fascia_prezzo": partecipante.fascia_prezzo,
        "tipo_evento_tariffa": "pranzo_cun",
        "tariffa_id": tariffa.id,
        "flag_solo_pranzo_cun": True,
        "eta": eta,
        "prezzo_lordo": prezzo_lordo,
        "sconto_eta": sconto_eta,
        "prezzo_netto": prezzo_netto,
    }
    return _salva_e_logga(partecipante, db, dettagli)


def calcola_prezzo_partecipante(partecipante: Partecipante, db: Session) -> dict:
    """Calcola notti, pasti e prezzo netto di un partecipante, aggiorna il DB e logga l'evento.

    Ritorna un dizionario con tutti i valori calcolati.
    """
    if partecipante.flag_solo_pranzo_cun:
        return _calcola_prezzo_solo_pranzo_cun(partecipante, db)

    if not partecipante.data_arrivo or not partecipante.data_partenza:
        raise CalcoloPrezzoError("Il partecipante non ha date di arrivo/partenza valide.")

    if partecipante.data_partenza < partecipante.data_arrivo:
        raise CalcoloPrezzoError("La data di partenza precede la data di arrivo.")

    notti = (partecipante.data_partenza - partecipante.data_arrivo).days
    if partecipante.flag_bosco_domenica:
        # Chi partecipa solo a "Parliamone" del lunedì arriva la domenica sera
        # per dormire a Bosco: notte aggiuntiva non coperta dall'intervallo
        # arrivo/partenza dichiarato (che tipicamente indica solo il lunedì).
        notti += 1

    pasti = _conta_pasti(partecipante)
    colazioni, pranzi, cene = pasti["colazioni"], pasti["pranzi"], pasti["cene"]

    categoria = categoria_tariffa(partecipante)
    tariffa = _trova_tariffa(db, categoria, partecipante.fascia_prezzo)

    prezzo_lordo = (
        notti * float(tariffa.prezzo_notte or 0)
        + colazioni * float(tariffa.prezzo_colazione or 0)
        + pranzi * float(tariffa.prezzo_pranzo or 0)
        + cene * float(tariffa.prezzo_cena or 0)
    )

    prezzo_lordo, sconto_eta, eta = _applica_tetto_e_sconto(prezzo_lordo, tariffa, partecipante)
    prezzo_netto = prezzo_lordo - sconto_eta

    dettagli = {
        "notti": notti,
        "colazioni": colazioni,
        "pranzi": pranzi,
        "cene": cene,
        "fascia_prezzo": partecipante.fascia_prezzo,
        "tipo_evento_tariffa": categoria,
        "tariffa_id": tariffa.id,
        "flag_solo_pranzo_cun": False,
        "eta": eta,
        "prezzo_lordo": prezzo_lordo,
        "sconto_eta": sconto_eta,
        "prezzo_netto": prezzo_netto,
    }
    return _salva_e_logga(partecipante, db, dettagli)


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


def genera_report_pasti(db: Session, tipo_evento: str | None = None) -> list:
    """Genera il report giornaliero dei pasti per tutti i partecipanti attivi.

    Considera solo i partecipanti con stato_iscrizione diverso da 'Annullata'
    e con date di arrivo/partenza valorizzate. Copre l'intero intervallo tra
    la data di arrivo più vecchia e la data di partenza più recente.
    Se tipo_evento è valorizzato (precun/campo_famiglie/cun_fest/pranzo_cun),
    filtra solo i partecipanti iscritti a quell'evento (un partecipante può
    comparire in più filtri se ha selezionato più eventi).
    """
    query = db.query(Partecipante).filter(
        Partecipante.stato_iscrizione != "Annullata",
        Partecipante.data_arrivo.isnot(None),
        Partecipante.data_partenza.isnot(None),
    )
    if tipo_evento:
        colonna = COLONNA_EVENTO.get(tipo_evento)
        if colonna is not None:
            query = query.filter(colonna.is_(True))
    partecipanti = query.all()

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
