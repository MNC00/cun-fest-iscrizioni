from datetime import date, datetime, timedelta
import logging
import os
import uuid

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_current_operatore_is_admin,
    get_current_operatore_username,
    hash_password,
    verify_password,
)
from app.calcolo import (
    CalcoloPrezzoError,
    calcola_prezzo_partecipante,
    genera_report_pasti,
    conta_bosco_domenica,
    ottieni_periodo_evento,
)
from app.database import get_db
from app.email_service import (
    EmailServiceError,
    formatta_data_italiana,
    formatta_pasto,
    invia_aggiornamento_prezzo,
    invia_annullamento,
    invia_annullamento_nucleo,
    invia_comunicazione_massa,
    invia_conferma_iscrizione,
)
from app.models import (
    Famiglia,
    LogEvento,
    Operatore,
    Pagamento,
    Partecipante,
    PeriodoEvento,
    RicevutaPagamento,
    RicevutaPartecipante,
    Tariffa,
)
from app.pagamenti import sincronizza_pagamento
from app.schemas import IscrizioneFamigliaRequest
from app.storage_service import StorageServiceError, carica_file, elimina_file, scarica_file

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="CUN Fest Iscrizioni")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

TIPI_EVENTO_LABELS = {
    "precun": "PreCunFest",
    "campo_famiglie": "Campo Famiglie",
    "cun_fest": "CunFest",
    "pranzo_cun": "Solo pranzo CUN",
}
templates.env.globals["TIPI_EVENTO_LABELS"] = TIPI_EVENTO_LABELS

# Campo booleano di Partecipante corrispondente a ciascun valore del filtro
# "evento" usato nelle pagine operatore (dashboard, pagamenti, comunicazioni).
CAMPO_EVENTO = {
    "precun": "flag_precun",
    "campo_famiglie": "flag_campo_famiglie",
    "cun_fest": "flag_cun_fest",
    "pranzo_cun": "flag_solo_pranzo_cun",
}
templates.env.globals["CAMPO_EVENTO"] = CAMPO_EVENTO
# Usata da _nav.html per mostrare/nascondere il link "Configurazione" senza
# dover passare is_admin nel context di ogni singola route.
templates.env.globals["is_admin_operatore"] = get_current_operatore_is_admin

# Sul form pubblico il partecipante sceglie solo la zona di provenienza geografica
# (Nord/Centro/Sud): la fascia di prezzo effettiva (usata per il calcolo) ne è
# derivata automaticamente, così l'utente non deve conoscere la terminologia
# interna "Nord"/"Altro" come categoria tariffaria. Centro e Sud confluiscono
# nella stessa fascia ("Altro").
MAPPA_ZONA_FASCIA = {
    "Nord": "Nord",
    "Centro": "Altro",
    "Sud": "Altro",
}


def _deriva_fascia_da_zona(zona_provenienza: str | None, fascia_dichiarata: str) -> str:
    """Deriva la fascia di prezzo dalla zona di provenienza del partecipante.

    Se la zona non è tra quelle note (Nord/Centro/Sud) — es. iscrizioni via
    /modifica-iscrizione o estensioni che non passano dal form pubblico —
    mantiene la fascia dichiarata esplicitamente nella richiesta.
    """
    return MAPPA_ZONA_FASCIA.get(zona_provenienza, fascia_dichiarata)


def _periodi_evento_dict(db: Session) -> dict:
    """Ritorna {tipo_evento: {"min": iso|None, "max": iso|None}} per tutti gli
    eventi configurati in periodi_evento, usato dal form pubblico per
    restringere via JS le date in base agli eventi selezionati dall'utente."""
    righe = db.query(PeriodoEvento).all()
    return {
        riga.tipo_evento: {
            "min": riga.data_inizio.isoformat() if riga.data_inizio else None,
            "max": riga.data_fine.isoformat() if riga.data_fine else None,
        }
        for riga in righe
    }


def _richiedi_operatore_admin(request: Request) -> tuple[str | None, RedirectResponse | None]:
    """Verifica che l'operatore sia loggato e amministratore.

    Ritorna (username, None) se autorizzato, oppure (None, redirect_a_login)
    se non loggato. Solleva HTTPException 403 se loggato ma non amministratore.
    """
    username = get_current_operatore_username(request)
    if not username:
        return None, RedirectResponse(url="/login", status_code=303)
    if not get_current_operatore_is_admin(request):
        raise HTTPException(status_code=403, detail="Sezione riservata agli amministratori.")
    return username, None


def _ottieni_o_crea_token_ricevute(famiglia: Famiglia, db: Session) -> str:
    """Ritorna il token di accesso alla pagina pubblica di upload ricevute della
    famiglia, generandolo (e salvandolo) al primo utilizzo se non esiste ancora
    (es. famiglie create prima dell'introduzione di questa funzionalità)."""
    if not famiglia.token_ricevute:
        famiglia.token_ricevute = uuid.uuid4().hex
        db.add(famiglia)
        db.commit()
        db.refresh(famiglia)
    return famiglia.token_ricevute


def _contesto_email_partecipante(partecipante: Partecipante, db: Session) -> dict:
    """Costruisce il contesto per le email di conferma/aggiornamento prezzo di un partecipante."""
    base_url = os.getenv("BASE_URL", "").rstrip("/")
    link_annullamento = (
        f"{base_url}/annulla/{partecipante.token_annullamento}"
        if base_url and partecipante.token_annullamento
        else None
    )
    link_ricevute = (
        f"{base_url}/ricevute/{_ottieni_o_crea_token_ricevute(partecipante.famiglia, db)}"
        if base_url
        else None
    )
    return {
        "nome": partecipante.nome,
        "anno": (partecipante.data_arrivo or date.today()).year,
        "hasPrezzo": partecipante.prezzo_netto is not None,
        "isSoloPranzo": bool(partecipante.flag_solo_pranzo_cun),
        "dataArrivoFormattata": formatta_data_italiana(partecipante.data_arrivo),
        "pastoArrivo": formatta_pasto(partecipante.pasto_arrivo),
        "dataPartenzaFormattata": formatta_data_italiana(partecipante.data_partenza),
        "pastoPartenza": formatta_pasto(partecipante.pasto_partenza),
        "prezzo": float(partecipante.prezzo_netto) if partecipante.prezzo_netto is not None else None,
        "linkAnnullamento": link_annullamento,
        "linkRicevute": link_ricevute,
    }


@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={"title": "CUN Fest"},
    )


@app.get("/iscriviti")
def form_iscrizione(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="form_iscrizione.html",
        context={
            "title": "Iscrizione CUN Fest",
            "periodi_eventi": _periodi_evento_dict(db),
        },
    )


@app.get("/test-db-models")
def test_db_models(db: Session = Depends(get_db)):
    tariffe_count = db.query(Tariffa).count()
    return {"tariffe_count": tariffe_count, "status": "ok"}


@app.post("/iscriviti")
def iscriviti(payload: IscrizioneFamigliaRequest, db: Session = Depends(get_db)):
    try:
        for p in payload.partecipanti:
            if p.flag_solo_pranzo_cun:
                # Le date sono fisse e vengono impostate automaticamente al
                # momento del calcolo del prezzo: nessuna validazione qui.
                continue

            componenti = [
                evento
                for evento, attivo in (
                    ("precun", p.flag_precun),
                    ("campo_famiglie", p.flag_campo_famiglie),
                    ("cun_fest", p.flag_cun_fest),
                )
                if attivo
            ]
            data_min, data_max = ottieni_periodo_evento(db, componenti)
            if data_min and data_max:
                for etichetta, valore in (("arrivo", p.data_arrivo), ("partenza", p.data_partenza)):
                    if valore and (valore < data_min or valore > data_max):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"La data di {etichetta} di {p.nome} {p.cognome} "
                                f"({valore.strftime('%d/%m/%Y')}) è fuori dal periodo dell'evento "
                                f"({data_min.strftime('%d/%m/%Y')} - {data_max.strftime('%d/%m/%Y')})."
                            ),
                        )

        if payload.famiglia_esistente_email:
            famiglia = (
                db.query(Famiglia)
                .filter(func.lower(Famiglia.email) == payload.famiglia_esistente_email.lower())
                .first()
            )
            if not famiglia:
                raise HTTPException(
                    status_code=404,
                    detail="Nessun nucleo familiare trovato con questa email. Verifica di aver "
                    "inserito l'email usata nella prima iscrizione.",
                )
        else:
            famiglia = Famiglia(
                referente_nome=payload.referente.nome,
                referente_cognome=payload.referente.cognome,
                email=payload.referente.email,
                telefono=payload.referente.telefono,
                zona_provenienza=payload.referente.zona_provenienza,
            )
            db.add(famiglia)
            db.flush()  # ottiene famiglia.id prima del commit

        partecipanti_ids = []
        partecipanti_creati = []
        for p in payload.partecipanti:
            partecipante = Partecipante(
                famiglia_id=famiglia.id,
                nome=p.nome,
                cognome=p.cognome,
                data_nascita=p.data_nascita,
                luogo_nascita=p.luogo_nascita,
                zona_provenienza=p.zona_provenienza,
                data_arrivo=p.data_arrivo,
                data_partenza=p.data_partenza,
                pasto_arrivo=p.pasto_arrivo,
                pasto_partenza=p.pasto_partenza,
                flag_solo_pranzo_cun=p.flag_solo_pranzo_cun,
                flag_bosco_domenica=p.flag_bosco_domenica,
                flag_cena_ristorante_domenica=p.flag_cena_ristorante_domenica,
                flag_precun=p.flag_precun,
                flag_campo_famiglie=p.flag_campo_famiglie,
                flag_cun_fest=p.flag_cun_fest,
                note=p.note,
                fascia_prezzo=_deriva_fascia_da_zona(p.zona_provenienza, p.fascia_prezzo),
                token_annullamento=uuid.uuid4().hex,
            )
            db.add(partecipante)
            db.flush()
            sincronizza_pagamento(partecipante, db)
            partecipanti_ids.append(partecipante.id)
            partecipanti_creati.append(partecipante)


        db.commit()

        for partecipante in partecipanti_creati:
            try:
                invia_conferma_iscrizione(
                    email=famiglia.email,
                    contesto=_contesto_email_partecipante(partecipante, db),
                )
            except EmailServiceError as exc:
                logger.error(
                    "Invio email di conferma fallito per partecipante %s: %s", partecipante.id, exc
                )

        return {
            "status": "ok",
            "famiglia_id": famiglia.id,
            "partecipanti_ids": partecipanti_ids,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"title": "Login operatori", "errore": None},
    )


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip()
    operatore = db.query(Operatore).filter(Operatore.username == username).first()

    if not operatore or not operatore.attivo or not verify_password(password, operatore.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"title": "Login operatori", "errore": "Username o password non validi."},
            status_code=401,
        )

    token = create_session_token(operatore.username, is_admin=bool(operatore.is_admin))
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/dashboard")
def dashboard(
    request: Request,
    msg: str | None = None,
    evento: str = "tutti",
    db: Session = Depends(get_db),
):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    famiglie = (
        db.query(Famiglia)
        .options(joinedload(Famiglia.partecipanti))
        .order_by(Famiglia.id)
        .all()
    )

    # Statistiche: un nucleo familiare con un solo membro attivo è una "iscrizione
    # singola", non va conteggiato come famiglia nelle statistiche (nucleo = famiglia
    # con più di un partecipante attivo). Il filtro per evento (PreCunFest/Campo
    # Famiglie/solo CunFest) è per partecipante: una famiglia resta visibile se ha
    # almeno un partecipante del pacchetto selezionato.
    def _match_evento(p: Partecipante) -> bool:
        if evento == "tutti":
            return True
        campo = CAMPO_EVENTO.get(evento)
        return bool(campo and getattr(p, campo, False))

    attivi_per_famiglia = [
        [p for p in famiglia.partecipanti if p.stato_iscrizione != "Annullata" and _match_evento(p)]
        for famiglia in famiglie
    ]
    totale_partecipanti = sum(len(attivi) for attivi in attivi_per_famiglia)
    nuclei_familiari = sum(1 for attivi in attivi_per_famiglia if len(attivi) > 1)
    iscritti_singoli = sum(1 for attivi in attivi_per_famiglia if len(attivi) == 1)

    famiglie_filtrate = [
        famiglia
        for famiglia, attivi in zip(famiglie, attivi_per_famiglia)
        if evento == "tutti" or any(_match_evento(p) for p in famiglia.partecipanti)
    ]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Dashboard operatori",
            "username": username,
            "famiglie": famiglie_filtrate,
            "msg": msg,
            "totale_partecipanti": totale_partecipanti,
            "nuclei_familiari": nuclei_familiari,
            "iscritti_singoli": iscritti_singoli,
            "evento_corrente": evento,
        },
    )


def _invia_email_aggiornamento_prezzo(partecipante: Partecipante, dettagli_calcolo: dict, db: Session) -> None:
    """Invia al referente l'email con il prezzo appena (ri)calcolato per il partecipante.

    Chiamata solo a seguito di un'azione esplicita dell'operatore (ricalcolo o
    modifica iscrizione). Un eventuale errore di invio viene solo loggato,
    senza far fallire l'operazione di calcolo già commit-ata.
    """
    try:
        invia_aggiornamento_prezzo(
            email=partecipante.famiglia.email,
            contesto=_contesto_email_partecipante(partecipante, db),
        )
    except EmailServiceError as exc:
        logger.error(
            "Invio email di aggiornamento prezzo fallito per partecipante %s: %s",
            partecipante.id,
            exc,
        )


@app.post("/ricalcola-prezzo/{partecipante_id}")
def ricalcola_prezzo(partecipante_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    partecipante = (
        db.query(Partecipante)
        .options(joinedload(Partecipante.famiglia))
        .filter(Partecipante.id == partecipante_id)
        .first()
    )
    if not partecipante:
        raise HTTPException(status_code=404, detail="Partecipante non trovato.")

    try:
        dettagli_calcolo = calcola_prezzo_partecipante(partecipante, db)
        sincronizza_pagamento(partecipante, db)
        db.commit()
        msg = f"Prezzo ricalcolato per {partecipante.nome} {partecipante.cognome}."
        _invia_email_aggiornamento_prezzo(partecipante, dettagli_calcolo, db)
    except CalcoloPrezzoError as exc:
        db.rollback()
        msg = f"Errore nel calcolo: {exc}"

    return RedirectResponse(url=f"/dashboard?msg={msg}", status_code=303)


@app.post("/ricalcola-prezzi-mancanti")
def ricalcola_prezzi_mancanti(request: Request, db: Session = Depends(get_db)):
    """Ricalcola in un'unica azione tutti i partecipanti con prezzo non ancora calcolato.

    Utile quando la tabella tariffe viene popolata dopo che alcuni partecipanti
    si sono già iscritti: per ognuno di essi, se il calcolo va a buon fine,
    invia anche l'email di aggiornamento prezzo.
    """
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    partecipanti = (
        db.query(Partecipante)
        .options(joinedload(Partecipante.famiglia))
        .filter(
            Partecipante.prezzo_netto.is_(None),
            Partecipante.stato_iscrizione != "Annullata",
        )
        .all()
    )

    calcolati = 0
    falliti = 0
    for partecipante in partecipanti:
        try:
            dettagli_calcolo = calcola_prezzo_partecipante(partecipante, db)
            sincronizza_pagamento(partecipante, db)
            db.commit()
            calcolati += 1
            _invia_email_aggiornamento_prezzo(partecipante, dettagli_calcolo, db)
        except CalcoloPrezzoError:
            db.rollback()
            falliti += 1

    msg = f"Ricalcolati {calcolati} prezzi e inviate le relative email."
    if falliti:
        msg += f" {falliti} partecipanti non calcolabili (tariffa mancante)."

    return RedirectResponse(url=f"/dashboard?msg={msg}", status_code=303)


@app.get("/modifica-iscrizione/{partecipante_id}")
def modifica_iscrizione_form(
    partecipante_id: int, request: Request, db: Session = Depends(get_db)
):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    partecipante = (
        db.query(Partecipante)
        .options(joinedload(Partecipante.famiglia))
        .filter(Partecipante.id == partecipante_id)
        .first()
    )
    if not partecipante:
        raise HTTPException(status_code=404, detail="Partecipante non trovato.")

    return templates.TemplateResponse(
        request=request,
        name="modifica_iscrizione.html",
        context={
            "title": "Modifica iscrizione",
            "username": username,
            "partecipante": partecipante,
            "periodi_eventi": _periodi_evento_dict(db),
        },
    )


@app.post("/modifica-iscrizione/{partecipante_id}")
def modifica_iscrizione_submit(
    partecipante_id: int,
    request: Request,
    data_arrivo: date | None = Form(None),
    data_partenza: date | None = Form(None),
    pasto_arrivo: str = Form("nessuno"),
    pasto_partenza: str = Form("nessuno"),
    fascia_prezzo: str = Form(...),
    note: str = Form(""),
    flag_solo_pranzo_cun: str | None = Form(None),
    flag_precun: str | None = Form(None),
    flag_campo_famiglie: str | None = Form(None),
    flag_cun_fest: str | None = Form(None),
    flag_bosco_domenica: str | None = Form(None),
    flag_cena_ristorante_domenica: str | None = Form(None),
    db: Session = Depends(get_db),
):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    partecipante = (
        db.query(Partecipante)
        .options(joinedload(Partecipante.famiglia))
        .filter(Partecipante.id == partecipante_id)
        .first()
    )
    if not partecipante:
        raise HTTPException(status_code=404, detail="Partecipante non trovato.")

    e_solo_pranzo_cun = flag_solo_pranzo_cun == "true"
    e_precun = flag_precun is not None
    e_campo_famiglie = flag_campo_famiglie is not None
    e_cun_fest = flag_cun_fest is not None

    if e_solo_pranzo_cun and (e_precun or e_campo_famiglie or e_cun_fest):
        return RedirectResponse(
            url=(
                f"/modifica-iscrizione/{partecipante_id}?errore="
                "'Solo pranzo CUN' non può essere combinato con altri eventi."
            ),
            status_code=303,
        )
    if not e_solo_pranzo_cun and e_precun and e_campo_famiglie:
        return RedirectResponse(
            url=(
                f"/modifica-iscrizione/{partecipante_id}?errore="
                "PreCunFest e Campo Famiglie si svolgono in contemporanea: selezionane solo uno."
            ),
            status_code=303,
        )
    if not e_solo_pranzo_cun and not (e_precun or e_campo_famiglie or e_cun_fest):
        return RedirectResponse(
            url=(
                f"/modifica-iscrizione/{partecipante_id}?errore="
                "Seleziona almeno un evento oppure 'Solo pranzo CUN'."
            ),
            status_code=303,
        )

    if not e_solo_pranzo_cun:
        if not data_arrivo or not data_partenza:
            return RedirectResponse(
                url=(
                    f"/modifica-iscrizione/{partecipante_id}?errore="
                    "Data di arrivo e di partenza sono obbligatorie."
                ),
                status_code=303,
            )
        componenti = [
            evento
            for evento, attivo in (
                ("precun", e_precun),
                ("campo_famiglie", e_campo_famiglie),
                ("cun_fest", e_cun_fest),
            )
            if attivo
        ]
        data_min, data_max = ottieni_periodo_evento(db, componenti)
        if data_min and data_max:
            for etichetta, valore in (("arrivo", data_arrivo), ("partenza", data_partenza)):
                if valore < data_min or valore > data_max:
                    return RedirectResponse(
                        url=(
                            f"/modifica-iscrizione/{partecipante_id}?errore="
                            f"Data di {etichetta} fuori dal periodo dell'evento "
                            f"({data_min.strftime('%d/%m/%Y')} - {data_max.strftime('%d/%m/%Y')})."
                        ),
                        status_code=303,
                    )

    valori_precedenti = {
        "data_arrivo": partecipante.data_arrivo.isoformat() if partecipante.data_arrivo else None,
        "data_partenza": partecipante.data_partenza.isoformat() if partecipante.data_partenza else None,
        "pasto_arrivo": partecipante.pasto_arrivo,
        "pasto_partenza": partecipante.pasto_partenza,
        "flag_solo_pranzo_cun": partecipante.flag_solo_pranzo_cun,
        "flag_precun": partecipante.flag_precun,
        "flag_campo_famiglie": partecipante.flag_campo_famiglie,
        "flag_cun_fest": partecipante.flag_cun_fest,
        "flag_bosco_domenica": partecipante.flag_bosco_domenica,
        "fascia_prezzo": partecipante.fascia_prezzo,
    }

    partecipante.flag_solo_pranzo_cun = e_solo_pranzo_cun
    partecipante.flag_precun = e_precun
    partecipante.flag_campo_famiglie = e_campo_famiglie
    partecipante.flag_cun_fest = e_cun_fest

    if e_solo_pranzo_cun:
        # Le date vengono impostate automaticamente dal calcolo del prezzo
        # in base a periodi_evento; qui azzeriamo eventuali date residue.
        partecipante.data_arrivo = None
        partecipante.data_partenza = None
        partecipante.pasto_arrivo = None
        partecipante.pasto_partenza = None
        partecipante.flag_bosco_domenica = False
        partecipante.flag_cena_ristorante_domenica = None
    else:
        partecipante.data_arrivo = data_arrivo
        partecipante.data_partenza = data_partenza
        partecipante.pasto_arrivo = pasto_arrivo
        partecipante.pasto_partenza = pasto_partenza
        partecipante.flag_bosco_domenica = flag_bosco_domenica is not None
        partecipante.flag_cena_ristorante_domenica = (
            (flag_cena_ristorante_domenica == "true") if partecipante.flag_bosco_domenica else None
        )

    partecipante.fascia_prezzo = fascia_prezzo
    partecipante.note = note or None

    try:
        dettagli_calcolo = calcola_prezzo_partecipante(partecipante, db)
        sincronizza_pagamento(partecipante, db)
    except CalcoloPrezzoError as exc:
        db.rollback()
        return RedirectResponse(
            url=f"/modifica-iscrizione/{partecipante_id}?errore={exc}", status_code=303
        )

    valori_nuovi = {
        "data_arrivo": partecipante.data_arrivo.isoformat() if partecipante.data_arrivo else None,
        "data_partenza": partecipante.data_partenza.isoformat() if partecipante.data_partenza else None,
        "pasto_arrivo": partecipante.pasto_arrivo,
        "pasto_partenza": partecipante.pasto_partenza,
        "flag_solo_pranzo_cun": partecipante.flag_solo_pranzo_cun,
        "flag_precun": partecipante.flag_precun,
        "flag_campo_famiglie": partecipante.flag_campo_famiglie,
        "flag_cun_fest": partecipante.flag_cun_fest,
        "flag_bosco_domenica": partecipante.flag_bosco_domenica,
        "fascia_prezzo": partecipante.fascia_prezzo,
    }

    log = LogEvento(
        oggetto_tipo="partecipante",
        oggetto_id=partecipante.id,
        azione="iscrizione_modificata",
        operatore=username,
        dettagli={"prima": valori_precedenti, "dopo": valori_nuovi},
    )
    db.add(log)
    db.commit()

    _invia_email_aggiornamento_prezzo(partecipante, dettagli_calcolo, db)

    return RedirectResponse(url="/dashboard?ok=1", status_code=303)


def _e_referente(partecipante: Partecipante, famiglia: Famiglia) -> bool:
    """True se il partecipante è il referente/responsabile registrato per la sua famiglia."""
    return (
        partecipante.nome.strip().lower() == (famiglia.referente_nome or "").strip().lower()
        and partecipante.cognome.strip().lower() == (famiglia.referente_cognome or "").strip().lower()
    )


def _esegui_annullamento(
    db: Session,
    partecipante: Partecipante,
    famiglia: Famiglia,
    azione: str,
    operatore_label: str,
    nuovo_referente_nome: str = "",
    nuovo_referente_cognome: str = "",
    nuovo_referente_email: str = "",
    nuovo_referente_telefono: str = "",
) -> tuple[bool, str | None]:
    """Esegue l'annullamento (singola o nucleo) di un'iscrizione, logga l'evento e
    invia la relativa email. Condivisa tra il flusso self-service e quello operatore.

    L'annullamento dell'intero nucleo e la riassegnazione del referente sono
    consentiti solo se il partecipante che avvia l'operazione è il referente
    stesso del nucleo: un membro qualsiasi può annullare solo se stesso.

    Ritorna (ok, messaggio_errore). Se ok è False la transazione non è stata modificata.
    """
    if azione == "nucleo":
        if not _e_referente(partecipante, famiglia):
            return False, "Solo il referente del nucleo familiare può annullare l'intera iscrizione del nucleo."

        attivi = [p for p in famiglia.partecipanti if p.stato_iscrizione != "Annullata"]
        nomi_annullati = []
        for p in attivi:
            p.stato_iscrizione = "Annullata"
            nomi_annullati.append(f"{p.nome} {p.cognome}")
            db.add(
                LogEvento(
                    oggetto_tipo="partecipante",
                    oggetto_id=p.id,
                    azione="iscrizione_annullata",
                    operatore=operatore_label,
                    dettagli={"modalita": "nucleo", "famiglia_id": famiglia.id},
                )
            )
        db.commit()

        if nomi_annullati:
            try:
                invia_annullamento_nucleo(email=famiglia.email, nomi=nomi_annullati)
            except EmailServiceError as exc:
                logger.error("Invio email annullamento nucleo fallito per famiglia %s: %s", famiglia.id, exc)
        return True, None

    if azione == "singola":
        altri_attivi = [
            p for p in famiglia.partecipanti if p.id != partecipante.id and p.stato_iscrizione != "Annullata"
        ]
        richiede_riassegnazione = altri_attivi and _e_referente(partecipante, famiglia)

        if richiede_riassegnazione and not (nuovo_referente_nome and nuovo_referente_cognome and nuovo_referente_email):
            return False, (
                "Dato che restano altri iscritti nel nucleo, indica nome, cognome ed email del "
                "nuovo referente per il nucleo familiare."
            )

        partecipante.stato_iscrizione = "Annullata"
        db.add(
            LogEvento(
                oggetto_tipo="partecipante",
                oggetto_id=partecipante.id,
                azione="iscrizione_annullata",
                operatore=operatore_label,
                dettagli={"modalita": "singola", "famiglia_id": famiglia.id},
            )
        )

        if richiede_riassegnazione:
            famiglia.referente_nome = nuovo_referente_nome
            famiglia.referente_cognome = nuovo_referente_cognome
            famiglia.email = nuovo_referente_email
            famiglia.telefono = nuovo_referente_telefono or famiglia.telefono

        db.commit()

        try:
            invia_annullamento(email=famiglia.email, nome=partecipante.nome)
        except EmailServiceError as exc:
            logger.error(
                "Invio email annullamento singola fallito per partecipante %s: %s",
                partecipante.id,
                exc,
            )
        return True, None

    return False, "Azione non riconosciuta."


@app.get("/dashboard/annulla/{partecipante_id}")
def annulla_iscrizione_operatore_form(partecipante_id: int, request: Request, db: Session = Depends(get_db)):
    """Pagina operatore per annullare un'iscrizione: singola (con eventuale riassegnazione
    del referente) oppure l'intero nucleo familiare."""
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    partecipante = (
        db.query(Partecipante)
        .options(joinedload(Partecipante.famiglia).joinedload(Famiglia.partecipanti))
        .filter(Partecipante.id == partecipante_id)
        .first()
    )
    if not partecipante:
        raise HTTPException(status_code=404, detail="Partecipante non trovato.")

    if partecipante.stato_iscrizione == "Annullata":
        return templates.TemplateResponse(
            request=request,
            name="annulla_self_service.html",
            context={
                "title": "Annulla iscrizione",
                "partecipante": partecipante,
                "altri_partecipanti": [],
                "gia_annullata": True,
                "is_operatore": True,
            },
        )

    altri_partecipanti = [
        p
        for p in partecipante.famiglia.partecipanti
        if p.id != partecipante.id and p.stato_iscrizione != "Annullata"
    ]

    return templates.TemplateResponse(
        request=request,
        name="annulla_self_service.html",
        context={
            "title": "Annulla iscrizione",
            "partecipante": partecipante,
            "altri_partecipanti": altri_partecipanti,
            "gia_annullata": False,
            "is_operatore": True,
            "is_referente": _e_referente(partecipante, partecipante.famiglia),
        },
    )


@app.post("/dashboard/annulla/{partecipante_id}")
def annulla_iscrizione_operatore_submit(
    partecipante_id: int,
    request: Request,
    azione: str = Form(...),
    nuovo_referente_nome: str = Form(""),
    nuovo_referente_cognome: str = Form(""),
    nuovo_referente_email: str = Form(""),
    nuovo_referente_telefono: str = Form(""),
    db: Session = Depends(get_db),
):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    partecipante = (
        db.query(Partecipante)
        .options(joinedload(Partecipante.famiglia).joinedload(Famiglia.partecipanti))
        .filter(Partecipante.id == partecipante_id)
        .first()
    )
    if not partecipante:
        raise HTTPException(status_code=404, detail="Partecipante non trovato.")

    famiglia = partecipante.famiglia
    ok, errore = _esegui_annullamento(
        db,
        partecipante,
        famiglia,
        azione,
        operatore_label=username,
        nuovo_referente_nome=nuovo_referente_nome,
        nuovo_referente_cognome=nuovo_referente_cognome,
        nuovo_referente_email=nuovo_referente_email,
        nuovo_referente_telefono=nuovo_referente_telefono,
    )

    if not ok:
        altri_partecipanti = [
            p
            for p in famiglia.partecipanti
            if p.id != partecipante.id and p.stato_iscrizione != "Annullata"
        ]
        return templates.TemplateResponse(
            request=request,
            name="annulla_self_service.html",
            context={
                "title": "Annulla iscrizione",
                "partecipante": partecipante,
                "altri_partecipanti": altri_partecipanti,
                "gia_annullata": False,
                "is_operatore": True,
                "is_referente": _e_referente(partecipante, famiglia),
                "errore": errore,
            },
            status_code=400,
        )

    return RedirectResponse(url="/dashboard?msg=Iscrizione+annullata+con+successo.", status_code=303)


@app.get("/annulla/{token}")
def annulla_self_service_form(token: str, request: Request, db: Session = Depends(get_db)):
    """Pagina pubblica (nessun login) che permette al partecipante di annullare la propria
    iscrizione, singolarmente o insieme a tutto il nucleo familiare."""
    partecipante = (
        db.query(Partecipante)
        .options(joinedload(Partecipante.famiglia).joinedload(Famiglia.partecipanti))
        .filter(Partecipante.token_annullamento == token)
        .first()
    )
    if not partecipante:
        raise HTTPException(status_code=404, detail="Link di annullamento non valido.")

    if partecipante.stato_iscrizione == "Annullata":
        return templates.TemplateResponse(
            request=request,
            name="annulla_self_service.html",
            context={
                "title": "Annulla iscrizione",
                "partecipante": partecipante,
                "altri_partecipanti": [],
                "gia_annullata": True,
            },
        )

    altri_partecipanti = [
        p
        for p in partecipante.famiglia.partecipanti
        if p.id != partecipante.id and p.stato_iscrizione != "Annullata"
    ]

    return templates.TemplateResponse(
        request=request,
        name="annulla_self_service.html",
        context={
            "title": "Annulla iscrizione",
            "partecipante": partecipante,
            "altri_partecipanti": altri_partecipanti,
            "gia_annullata": False,
            "is_referente": _e_referente(partecipante, partecipante.famiglia),
        },
    )


@app.post("/annulla/{token}")
def annulla_self_service_submit(
    token: str,
    request: Request,
    azione: str = Form(...),
    nuovo_referente_nome: str = Form(""),
    nuovo_referente_cognome: str = Form(""),
    nuovo_referente_email: str = Form(""),
    nuovo_referente_telefono: str = Form(""),
    db: Session = Depends(get_db),
):
    partecipante = (
        db.query(Partecipante)
        .options(joinedload(Partecipante.famiglia).joinedload(Famiglia.partecipanti))
        .filter(Partecipante.token_annullamento == token)
        .first()
    )
    if not partecipante:
        raise HTTPException(status_code=404, detail="Link di annullamento non valido.")

    famiglia = partecipante.famiglia
    ok, messaggio_errore = _esegui_annullamento(
        db,
        partecipante,
        famiglia,
        azione,
        operatore_label="self-service",
        nuovo_referente_nome=nuovo_referente_nome,
        nuovo_referente_cognome=nuovo_referente_cognome,
        nuovo_referente_email=nuovo_referente_email,
        nuovo_referente_telefono=nuovo_referente_telefono,
    )

    if not ok:
        altri_partecipanti = [
            p
            for p in famiglia.partecipanti
            if p.id != partecipante.id and p.stato_iscrizione != "Annullata"
        ]
        return templates.TemplateResponse(
            request=request,
            name="annulla_self_service.html",
            context={
                "title": "Annulla iscrizione",
                "partecipante": partecipante,
                "altri_partecipanti": altri_partecipanti,
                "gia_annullata": False,
                "is_referente": _e_referente(partecipante, famiglia),
                "errore": messaggio_errore,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        request=request,
        name="annulla_self_service.html",
        context={
            "title": "Annulla iscrizione",
            "partecipante": partecipante,
            "altri_partecipanti": [],
            "gia_annullata": True,
            "esito_ok": True,
        },
    )


@app.get("/pagamenti")
def pagamenti_lista(
    request: Request,
    stato: str = "tutti",
    evento: str = "tutti",
    db: Session = Depends(get_db),
):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    query = (
        db.query(Pagamento)
        .join(Partecipante)
        .join(Famiglia)
        .options(
            joinedload(Pagamento.partecipante).joinedload(Partecipante.famiglia)
        )
    )

    if stato == "non_pagati":
        query = query.filter(Pagamento.stato.in_(["Non_pagato", "Parzialmente_pagato"]))
    elif stato == "pagati":
        query = query.filter(Pagamento.stato == "Pagato")

    if evento != "tutti":
        campo = CAMPO_EVENTO.get(evento)
        if campo:
            query = query.filter(getattr(Partecipante, campo).is_(True))

    pagamenti = query.order_by(Pagamento.id).all()

    ricevute_per_partecipante: dict[int, list] = {}
    partecipante_ids = [p.partecipante_id for p in pagamenti]
    if partecipante_ids:
        righe = (
            db.query(RicevutaPartecipante.partecipante_id, RicevutaPagamento)
            .join(RicevutaPagamento, RicevutaPartecipante.ricevuta_id == RicevutaPagamento.id)
            .filter(RicevutaPartecipante.partecipante_id.in_(partecipante_ids))
            .order_by(RicevutaPagamento.created_at)
            .all()
        )
        for partecipante_id, ricevuta in righe:
            ricevute_per_partecipante.setdefault(partecipante_id, []).append(ricevuta)

    return templates.TemplateResponse(
        request=request,
        name="pagamenti.html",
        context={
            "title": "Pagamenti",
            "username": username,
            "pagamenti": pagamenti,
            "stato_filtro": stato,
            "evento_corrente": evento,
            "ricevute_per_partecipante": ricevute_per_partecipante,
        },
    )


@app.post("/pagamenti/segna-pagato/{pagamento_id}")
def segna_pagamento_pagato(
    pagamento_id: int,
    request: Request,
    metodo: str = Form(...),
    data_pagamento: date = Form(default_factory=date.today),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    pagamento = db.query(Pagamento).filter(Pagamento.id == pagamento_id).first()
    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento non trovato.")

    pagamento.importo_pagato = pagamento.importo_dovuto
    pagamento.stato = "Pagato"
    pagamento.data_pagamento = data_pagamento
    pagamento.metodo = metodo
    pagamento.note = note or None

    log = LogEvento(
        oggetto_tipo="pagamento",
        oggetto_id=pagamento.id,
        azione="pagamento_registrato",
        operatore=username,
        dettagli={
            "partecipante_id": pagamento.partecipante_id,
            "importo_pagato": float(pagamento.importo_pagato or 0),
            "metodo": metodo,
        },
    )
    db.add(log)
    db.commit()

    return RedirectResponse(url="/pagamenti?ok=1", status_code=303)


def _estensione_consentita(nome_file: str) -> str | None:
    """Ritorna l'estensione (in minuscolo, con punto) se è tra quelle ammesse per le ricevute, altrimenti None."""
    estensione = os.path.splitext(nome_file)[1].lower()
    return estensione if estensione in {".pdf", ".jpg", ".jpeg", ".png"} else None


CONTENT_TYPE_PER_ESTENSIONE = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

DIMENSIONE_MASSIMA_RICEVUTA_BYTES = 8 * 1024 * 1024  # 8 MB


@app.get("/pagamenti/ricevute/{ricevuta_id}/scarica")
def scarica_ricevuta(ricevuta_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    ricevuta = db.query(RicevutaPagamento).filter(RicevutaPagamento.id == ricevuta_id).first()
    if not ricevuta:
        raise HTTPException(status_code=404, detail="Ricevuta non trovata.")

    try:
        contenuto, content_type = scarica_file(ricevuta.storage_path)
    except StorageServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(
        content=contenuto,
        media_type=ricevuta.content_type or content_type,
        headers={"Content-Disposition": f'inline; filename="{ricevuta.nome_file_originale}"'},
    )


@app.post("/pagamenti/ricevute/{ricevuta_id}/verifica")
def verifica_ricevuta(ricevuta_id: int, request: Request, db: Session = Depends(get_db)):
    """Segna/rimuove la verifica manuale di una ricevuta. Il controllo che il
    bonifico corrisponda davvero all'importo dovuto resta sempre a carico
    dell'operatore: qui si registra solo l'esito di quel controllo."""
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    ricevuta = db.query(RicevutaPagamento).filter(RicevutaPagamento.id == ricevuta_id).first()
    if not ricevuta:
        raise HTTPException(status_code=404, detail="Ricevuta non trovata.")

    ricevuta.verificata = not ricevuta.verificata
    ricevuta.verificata_da = username if ricevuta.verificata else None
    ricevuta.verificata_il = datetime.now() if ricevuta.verificata else None

    db.add(
        LogEvento(
            oggetto_tipo="ricevuta_pagamento",
            oggetto_id=ricevuta.id,
            azione="ricevuta_verificata" if ricevuta.verificata else "ricevuta_verifica_rimossa",
            operatore=username,
            dettagli={"famiglia_id": ricevuta.famiglia_id, "nome_file": ricevuta.nome_file_originale},
        )
    )
    db.commit()

    return RedirectResponse(url="/pagamenti?ok=1", status_code=303)


@app.post("/pagamenti/ricevute/{ricevuta_id}/elimina")
def elimina_ricevuta(ricevuta_id: int, request: Request, db: Session = Depends(get_db)):
    """Elimina una ricevuta caricata per errore/duplicata (es. file sbagliato)."""
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    ricevuta = db.query(RicevutaPagamento).filter(RicevutaPagamento.id == ricevuta_id).first()
    if not ricevuta:
        raise HTTPException(status_code=404, detail="Ricevuta non trovata.")

    try:
        elimina_file(ricevuta.storage_path)
    except StorageServiceError as exc:
        logger.error("Eliminazione file su Supabase Storage fallita per ricevuta %s: %s", ricevuta.id, exc)

    db.add(
        LogEvento(
            oggetto_tipo="ricevuta_pagamento",
            oggetto_id=ricevuta.id,
            azione="ricevuta_eliminata",
            operatore=username,
            dettagli={"famiglia_id": ricevuta.famiglia_id, "nome_file": ricevuta.nome_file_originale},
        )
    )
    db.delete(ricevuta)
    db.commit()

    return RedirectResponse(url="/pagamenti?ok=1", status_code=303)


@app.get("/ricevute/{token}")
def ricevute_pagina(token: str, request: Request, db: Session = Depends(get_db)):
    famiglia = db.query(Famiglia).filter(Famiglia.token_ricevute == token).first()
    if not famiglia:
        raise HTTPException(status_code=404, detail="Link non valido.")

    partecipanti = (
        db.query(Partecipante)
        .filter(Partecipante.famiglia_id == famiglia.id, Partecipante.stato_iscrizione != "Annullata")
        .order_by(Partecipante.id)
        .all()
    )
    ricevute = (
        db.query(RicevutaPagamento)
        .options(joinedload(RicevutaPagamento.partecipanti_coperti).joinedload(RicevutaPartecipante.partecipante))
        .filter(RicevutaPagamento.famiglia_id == famiglia.id)
        .order_by(RicevutaPagamento.created_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="ricevute_pagamento.html",
        context={
            "title": "Carica ricevuta di pagamento",
            "famiglia": famiglia,
            "partecipanti": partecipanti,
            "ricevute": ricevute,
            "token": token,
        },
    )


@app.post("/ricevute/{token}")
async def ricevute_upload(
    token: str,
    request: Request,
    partecipante_ids: list[int] = Form([]),
    note: str = Form(""),
    file: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    famiglia = db.query(Famiglia).filter(Famiglia.token_ricevute == token).first()
    if not famiglia:
        raise HTTPException(status_code=404, detail="Link non valido.")

    partecipanti_validi_ids = {
        p.id
        for p in db.query(Partecipante.id).filter(Partecipante.famiglia_id == famiglia.id).all()
    }
    selezionati = [pid for pid in partecipante_ids if pid in partecipanti_validi_ids]
    if not selezionati:
        return RedirectResponse(
            url=f"/ricevute/{token}?errore=Seleziona almeno un partecipante coperto da questa ricevuta.",
            status_code=303,
        )

    file_validi = [f for f in file if f.filename]
    if not file_validi:
        return RedirectResponse(
            url=f"/ricevute/{token}?errore=Seleziona almeno un file da caricare.", status_code=303
        )

    for upload in file_validi:
        estensione = _estensione_consentita(upload.filename)
        if not estensione:
            return RedirectResponse(
                url=f"/ricevute/{token}?errore=Formato di '{upload.filename}' non supportato "
                "(sono ammessi solo PDF, JPG e PNG).",
                status_code=303,
            )

        contenuto = await upload.read()
        if len(contenuto) > DIMENSIONE_MASSIMA_RICEVUTA_BYTES:
            return RedirectResponse(
                url=f"/ricevute/{token}?errore='{upload.filename}' supera la dimensione massima consentita (8 MB).",
                status_code=303,
            )

        storage_path = f"famiglia_{famiglia.id}/{uuid.uuid4().hex}{estensione}"
        content_type = CONTENT_TYPE_PER_ESTENSIONE.get(estensione, "application/octet-stream")

        try:
            carica_file(storage_path, contenuto, content_type)
        except StorageServiceError as exc:
            logger.error("Upload ricevuta fallito per famiglia %s: %s", famiglia.id, exc)
            return RedirectResponse(
                url=f"/ricevute/{token}?errore=Caricamento fallito, riprova tra qualche minuto "
                "o scrivici rispondendo all'email di conferma iscrizione.",
                status_code=303,
            )

        ricevuta = RicevutaPagamento(
            famiglia_id=famiglia.id,
            nome_file_originale=upload.filename,
            storage_path=storage_path,
            content_type=content_type,
            dimensione_bytes=len(contenuto),
            note=note or None,
        )
        db.add(ricevuta)
        db.flush()

        for partecipante_id in selezionati:
            db.add(RicevutaPartecipante(ricevuta_id=ricevuta.id, partecipante_id=partecipante_id))

    db.commit()

    return RedirectResponse(url=f"/ricevute/{token}?ok=1", status_code=303)



def _query_destinatari(db: Session, fascia: str, stato_iscrizione: str, tipo_evento: str = ""):
    """Costruisce la query dei partecipanti destinatari in base ai filtri di comunicazione."""
    query = db.query(Partecipante).join(Famiglia)
    if fascia:
        query = query.filter(Partecipante.fascia_prezzo == fascia)
    if stato_iscrizione:
        query = query.filter(Partecipante.stato_iscrizione == stato_iscrizione)
    if tipo_evento:
        campo = CAMPO_EVENTO.get(tipo_evento)
        if campo:
            query = query.filter(getattr(Partecipante, campo).is_(True))
    return query


@app.get("/comunicazioni")
def comunicazioni_form(request: Request, db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    numero_destinatari = _query_destinatari(db, "", "", "").count()

    return templates.TemplateResponse(
        request=request,
        name="comunicazioni.html",
        context={
            "title": "Comunicazioni",
            "username": username,
            "filtri": {"fascia": "", "stato_iscrizione": "", "tipo_evento": ""},
            "numero_destinatari": numero_destinatari,
            "oggetto": "",
            "testo_libero": "",
            "risultato": None,
        },
    )


@app.post("/comunicazioni")
def comunicazioni_submit(
    request: Request,
    azione: str = Form(...),
    fascia: str = Form(""),
    stato_iscrizione: str = Form(""),
    tipo_evento: str = Form(""),
    oggetto: str = Form(""),
    testo_libero: str = Form(""),
    db: Session = Depends(get_db),
):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    filtri = {
        "fascia": fascia,
        "stato_iscrizione": stato_iscrizione,
        "tipo_evento": tipo_evento,
    }

    destinatari = _query_destinatari(db, fascia, stato_iscrizione, tipo_evento).all()
    risultato = None

    if azione == "invia":
        inviate = 0
        fallite = 0
        for partecipante in destinatari:
            try:
                invia_comunicazione_massa(
                    email=partecipante.famiglia.email,
                    nome=partecipante.nome,
                    oggetto=oggetto,
                    testo_libero=testo_libero,
                )
                log = LogEvento(
                    oggetto_tipo="partecipante",
                    oggetto_id=partecipante.id,
                    azione="email_massiva_inviata",
                    operatore=username,
                    dettagli={"partecipante_id": partecipante.id, "oggetto": oggetto},
                )
                db.add(log)
                inviate += 1
            except EmailServiceError:
                fallite += 1
        db.commit()
        risultato = f"Inviato a {inviate} destinatari" + (f" ({fallite} falliti)" if fallite else ".")

    return templates.TemplateResponse(
        request=request,
        name="comunicazioni.html",
        context={
            "title": "Comunicazioni",
            "username": username,
            "filtri": filtri,
            "numero_destinatari": len(destinatari),
            "oggetto": oggetto,
            "testo_libero": testo_libero,
            "risultato": risultato,
        },
    )


@app.get("/report-pasti")
def report_pasti_pagina(request: Request, evento: str = "tutti", db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    righe = genera_report_pasti(db, tipo_evento=None if evento == "tutti" else evento)

    bosco_domenica = None
    if evento in ("tutti", "cun_fest"):
        bosco_domenica = conta_bosco_domenica(db, tipo_evento=None if evento == "tutti" else evento)

    return templates.TemplateResponse(
        request=request,
        name="report_pasti.html",
        context={
            "title": "Report pasti",
            "username": username,
            "righe": righe,
            "evento_corrente": evento,
            "bosco_domenica": bosco_domenica,
        },
    )


@app.get("/report-pasti/csv")
def report_pasti_csv(request: Request, evento: str = "tutti", db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    righe = genera_report_pasti(db, tipo_evento=None if evento == "tutti" else evento)

    def genera_righe_csv():
        yield "data,colazioni,pranzi,cene\n"
        for riga in righe:
            yield f"{riga['data'].isoformat()},{riga['colazioni']},{riga['pranzi']},{riga['cene']}\n"

    return StreamingResponse(
        genera_righe_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=report_pasti.csv"},
    )


def _parse_float_opt(valore: str | None) -> float | None:
    """Converte una stringa di form in float, o None se vuota/assente."""
    if valore is None or valore.strip() == "":
        return None
    return float(valore.replace(",", "."))


FASCE_TARIFFA = ["Nord", "Altro"]


@app.get("/configurazione")
def configurazione_pagina(
    request: Request, sezione: str = "periodi", db: Session = Depends(get_db)
):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    periodi = {r.tipo_evento: r for r in db.query(PeriodoEvento).all()}
    tariffe = db.query(Tariffa).order_by(Tariffa.tipo_evento, Tariffa.fascia).all()
    operatori = db.query(Operatore).order_by(Operatore.username).all()

    return templates.TemplateResponse(
        request=request,
        name="configurazione.html",
        context={
            "title": "Configurazione",
            "username": username,
            "sezione": sezione,
            "periodi": periodi,
            "tariffe": tariffe,
            "operatori": operatori,
            "fasce_tariffa": FASCE_TARIFFA,
        },
    )


@app.post("/configurazione/periodi/{tipo_evento}")
def configurazione_aggiorna_periodo(
    tipo_evento: str,
    request: Request,
    data_inizio: date | None = Form(None),
    data_fine: date | None = Form(None),
    db: Session = Depends(get_db),
):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    periodo = db.query(PeriodoEvento).filter(PeriodoEvento.tipo_evento == tipo_evento).first()
    if not periodo:
        raise HTTPException(status_code=404, detail="Periodo evento non trovato.")

    valori_precedenti = {
        "data_inizio": periodo.data_inizio.isoformat() if periodo.data_inizio else None,
        "data_fine": periodo.data_fine.isoformat() if periodo.data_fine else None,
    }
    periodo.data_inizio = data_inizio
    periodo.data_fine = data_fine

    db.add(
        LogEvento(
            oggetto_tipo="periodo_evento",
            oggetto_id=periodo.id,
            azione="periodo_modificato",
            operatore=username,
            dettagli={
                "tipo_evento": tipo_evento,
                "prima": valori_precedenti,
                "dopo": {
                    "data_inizio": data_inizio.isoformat() if data_inizio else None,
                    "data_fine": data_fine.isoformat() if data_fine else None,
                },
            },
        )
    )
    db.commit()

    return RedirectResponse(url="/configurazione?sezione=periodi&ok=1", status_code=303)


@app.post("/configurazione/tariffe/nuova")
def configurazione_crea_tariffa(
    request: Request,
    tipo_evento: str = Form(...),
    fascia: str = Form(""),
    prezzo_notte: str = Form(""),
    prezzo_colazione: str = Form(""),
    prezzo_pranzo: str = Form(""),
    prezzo_cena: str = Form(""),
    tetto_spesa_fascia: str = Form(""),
    sconto_giovani_percentuale: str = Form(""),
    attivo: str | None = Form(None),
    db: Session = Depends(get_db),
):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    tariffa = Tariffa(
        tipo_evento=tipo_evento,
        fascia=fascia or None,
        prezzo_notte=_parse_float_opt(prezzo_notte),
        prezzo_colazione=_parse_float_opt(prezzo_colazione),
        prezzo_pranzo=_parse_float_opt(prezzo_pranzo),
        prezzo_cena=_parse_float_opt(prezzo_cena),
        tetto_spesa_fascia=_parse_float_opt(tetto_spesa_fascia),
        sconto_giovani_percentuale=_parse_float_opt(sconto_giovani_percentuale),
        attivo=attivo is not None,
    )
    db.add(tariffa)
    db.flush()

    db.add(
        LogEvento(
            oggetto_tipo="tariffa",
            oggetto_id=tariffa.id,
            azione="tariffa_creata",
            operatore=username,
            dettagli={
                "tipo_evento": tariffa.tipo_evento,
                "fascia": tariffa.fascia,
                "prezzo_notte": tariffa.prezzo_notte,
                "prezzo_colazione": tariffa.prezzo_colazione,
                "prezzo_pranzo": tariffa.prezzo_pranzo,
                "prezzo_cena": tariffa.prezzo_cena,
                "tetto_spesa_fascia": tariffa.tetto_spesa_fascia,
                "sconto_giovani_percentuale": tariffa.sconto_giovani_percentuale,
                "attivo": tariffa.attivo,
            },
        )
    )
    db.commit()

    return RedirectResponse(url="/configurazione?sezione=tariffe&ok=1", status_code=303)


@app.post("/configurazione/tariffe/{tariffa_id}")
def configurazione_aggiorna_tariffa(
    tariffa_id: int,
    request: Request,
    prezzo_notte: str = Form(""),
    prezzo_colazione: str = Form(""),
    prezzo_pranzo: str = Form(""),
    prezzo_cena: str = Form(""),
    tetto_spesa_fascia: str = Form(""),
    sconto_giovani_percentuale: str = Form(""),
    attivo: str | None = Form(None),
    db: Session = Depends(get_db),
):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    tariffa = db.query(Tariffa).filter(Tariffa.id == tariffa_id).first()
    if not tariffa:
        raise HTTPException(status_code=404, detail="Tariffa non trovata.")

    def _snapshot(t: Tariffa) -> dict:
        return {
            "prezzo_notte": float(t.prezzo_notte) if t.prezzo_notte is not None else None,
            "prezzo_colazione": float(t.prezzo_colazione) if t.prezzo_colazione is not None else None,
            "prezzo_pranzo": float(t.prezzo_pranzo) if t.prezzo_pranzo is not None else None,
            "prezzo_cena": float(t.prezzo_cena) if t.prezzo_cena is not None else None,
            "tetto_spesa_fascia": float(t.tetto_spesa_fascia) if t.tetto_spesa_fascia is not None else None,
            "sconto_giovani_percentuale": float(t.sconto_giovani_percentuale) if t.sconto_giovani_percentuale is not None else None,
            "attivo": t.attivo,
        }

    valori_precedenti = _snapshot(tariffa)

    tariffa.prezzo_notte = _parse_float_opt(prezzo_notte)
    tariffa.prezzo_colazione = _parse_float_opt(prezzo_colazione)
    tariffa.prezzo_pranzo = _parse_float_opt(prezzo_pranzo)
    tariffa.prezzo_cena = _parse_float_opt(prezzo_cena)
    tariffa.tetto_spesa_fascia = _parse_float_opt(tetto_spesa_fascia)
    tariffa.sconto_giovani_percentuale = _parse_float_opt(sconto_giovani_percentuale)
    tariffa.attivo = attivo is not None

    db.add(
        LogEvento(
            oggetto_tipo="tariffa",
            oggetto_id=tariffa.id,
            azione="tariffa_modificata",
            operatore=username,
            dettagli={"prima": valori_precedenti, "dopo": _snapshot(tariffa)},
        )
    )
    db.commit()

    return RedirectResponse(url="/configurazione?sezione=tariffe&ok=1", status_code=303)


@app.post("/configurazione/tariffe/{tariffa_id}/elimina")
def configurazione_elimina_tariffa(tariffa_id: int, request: Request, db: Session = Depends(get_db)):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    tariffa = db.query(Tariffa).filter(Tariffa.id == tariffa_id).first()
    if not tariffa:
        raise HTTPException(status_code=404, detail="Tariffa non trovata.")

    db.add(
        LogEvento(
            oggetto_tipo="tariffa",
            oggetto_id=tariffa.id,
            azione="tariffa_eliminata",
            operatore=username,
            dettagli={"tipo_evento": tariffa.tipo_evento, "fascia": tariffa.fascia},
        )
    )
    db.delete(tariffa)
    db.commit()

    return RedirectResponse(url="/configurazione?sezione=tariffe&ok=1", status_code=303)


@app.post("/configurazione/operatori/nuovo")
def configurazione_crea_operatore(
    request: Request,
    nuovo_username: str = Form(...),
    nuovo_password: str = Form(...),
    nuovo_nome: str = Form(""),
    nuovo_is_admin: str | None = Form(None),
    db: Session = Depends(get_db),
):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    nuovo_username = nuovo_username.strip()
    if not nuovo_username or not nuovo_password:
        return RedirectResponse(
            url="/configurazione?sezione=operatori&errore=Username e password sono obbligatori.",
            status_code=303,
        )

    esistente = db.query(Operatore).filter(Operatore.username == nuovo_username).first()
    if esistente:
        return RedirectResponse(
            url=f"/configurazione?sezione=operatori&errore=Esiste già un operatore con username '{nuovo_username}'.",
            status_code=303,
        )

    operatore = Operatore(
        username=nuovo_username,
        password_hash=hash_password(nuovo_password),
        nome=nuovo_nome or None,
        attivo=True,
        is_admin=nuovo_is_admin is not None,
    )
    db.add(operatore)
    db.flush()

    db.add(
        LogEvento(
            oggetto_tipo="operatore",
            oggetto_id=operatore.id,
            azione="operatore_creato",
            operatore=username,
            dettagli={"username": operatore.username, "is_admin": operatore.is_admin},
        )
    )
    db.commit()

    return RedirectResponse(url="/configurazione?sezione=operatori&ok=1", status_code=303)


@app.post("/configurazione/operatori/{operatore_id}/toggle-admin")
def configurazione_toggle_admin_operatore(operatore_id: int, request: Request, db: Session = Depends(get_db)):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    operatore = db.query(Operatore).filter(Operatore.id == operatore_id).first()
    if not operatore:
        raise HTTPException(status_code=404, detail="Operatore non trovato.")

    if operatore.username == username and operatore.is_admin:
        return RedirectResponse(
            url="/configurazione?sezione=operatori&errore=Non puoi togliere a te stesso il ruolo di amministratore.",
            status_code=303,
        )

    operatore.is_admin = not operatore.is_admin
    db.add(
        LogEvento(
            oggetto_tipo="operatore",
            oggetto_id=operatore.id,
            azione="operatore_ruolo_modificato",
            operatore=username,
            dettagli={"username": operatore.username, "is_admin": operatore.is_admin},
        )
    )
    db.commit()

    return RedirectResponse(url="/configurazione?sezione=operatori&ok=1", status_code=303)


@app.post("/configurazione/operatori/{operatore_id}/toggle-attivo")
def configurazione_toggle_attivo_operatore(operatore_id: int, request: Request, db: Session = Depends(get_db)):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    operatore = db.query(Operatore).filter(Operatore.id == operatore_id).first()
    if not operatore:
        raise HTTPException(status_code=404, detail="Operatore non trovato.")

    if operatore.username == username and operatore.attivo:
        return RedirectResponse(
            url="/configurazione?sezione=operatori&errore=Non puoi disattivare te stesso.",
            status_code=303,
        )

    operatore.attivo = not operatore.attivo
    db.add(
        LogEvento(
            oggetto_tipo="operatore",
            oggetto_id=operatore.id,
            azione="operatore_stato_modificato",
            operatore=username,
            dettagli={"username": operatore.username, "attivo": operatore.attivo},
        )
    )
    db.commit()

    return RedirectResponse(url="/configurazione?sezione=operatori&ok=1", status_code=303)


@app.post("/configurazione/operatori/{operatore_id}/reset-password")
def configurazione_reset_password_operatore(
    operatore_id: int,
    request: Request,
    nuova_password: str = Form(...),
    db: Session = Depends(get_db),
):
    username, redirect = _richiedi_operatore_admin(request)
    if redirect:
        return redirect

    operatore = db.query(Operatore).filter(Operatore.id == operatore_id).first()
    if not operatore:
        raise HTTPException(status_code=404, detail="Operatore non trovato.")

    if not nuova_password:
        return RedirectResponse(
            url="/configurazione?sezione=operatori&errore=La nuova password non può essere vuota.",
            status_code=303,
        )

    operatore.password_hash = hash_password(nuova_password)
    db.add(
        LogEvento(
            oggetto_tipo="operatore",
            oggetto_id=operatore.id,
            azione="operatore_password_reimpostata",
            operatore=username,
            dettagli={"username": operatore.username},
        )
    )
    db.commit()

    return RedirectResponse(url="/configurazione?sezione=operatori&ok=1", status_code=303)