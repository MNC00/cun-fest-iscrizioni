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


def _componenti_ordinati_per_prezzo(partecipante: Partecipante) -> list:
    """Ordina gli eventi selezionati dal partecipante per priorità di
    assegnazione tariffaria: Campo Famiglie e PreCunFest sono programmi più
    specifici di CunFest, quindi hanno la precedenza quando un giorno del
    soggiorno ricade nei periodi di più eventi selezionati contemporaneamente
    (o quando i periodi non sono configurati e non si può disambiguare per
    data: vedi _categoria_per_giorno)."""
    ordine = []
    if partecipante.flag_campo_famiglie:
        ordine.append("campo_famiglie")
    if partecipante.flag_precun:
        ordine.append("precun")
    if partecipante.flag_cun_fest:
        ordine.append("cun_fest")
    return ordine


def _mappa_periodi(db: Session) -> dict:
    """Ritorna {tipo_evento: (data_inizio, data_fine)} per tutte le righe di periodi_evento."""
    righe = db.query(PeriodoEvento).all()
    return {r.tipo_evento: (r.data_inizio, r.data_fine) for r in righe}


def _categoria_per_giorno(giorno: date, componenti: list, periodi: dict) -> str:
    """Determina quale tariffa (per tipo di evento) si applica a un singolo
    giorno del soggiorno di un partecipante iscritto a più eventi.

    Controlla, in ordine di priorità (vedi _componenti_ordinati_per_prezzo),
    quale evento selezionato ha un periodo configurato che copre quel giorno.
    Se nessun periodo configurato copre il giorno (es. perché le date non
    sono ancora state impostate in periodi_evento), ricade sul primo
    componente selezionato: in questo caso il calcolo equivale a usare
    un'unica tariffa "governante" per l'intero soggiorno, come comportamento
    di transizione finché i periodi non sono valorizzati."""
    for tipo in componenti:
        inizio, fine = periodi.get(tipo, (None, None))
        if inizio and fine and inizio <= giorno <= fine:
            return tipo
    return componenti[0] if componenti else "cun_fest"


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

    Il prezzo è sempre calcolato notte per notte e pasto per pasto: cambia solo
    la tariffa applicata a ciascun giorno, in base a quale evento selezionato
    (PreCunFest / Campo Famiglie / CunFest) copre quella data secondo i periodi
    configurati in periodi_evento. Tetto di spesa e sconto giovani vengono
    invece applicati una sola volta sul totale, usando la tariffa dell'evento
    "principale" (stessa priorità Campo Famiglie > PreCunFest > CunFest).

    Ritorna un dizionario con tutti i valori calcolati.
    """
    if partecipante.stato_iscrizione == "Annullata":
        raise CalcoloPrezzoError(
            "Impossibile calcolare il prezzo: l'iscrizione è stata annullata."
        )

    if partecipante.flag_solo_pranzo_cun:
        return _calcola_prezzo_solo_pranzo_cun(partecipante, db)

    if not partecipante.data_arrivo or not partecipante.data_partenza:
        raise CalcoloPrezzoError("Il partecipante non ha date di arrivo/partenza valide.")

    if partecipante.data_partenza < partecipante.data_arrivo:
        raise CalcoloPrezzoError("La data di partenza precede la data di arrivo.")

    componenti = _componenti_ordinati_per_prezzo(partecipante)
    if not componenti:
        raise CalcoloPrezzoError("Il partecipante non ha selezionato alcun evento.")

    periodi = _mappa_periodi(db)

    # Una notte per ogni giorno tra arrivo (incluso) e partenza (escluso).
    notti_giorni = []
    giorno = partecipante.data_arrivo
    while giorno < partecipante.data_partenza:
        notti_giorni.append(giorno)
        giorno += timedelta(days=1)

    if partecipante.flag_bosco_domenica:
        # Chi partecipa solo a "Parliamone" del lunedì arriva la domenica sera
        # per dormire a Bosco: notte aggiuntiva non coperta dall'intervallo
        # arrivo/partenza dichiarato. Le si assegna la categoria del giorno di
        # partenza (tipicamente il lunedì), assunzione semplificativa dato che
        # non corrisponde a una data esplicita del soggiorno dichiarato.
        notti_giorni.append(partecipante.data_partenza)

    pasti_giorno = calcola_pasti_per_giorno(partecipante)

    tariffe_cache: dict = {}

    def ottieni_tariffa(categoria: str) -> Tariffa:
        if categoria not in tariffe_cache:
            tariffe_cache[categoria] = _trova_tariffa(db, categoria, partecipante.fascia_prezzo)
        return tariffe_cache[categoria]

    prezzo_lordo = 0.0
    notti_per_categoria: dict = {}
    for giorno_notte in notti_giorni:
        categoria = _categoria_per_giorno(giorno_notte, componenti, periodi)
        tariffa = ottieni_tariffa(categoria)
        prezzo_lordo += float(tariffa.prezzo_notte or 0)
        notti_per_categoria[categoria] = notti_per_categoria.get(categoria, 0) + 1

    colazioni = pranzi = cene = 0
    for giorno_pasto, pasti in pasti_giorno.items():
        categoria = _categoria_per_giorno(giorno_pasto, componenti, periodi)
        tariffa = ottieni_tariffa(categoria)
        if pasti["colazione"]:
            prezzo_lordo += float(tariffa.prezzo_colazione or 0)
            colazioni += 1
        if pasti["pranzo"]:
            prezzo_lordo += float(tariffa.prezzo_pranzo or 0)
            pranzi += 1
        if pasti["cena"]:
            prezzo_lordo += float(tariffa.prezzo_cena or 0)
            cene += 1

    notti = len(notti_giorni)

    categoria_principale = componenti[0]
    tariffa_principale = ottieni_tariffa(categoria_principale)
    prezzo_lordo, sconto_eta, eta = _applica_tetto_e_sconto(prezzo_lordo, tariffa_principale, partecipante)
    prezzo_netto = prezzo_lordo - sconto_eta

    dettagli = {
        "notti": notti,
        "colazioni": colazioni,
        "pranzi": pranzi,
        "cene": cene,
        "fascia_prezzo": partecipante.fascia_prezzo,
        "notti_per_categoria": notti_per_categoria,
        "tipo_evento_tariffa_principale": categoria_principale,
        "tariffa_id": tariffa_principale.id,
        "flag_solo_pranzo_cun": False,
        "eta": eta,
        "prezzo_lordo": prezzo_lordo,
        "sconto_eta": sconto_eta,
        "prezzo_netto": prezzo_netto,
    }
    return _salva_e_logga(partecipante, db, dettagli)


# Ordine cronologico dei pasti in un giorno, usato per "espandere" la scelta
# di arrivo/partenza in tutti i pasti effettivamente dovuti (vedi
# calcola_pasti_per_giorno): "pasto_arrivo" indica da quale pasto in poi si è
# presenti, "pasto_partenza" fino a quale pasto (incluso) si resta.
ORDINE_PASTI = ["colazione", "pranzo", "cena"]


def _pasti_da(pasto: str) -> set:
    """Pasti dovuti il giorno di arrivo, a partire da 'pasto' (incluso)."""
    if pasto not in ORDINE_PASTI:
        return set()
    return set(ORDINE_PASTI[ORDINE_PASTI.index(pasto):])


def _pasti_fino_a(pasto: str) -> set:
    """Pasti dovuti il giorno di partenza, fino a 'pasto' (incluso)."""
    if pasto not in ORDINE_PASTI:
        return set()
    return set(ORDINE_PASTI[: ORDINE_PASTI.index(pasto) + 1])


def calcola_pasti_per_giorno(partecipante: Partecipante, db: Session = None) -> dict:
    """Calcola, giorno per giorno, quali pasti sono dovuti per un partecipante.

    Ritorna un dict {data: {"colazione": bool, "pranzo": bool, "cena": bool}}.
    "pasto_arrivo" e "pasto_partenza" sono estremi di un intervallo (non un
    singolo pasto isolato): se ad es. pasto_partenza = "pranzo", il
    partecipante resta per colazione E pranzo quel giorno, non solo il pranzo.
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
        # Stesso giorno: i pasti dovuti sono l'intersezione tra "da quale
        # pasto si è presenti" e "fino a quale pasto si resta".
        pasti_dovuti = _pasti_da(partecipante.pasto_arrivo) & _pasti_fino_a(partecipante.pasto_partenza)
        for pasto in pasti_dovuti:
            imposta(partecipante.data_arrivo, pasto)
        return risultato

    for pasto in _pasti_da(partecipante.pasto_arrivo):
        imposta(partecipante.data_arrivo, pasto)

    giorno = partecipante.data_arrivo + timedelta(days=1)
    while giorno < partecipante.data_partenza:
        imposta(giorno, "colazione")
        imposta(giorno, "pranzo")
        imposta(giorno, "cena")
        giorno += timedelta(days=1)

    for pasto in _pasti_fino_a(partecipante.pasto_partenza):
        imposta(partecipante.data_partenza, pasto)

    return risultato


def genera_report_pasti(db: Session, tipo_evento: str | None = None) -> list:
    """Genera il report giornaliero dei pasti per tutti i partecipanti attivi.

    Considera solo i partecipanti con stato_iscrizione diverso da 'Annullata'
    e con date di arrivo/partenza valorizzate. Se tipo_evento è valorizzato
    (precun/campo_famiglie/cun_fest/pranzo_cun), filtra solo i partecipanti
    iscritti a quell'evento (un partecipante può comparire in più filtri se
    ha selezionato più eventi).

    Il report copre sempre almeno l'intero periodo ufficiale dell'evento/i
    considerati (da periodi_evento, se configurato), anche oltre l'ultimo
    giorno con pasti effettivamente registrati: questo garantisce che
    l'ultimo giorno (tipicamente solo pranzo, senza cena) compaia sempre in
    tabella con 0 se non ci sono ancora iscrizioni fino a quella data.
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

    periodi = _mappa_periodi(db)
    tipi_considerati = [tipo_evento] if tipo_evento else list(COLONNA_EVENTO.keys())
    date_inizio_periodo = [periodi[t][0] for t in tipi_considerati if periodi.get(t) and periodi[t][0]]
    date_fine_periodo = [periodi[t][1] for t in tipi_considerati if periodi.get(t) and periodi[t][1]]

    candidati_min = list(date_inizio_periodo)
    candidati_max = list(date_fine_periodo)
    if conteggi:
        candidati_min.append(min(conteggi))
        candidati_max.append(max(conteggi))

    if not candidati_min or not candidati_max:
        return []

    giorno_min = min(candidati_min)
    giorno_max = max(candidati_max)

    report = []
    giorno = giorno_min
    while giorno <= giorno_max:
        dati = conteggi.get(giorno, {"colazioni": 0, "pranzi": 0, "cene": 0})
        report.append({"data": giorno, **dati})
        giorno += timedelta(days=1)

    return report


def conta_bosco_domenica(db: Session, tipo_evento: str | None = None) -> dict:
    """Conta i partecipanti attivi che hanno flaggato 'Vorrei dormire a Bosco
    la domenica sera', suddivisi in base a come intendono cenare la domenica
    (al ristorante / autonomamente / non ancora specificato).
    """
    query = db.query(Partecipante).filter(
        Partecipante.stato_iscrizione != "Annullata",
        Partecipante.flag_bosco_domenica.is_(True),
    )
    if tipo_evento:
        colonna = COLONNA_EVENTO.get(tipo_evento)
        if colonna is not None:
            query = query.filter(colonna.is_(True))
    partecipanti = query.all()

    ristorante = sum(1 for p in partecipanti if p.flag_cena_ristorante_domenica is True)
    autonoma = sum(1 for p in partecipanti if p.flag_cena_ristorante_domenica is False)
    non_specificato = sum(1 for p in partecipanti if p.flag_cena_ristorante_domenica is None)

    return {
        "totale": len(partecipanti),
        "ristorante": ristorante,
        "autonoma": autonoma,
        "non_specificato": non_specificato,
    }
