from sqlalchemy.orm import Session

from app.models import Pagamento, Partecipante


def sincronizza_pagamento(partecipante: Partecipante, db: Session) -> Pagamento:
    """Crea o aggiorna il record di pagamento associato a un partecipante.

    Allinea importo_dovuto al prezzo_netto corrente del partecipante. Se il
    pagamento non esiste ancora viene creato con importo_pagato = 0 e stato
    'Non_pagato' (o 'Pagato' se il prezzo netto è zero).
    """
    prezzo_netto = float(partecipante.prezzo_netto) if partecipante.prezzo_netto is not None else 0.0

    pagamento = (
        db.query(Pagamento).filter(Pagamento.partecipante_id == partecipante.id).first()
    )

    if pagamento:
        pagamento.importo_dovuto = prezzo_netto
        if pagamento.stato == "Non_pagato" and prezzo_netto == 0:
            pagamento.stato = "Pagato"
    else:
        pagamento = Pagamento(
            partecipante_id=partecipante.id,
            importo_dovuto=prezzo_netto,
            importo_pagato=0,
            stato="Pagato" if prezzo_netto == 0 else "Non_pagato",
        )
        db.add(pagamento)

    db.flush()
    return pagamento
