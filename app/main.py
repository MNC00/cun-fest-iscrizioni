from datetime import date, timedelta
import logging

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_current_operatore_username,
    verify_password,
)
from app.calcolo import CalcoloPrezzoError, calcola_prezzo_partecipante, genera_report_pasti
from app.database import get_db
from app.email_service import (
    EmailServiceError,
    costruisci_email_annullamento,
    costruisci_email_massa,
    invia_aggiornamento_prezzo,
    invia_conferma_iscrizione,
    invia_email,
)
from app.models import Famiglia, LogEvento, Operatore, Pagamento, Partecipante, Tariffa
from app.pagamenti import sincronizza_pagamento
from app.schemas import IscrizioneFamigliaRequest

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="CUN Fest Iscrizioni")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={"title": "CUN Fest"},
    )


@app.get("/iscriviti")
def form_iscrizione(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="form_iscrizione.html",
        context={"title": "Iscrizione CUN Fest"},
    )


@app.get("/test-db-models")
def test_db_models(db: Session = Depends(get_db)):
    tariffe_count = db.query(Tariffa).count()
    return {"tariffe_count": tariffe_count, "status": "ok"}


@app.post("/iscriviti")
def iscriviti(payload: IscrizioneFamigliaRequest, db: Session = Depends(get_db)):
    try:
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
        for p in payload.partecipanti:
            partecipante = Partecipante(
                famiglia_id=famiglia.id,
                nome=p.nome,
                cognome=p.cognome,
                data_nascita=p.data_nascita,
                zona_provenienza=p.zona_provenienza,
                data_arrivo=p.data_arrivo,
                data_partenza=p.data_partenza,
                pasto_arrivo=p.pasto_arrivo,
                pasto_partenza=p.pasto_partenza,
                flag_solo_pranzo_cun=p.flag_solo_pranzo_cun,
                flag_parliamo_solo_lunedi=p.flag_parliamo_solo_lunedi,
                note=p.note,
                fascia_prezzo=p.fascia_prezzo,
            )
            db.add(partecipante)
            db.flush()
            sincronizza_pagamento(partecipante, db)
            partecipanti_ids.append(partecipante.id)

        db.commit()

        try:
            partecipanti_list = [
                {
                    "nome": p.nome,
                    "cognome": p.cognome,
                    "data_arrivo": p.data_arrivo.isoformat() if p.data_arrivo else "",
                    "data_partenza": p.data_partenza.isoformat() if p.data_partenza else "",
                }
                for p in payload.partecipanti
            ]
            invia_conferma_iscrizione(
                referente_nome=famiglia.referente_nome,
                referente_cognome=famiglia.referente_cognome,
                email=famiglia.email,
                partecipanti_list=partecipanti_list,
            )
        except EmailServiceError as exc:
            logger.error("Invio email di conferma fallito per famiglia %s: %s", famiglia.id, exc)

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

    token = create_session_token(operatore.username)
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
def dashboard(request: Request, msg: str | None = None, db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    famiglie = (
        db.query(Famiglia)
        .options(joinedload(Famiglia.partecipanti))
        .order_by(Famiglia.id)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Dashboard operatori",
            "username": username,
            "famiglie": famiglie,
            "msg": msg,
        },
    )


def _invia_email_aggiornamento_prezzo(partecipante: Partecipante, dettagli_calcolo: dict) -> None:
    """Invia al referente l'email con il prezzo appena (ri)calcolato per il partecipante.

    Chiamata solo a seguito di un'azione esplicita dell'operatore (ricalcolo o
    modifica iscrizione). Un eventuale errore di invio viene solo loggato,
    senza far fallire l'operazione di calcolo già commit-ata.
    """
    dettaglio_email = {
        "notti": dettagli_calcolo.get("notti"),
        "pasti": (
            f"{dettagli_calcolo.get('colazioni', 0)} colazioni, "
            f"{dettagli_calcolo.get('pranzi', 0)} pranzi, "
            f"{dettagli_calcolo.get('cene', 0)} cene"
        ),
        "fascia": dettagli_calcolo.get("fascia_prezzo"),
        "sconto": f"{dettagli_calcolo.get('sconto_eta', 0):.2f} €",
    }

    try:
        invia_aggiornamento_prezzo(
            email=partecipante.famiglia.email,
            partecipante_nome=f"{partecipante.nome} {partecipante.cognome}",
            prezzo_netto=dettagli_calcolo.get("prezzo_netto", 0),
            dettaglio=dettaglio_email,
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
        _invia_email_aggiornamento_prezzo(partecipante, dettagli_calcolo)
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
            _invia_email_aggiornamento_prezzo(partecipante, dettagli_calcolo)
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
        },
    )


@app.post("/modifica-iscrizione/{partecipante_id}")
def modifica_iscrizione_submit(
    partecipante_id: int,
    request: Request,
    data_arrivo: date = Form(...),
    data_partenza: date = Form(...),
    pasto_arrivo: str = Form("nessuno"),
    pasto_partenza: str = Form("nessuno"),
    fascia_prezzo: str = Form(...),
    note: str = Form(""),
    flag_solo_pranzo_cun: str | None = Form(None),
    flag_parliamo_solo_lunedi: str | None = Form(None),
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

    valori_precedenti = {
        "data_arrivo": partecipante.data_arrivo.isoformat() if partecipante.data_arrivo else None,
        "data_partenza": partecipante.data_partenza.isoformat() if partecipante.data_partenza else None,
        "pasto_arrivo": partecipante.pasto_arrivo,
        "pasto_partenza": partecipante.pasto_partenza,
        "flag_solo_pranzo_cun": partecipante.flag_solo_pranzo_cun,
        "flag_parliamo_solo_lunedi": partecipante.flag_parliamo_solo_lunedi,
        "fascia_prezzo": partecipante.fascia_prezzo,
    }

    partecipante.data_arrivo = data_arrivo
    partecipante.data_partenza = data_partenza
    partecipante.pasto_arrivo = pasto_arrivo
    partecipante.pasto_partenza = pasto_partenza
    partecipante.fascia_prezzo = fascia_prezzo
    partecipante.note = note or None
    partecipante.flag_solo_pranzo_cun = flag_solo_pranzo_cun is not None
    partecipante.flag_parliamo_solo_lunedi = flag_parliamo_solo_lunedi is not None

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
        "flag_parliamo_solo_lunedi": partecipante.flag_parliamo_solo_lunedi,
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

    _invia_email_aggiornamento_prezzo(partecipante, dettagli_calcolo)

    return RedirectResponse(url="/dashboard?ok=1", status_code=303)


@app.post("/annulla-iscrizione/{partecipante_id}")
def annulla_iscrizione(partecipante_id: int, request: Request, db: Session = Depends(get_db)):
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

    stato_precedente = partecipante.stato_iscrizione
    partecipante.stato_iscrizione = "Annullata"

    log = LogEvento(
        oggetto_tipo="partecipante",
        oggetto_id=partecipante.id,
        azione="iscrizione_annullata",
        operatore=username,
        dettagli={"stato_precedente": stato_precedente, "stato_nuovo": "Annullata"},
    )
    db.add(log)
    db.commit()

    try:
        contenuto_html = costruisci_email_annullamento({"nome": partecipante.nome})
        invia_email(
            destinatario=partecipante.famiglia.email,
            oggetto="Annullamento iscrizione CUN FEST",
            contenuto_html=contenuto_html,
        )
        msg = f"Iscrizione di {partecipante.nome} {partecipante.cognome} annullata. Email inviata."
    except EmailServiceError as exc:
        msg = f"Iscrizione annullata, ma invio email fallito: {exc}"

    return RedirectResponse(url=f"/dashboard?msg={msg}", status_code=303)


@app.get("/pagamenti")
def pagamenti_lista(request: Request, stato: str = "tutti", db: Session = Depends(get_db)):
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

    pagamenti = query.order_by(Pagamento.id).all()

    return templates.TemplateResponse(
        request=request,
        name="pagamenti.html",
        context={
            "title": "Pagamenti",
            "username": username,
            "pagamenti": pagamenti,
            "stato_filtro": stato,
        },
    )


@app.post("/pagamenti/segna-pagato/{pagamento_id}")
def segna_pagamento_pagato(pagamento_id: int, request: Request, db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    pagamento = db.query(Pagamento).filter(Pagamento.id == pagamento_id).first()
    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento non trovato.")

    pagamento.importo_pagato = pagamento.importo_dovuto
    pagamento.stato = "Pagato"
    pagamento.data_pagamento = date.today()

    log = LogEvento(
        oggetto_tipo="pagamento",
        oggetto_id=pagamento.id,
        azione="pagamento_registrato",
        operatore=username,
        dettagli={
            "partecipante_id": pagamento.partecipante_id,
            "importo_pagato": float(pagamento.importo_pagato or 0),
        },
    )
    db.add(log)
    db.commit()

    return RedirectResponse(url="/pagamenti?ok=1", status_code=303)


def _query_destinatari(db: Session, fascia: str, stato_iscrizione: str, zona_provenienza: str):
    """Costruisce la query dei partecipanti destinatari in base ai filtri di comunicazione."""
    query = db.query(Partecipante).join(Famiglia)
    if fascia:
        query = query.filter(Partecipante.fascia_prezzo == fascia)
    if stato_iscrizione:
        query = query.filter(Partecipante.stato_iscrizione == stato_iscrizione)
    if zona_provenienza:
        query = query.filter(Partecipante.zona_provenienza.ilike(f"%{zona_provenienza}%"))
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
            "filtri": {"fascia": "", "stato_iscrizione": "", "zona_provenienza": ""},
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
    zona_provenienza: str = Form(""),
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
        "zona_provenienza": zona_provenienza,
    }

    destinatari = _query_destinatari(db, fascia, stato_iscrizione, zona_provenienza).all()
    risultato = None

    if azione == "invia":
        inviate = 0
        fallite = 0
        for partecipante in destinatari:
            try:
                contenuto_html = costruisci_email_massa(partecipante.nome, oggetto, testo_libero)
                invia_email(
                    destinatario=partecipante.famiglia.email,
                    oggetto=oggetto,
                    contenuto_html=contenuto_html,
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
def report_pasti_pagina(request: Request, db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    righe = genera_report_pasti(db)

    return templates.TemplateResponse(
        request=request,
        name="report_pasti.html",
        context={
            "title": "Report pasti",
            "username": username,
            "righe": righe,
        },
    )


@app.get("/report-pasti/csv")
def report_pasti_csv(request: Request, db: Session = Depends(get_db)):
    username = get_current_operatore_username(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)

    righe = genera_report_pasti(db)

    def genera_righe_csv():
        yield "data,colazioni,pranzi,cene\n"
        for riga in righe:
            yield f"{riga['data'].isoformat()},{riga['colazioni']},{riga['pranzi']},{riga['cene']}\n"

    return StreamingResponse(
        genera_righe_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=report_pasti.csv"},
    )