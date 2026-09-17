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
    flag_bosco_domenica = Column(Boolean, default=False)
    flag_cena_ristorante_domenica = Column(Boolean)  # solo se flag_bosco_domenica; None = non applicabile
    tipo_evento = Column(String, default="solo_cun")  # 'precun_cun' | 'campo_famiglie_cun' | 'solo_cun'
    note = Column(Text)
    fascia_prezzo = Column(String, default="Generale")
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
    fascia = Column(String, nullable=False)
    prezzo_notte = Column(Numeric)
    prezzo_colazione = Column(Numeric)
    prezzo_pranzo = Column(Numeric)
    prezzo_cena = Column(Numeric)
    tetto_spesa_fascia = Column(Numeric)
    sconto_giovani_percentuale = Column(Numeric)
    valido_dal = Column(Date)
    valido_al = Column(Date)
    attivo = Column(Boolean, default=True)


class Operatore(Base):
    __tablename__ = "operatori"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    nome = Column(String)
    attivo = Column(Boolean, default=True)
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
