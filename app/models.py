from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Famiglia(Base):
    __tablename__ = "famiglie"

    id = Column(Integer, primary_key=True)
    referente_nome = Column(String, nullable=False)
    referente_cognome = Column(String, nullable=False)
    email = Column(String, nullable=False)
    telefono = Column(String)
    zona_provenienza = Column(String)
    token_ricevute = Column(String, unique=True, index=True)  # accesso alla pagina pubblica di upload ricevute
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    partecipanti = relationship(
        "Partecipante", back_populates="famiglia", cascade="all, delete-orphan"
    )


class Partecipante(Base):
    __tablename__ = "partecipanti"

    id = Column(Integer, primary_key=True)
    famiglia_id = Column(Integer, ForeignKey("famiglie.id", ondelete="CASCADE"))
    nome = Column(String, nullable=False)
    cognome = Column(String, nullable=False)
    data_nascita = Column(Date)
    luogo_nascita = Column(String)
    zona_provenienza = Column(String)
    data_arrivo = Column(Date)
    data_partenza = Column(Date)
    pasto_arrivo = Column(String)
    pasto_partenza = Column(String)
    flag_solo_pranzo_cun = Column(Boolean, default=False)
    flag_precun = Column(Boolean, default=False)
    flag_campo_famiglie = Column(Boolean, default=False)
    flag_cun_fest = Column(Boolean, default=False)
    flag_bosco_domenica = Column(Boolean, default=False)
    flag_cena_ristorante_domenica = Column(Boolean)  # solo se flag_bosco_domenica; None = non applicabile
    note = Column(Text)
    fascia_prezzo = Column(String, default="Altro")  # 'Nord' | 'Altro'
    stato_iscrizione = Column(String, default="Inviata")
    token_annullamento = Column(String, unique=True, index=True)
    notti_calcolate = Column(Integer)
    prezzo_lordo = Column(Numeric)
    sconto_eta = Column(Numeric)
    prezzo_netto = Column(Numeric)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    famiglia = relationship("Famiglia", back_populates="partecipanti")


class Pagamento(Base):
    __tablename__ = "pagamenti"

    id = Column(Integer, primary_key=True)
    partecipante_id = Column(Integer, ForeignKey("partecipanti.id", ondelete="CASCADE"))
    importo_dovuto = Column(Numeric)
    importo_pagato = Column(Numeric, default=0)
    stato = Column(String, default="Non_pagato")
    data_pagamento = Column(Date)
    metodo = Column(String)
    causale = Column(String)
    note = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    partecipante = relationship("Partecipante", backref="pagamenti")


class Tariffa(Base):
    __tablename__ = "tariffe"

    id = Column(Integer, primary_key=True)
    tipo_evento = Column(String, nullable=False)  # 'precun' | 'campo_famiglie' | 'cun_fest' | 'pranzo_cun'
    fascia = Column(String)  # 'Nord' | 'Altro' | NULL = tariffa base dell'evento (tutte le fasce)
    prezzo_notte = Column(Numeric)
    prezzo_colazione = Column(Numeric)
    prezzo_pranzo = Column(Numeric)
    prezzo_cena = Column(Numeric)
    tetto_spesa_fascia = Column(Numeric)
    sconto_giovani_percentuale = Column(Numeric)
    valido_dal = Column(Date)
    valido_al = Column(Date)
    attivo = Column(Boolean, default=True)


class PeriodoEvento(Base):
    """Finestra di date di ciascun evento/componente (PreCunFest, Campo Famiglie,
    CunFest, pranzo CUN), indipendente dalle tariffe. Il periodo valido per un
    partecipante è l'unione dei periodi degli eventi a cui partecipa."""

    __tablename__ = "periodi_evento"

    id = Column(Integer, primary_key=True)
    tipo_evento = Column(String, nullable=False, unique=True)  # 'precun' | 'campo_famiglie' | 'cun_fest' | 'pranzo_cun'
    data_inizio = Column(Date)
    data_fine = Column(Date)


class Operatore(Base):
    __tablename__ = "operatori"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    nome = Column(String)
    attivo = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # accesso alla sezione /configurazione
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LogEvento(Base):
    __tablename__ = "log_eventi"

    id = Column(Integer, primary_key=True)
    oggetto_tipo = Column(String)
    oggetto_id = Column(Integer)
    azione = Column(String)
    operatore = Column(String)
    dettagli = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RicevutaPagamento(Base):
    """Una ricevuta (es. bonifico) caricata dalla famiglia. Può coprire uno o
    più partecipanti dello stesso nucleo (vedi RicevutaPartecipante): un unico
    bonifico può pagare l'intero nucleo, oppure la famiglia può caricare più
    ricevute separate per pagare partecipanti diversi in momenti diversi."""

    __tablename__ = "ricevute_pagamento"

    id = Column(Integer, primary_key=True)
    famiglia_id = Column(Integer, ForeignKey("famiglie.id", ondelete="CASCADE"), nullable=False)
    nome_file_originale = Column(String, nullable=False)
    storage_path = Column(String, nullable=False, unique=True)  # percorso su Supabase Storage
    content_type = Column(String)
    dimensione_bytes = Column(Integer)
    note = Column(Text)  # testo libero facoltativo inserito da chi carica (es. riferimento bonifico)
    verificata = Column(Boolean, default=False)  # controllo manuale dell'operatore (mai automatico)
    verificata_da = Column(String)  # username dell'operatore che ha verificato
    verificata_il = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    famiglia = relationship("Famiglia", backref="ricevute")
    partecipanti_coperti = relationship(
        "RicevutaPartecipante",
        back_populates="ricevuta",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RicevutaPartecipante(Base):
    """Associazione N:N tra una ricevuta e i partecipanti che copre."""

    __tablename__ = "ricevuta_partecipanti"

    ricevuta_id = Column(
        Integer, ForeignKey("ricevute_pagamento.id", ondelete="CASCADE"), primary_key=True
    )
    partecipante_id = Column(
        Integer, ForeignKey("partecipanti.id", ondelete="CASCADE"), primary_key=True
    )

    ricevuta = relationship("RicevutaPagamento", back_populates="partecipanti_coperti")
    partecipante = relationship("Partecipante", backref="ricevute_associate")

