from sqlalchemy.orm import Session

from app.models import Pagamento, Partecipante


def sincronizza_pagamento(partecipante: Partecipante, db: Session) -> Pagamento:
    """Crea o aggiorna il record di pagamento associato a un partecipante.

    Allinea importo_dovuto al prezzo_netto corrente del partecipante. Se il
    pagamento non esiste ancora viene creato con importo_pagato = 0 e stato
    'Non_pagato' — SOLO se il prezzo è già stato calcolato ed è effettivamente
    pari a zero lo stato diventa 'Pagato' automaticamente. Finché il prezzo
    non è ancora noto (None, tariffe non popolate) lo stato resta 'Non_pagato'.
    """
    prezzo_calcolato = partecipante.prezzo_netto is not None
    prezzo_netto = float(partecipante.prezzo_netto) if prezzo_calcolato else 0.0

    pagamento = (
        db.query(Pagamento).filter(Pagamento.partecipante_id == partecipante.id).first()
    )

    if pagamento:
        pagamento.importo_dovuto = prezzo_netto
        if pagamento.stato == "Non_pagato" and prezzo_calcolato and prezzo_netto == 0:
            pagamento.stato = "Pagato"
    else:
        pagamento = Pagamento(
            partecipante_id=partecipante.id,
            importo_dovuto=prezzo_netto,
            importo_pagato=0,
            stato="Pagato" if (prezzo_calcolato and prezzo_netto == 0) else "Non_pagato",
        )
        db.add(pagamento)

    db.flush()
    return pagamento
