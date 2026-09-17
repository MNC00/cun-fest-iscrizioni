document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("partecipanti-container");
    const template = document.getElementById("template-partecipante");
    const btnAggiungi = document.getElementById("btn-aggiungi-partecipante");
    const nessunPartecipanteMsg = document.getElementById("nessun-partecipante-msg");
    const form = document.getElementById("form-iscrizione");
    const alertBox = document.getElementById("alert-box");

    let partecipanteCounter = 0;

    function aggiornaIndici() {
        const blocchi = container.querySelectorAll(".partecipante-block");
        blocchi.forEach((blocco, idx) => {
            blocco.querySelector(".partecipante-index").textContent = idx + 1;
        });
        nessunPartecipanteMsg.classList.toggle("d-none", blocchi.length > 0);
    }

    function aggiungiPartecipante() {
        partecipanteCounter += 1;
        const clone = template.content.cloneNode(true);
        const blocco = clone.querySelector(".partecipante-block");

        // Rende univoci gli id/for dei checkbox per evitare duplicati nel DOM
        blocco.querySelectorAll("[id]").forEach((el) => {
            const nuovoId = el.id + "-" + partecipanteCounter;
            el.id = nuovoId;
        });
        blocco.querySelectorAll("label[for]").forEach((label) => {
            label.setAttribute("for", label.getAttribute("for") + "-" + partecipanteCounter);
        });

        const checkModalitaNormale = blocco.querySelector('[data-field="modalita_iscrizione"][value="normale"]');
        const checkModalitaPranzo = blocco.querySelector('[data-field="modalita_iscrizione"][value="pranzo_cun"]');
        const blocchiEventiNormali = blocco.querySelectorAll(".blocco-eventi-normali");
        const blocchiPranzoCun = blocco.querySelectorAll(".blocco-pranzo-cun");
        const checkPrecun = blocco.querySelector('[data-field="flag_precun"]');
        const checkCampoFamiglie = blocco.querySelector('[data-field="flag_campo_famiglie"]');
        const checkCunFest = blocco.querySelector('[data-field="flag_cun_fest"]');
        const checkBoscoDomenica = blocco.querySelector('[data-field="flag_bosco_domenica"]');
        const campiPasto = blocco.querySelectorAll(".campo-pasto");
        const msgBoscoDomenica = blocco.querySelector(".msg-bosco-domenica");
        const campoCenaDomenica = blocco.querySelector(".campo-cena-domenica");
        const btnRimuovi = blocco.querySelector(".btn-rimuovi-partecipante");
        const inputDataArrivo = blocco.querySelector('[data-field="data_arrivo"]');
        const inputDataPartenza = blocco.querySelector('[data-field="data_partenza"]');
        const notaDateEvento = blocco.querySelector(".nota-date-evento");

        function formattaDataIt(isoDate) {
            const [anno, mese, giorno] = isoDate.split("-");
            return `${giorno}/${mese}/${anno}`;
        }

        function aggiornaVincoliData() {
            if (!window.PERIODI_EVENTI) return;
            const componenti = [];
            if (checkPrecun && checkPrecun.checked) componenti.push("precun");
            if (checkCampoFamiglie && checkCampoFamiglie.checked) componenti.push("campo_famiglie");
            if (checkCunFest && checkCunFest.checked) componenti.push("cun_fest");

            let dataMin = null;
            let dataMax = null;
            componenti.forEach((tipo) => {
                const periodo = window.PERIODI_EVENTI[tipo];
                if (!periodo) return;
                if (periodo.min && (!dataMin || periodo.min < dataMin)) dataMin = periodo.min;
                if (periodo.max && (!dataMax || periodo.max > dataMax)) dataMax = periodo.max;
            });

            inputDataArrivo.min = dataMin || "";
            inputDataPartenza.min = dataMin || "";
            inputDataArrivo.max = dataMax || "";
            inputDataPartenza.max = dataMax || "";

            if (notaDateEvento) {
                if (dataMin && dataMax) {
                    notaDateEvento.textContent =
                        "Per gli eventi selezionati puoi inserire solo date comprese tra il " +
                        formattaDataIt(dataMin) + " e il " + formattaDataIt(dataMax) + ".";
                } else if (componenti.length > 0) {
                    notaDateEvento.textContent = "";
                } else {
                    notaDateEvento.textContent = "Seleziona almeno un evento per vedere le date consentite.";
                }
            }
        }


        // PreCunFest e Campo Famiglie sono mutuamente esclusivi (si svolgono in contemporanea)
        if (checkPrecun && checkCampoFamiglie) {
            checkPrecun.addEventListener("change", function () {
                if (checkPrecun.checked) checkCampoFamiglie.checked = false;
                aggiornaVincoliData();
            });
            checkCampoFamiglie.addEventListener("change", function () {
                if (checkCampoFamiglie.checked) checkPrecun.checked = false;
                aggiornaVincoliData();
            });
        }
        if (checkCunFest) {
            checkCunFest.addEventListener("change", aggiornaVincoliData);
        }

        function aggiornaVisibilitaCenaDomenica() {
            const boscoAttivo = checkBoscoDomenica.checked;
            msgBoscoDomenica.classList.toggle("d-none", !boscoAttivo);
            campoCenaDomenica.classList.toggle("d-none", !boscoAttivo);
            campoCenaDomenica.querySelectorAll("input").forEach((radio) => {
                radio.disabled = !boscoAttivo;
                if (!boscoAttivo) radio.checked = false;
            });
        }

        function aggiornaModalitaIscrizione() {
            const isPranzoCun = checkModalitaPranzo && checkModalitaPranzo.checked;
            blocchiEventiNormali.forEach((el) => {
                el.classList.toggle("d-none", isPranzoCun);
                el.querySelectorAll("input, select, textarea").forEach((campo) => {
                    campo.disabled = isPranzoCun;
                });
            });
            blocchiPranzoCun.forEach((el) => el.classList.toggle("d-none", !isPranzoCun));
            if (!isPranzoCun) {
                aggiornaVincoliData();
                // Il toggle qui sopra su blocchiEventiNormali rimuove "d-none" anche dal
                // blocco cena-domenica (ne fa parte): va ripristinato in base al flag
                // "Vorrei dormire a Bosco la domenica sera", non reso sempre visibile.
                aggiornaVisibilitaCenaDomenica();
            }
        }

        if (checkModalitaNormale && checkModalitaPranzo) {
            checkModalitaNormale.addEventListener("change", aggiornaModalitaIscrizione);
            checkModalitaPranzo.addEventListener("change", aggiornaModalitaIscrizione);
        }
        aggiornaModalitaIscrizione();

        checkBoscoDomenica.addEventListener("change", aggiornaVisibilitaCenaDomenica);

        btnRimuovi.addEventListener("click", function () {
            blocco.remove();
            aggiornaIndici();
        });

        container.appendChild(blocco);
        aggiornaIndici();
    }

    btnAggiungi.addEventListener("click", aggiungiPartecipante);

    // Aggiunge un primo partecipante di default
    aggiungiPartecipante();

    // --- Gestione tipo di iscrizione (singola / famiglia / estensione) ---
    const radioTipoIscrizione = document.querySelectorAll('input[name="tipo_iscrizione"]');
    const campiReferenteNome = document.querySelectorAll(".campo-referente-nome");
    const campiReferenteContatto = document.querySelectorAll(".campo-referente-contatto");
    const campoFamigliaEsistente = document.querySelector(".campo-famiglia-esistente");
    const inputFamigliaEsistente = campoFamigliaEsistente.querySelector("input");
    const inputReferenteEmail = document.querySelector('input[name="referente_email"]');
    const titoloSezioneReferente = document.getElementById("titolo-sezione-referente");
    const sottotitoloSezioneReferente = document.getElementById("sottotitolo-sezione-referente");
    const titoloSezionePartecipanti = document.getElementById("titolo-sezione-partecipanti");

    const TESTI_MODALITA = {
        singola: {
            titoloReferente: "I tuoi dati di contatto",
            sottotitoloReferente: "Nome e cognome verranno presi automaticamente dal partecipante qui sotto.",
            titoloPartecipanti: "Il tuo partecipante",
        },
        famiglia: {
            titoloReferente: "Referente del nucleo familiare",
            sottotitoloReferente: "Questi dati identificano la famiglia e verranno usati per le comunicazioni.",
            titoloPartecipanti: "Partecipanti della famiglia",
        },
        estensione: {
            titoloReferente: "Identifica il tuo nucleo familiare",
            sottotitoloReferente: "Inserisci l'email usata per la prima iscrizione: i nuovi partecipanti verranno aggiunti a quella famiglia.",
            titoloPartecipanti: "Nuovi partecipanti da aggiungere al nucleo",
        },
    };

    function getTipoIscrizione() {
        const scelto = document.querySelector('input[name="tipo_iscrizione"]:checked');
        return scelto ? scelto.value : "singola";
    }

    function impostaSezione(elementi, mostra) {
        elementi.forEach((el) => {
            el.classList.toggle("d-none", !mostra);
            el.querySelectorAll("input, select, textarea").forEach((campo) => {
                campo.disabled = !mostra;
            });
        });
    }

    function aggiornaTipoIscrizione() {
        const tipo = getTipoIscrizione();
        const testi = TESTI_MODALITA[tipo] || TESTI_MODALITA.singola;

        impostaSezione(campiReferenteNome, tipo === "famiglia");
        impostaSezione(campiReferenteContatto, tipo !== "estensione");
        impostaSezione([campoFamigliaEsistente], tipo === "estensione");

        inputFamigliaEsistente.required = tipo === "estensione";
        inputReferenteEmail.required = tipo !== "estensione";

        titoloSezioneReferente.textContent = testi.titoloReferente;
        sottotitoloSezioneReferente.textContent = testi.sottotitoloReferente;
        titoloSezionePartecipanti.textContent = testi.titoloPartecipanti;

        btnAggiungi.classList.toggle("d-none", tipo === "singola");

        if (tipo === "singola") {
            const blocchi = container.querySelectorAll(".partecipante-block");
            blocchi.forEach((blocco, idx) => {
                if (idx > 0) blocco.remove();
            });
            if (container.querySelectorAll(".partecipante-block").length === 0) {
                aggiungiPartecipante();
            }
            aggiornaIndici();
        }
    }

    radioTipoIscrizione.forEach((radio) => radio.addEventListener("change", aggiornaTipoIscrizione));
    aggiornaTipoIscrizione();

    function mostraAlert(tipo, messaggio) {
        alertBox.innerHTML =
            '<div class="alert alert-' + tipo + '" role="alert">' + messaggio + "</div>";
    }

    function raccogliPartecipanti() {
        const blocchi = container.querySelectorAll(".partecipante-block");
        const partecipanti = [];

        blocchi.forEach((blocco) => {
            const getVal = (field) => {
                const el = blocco.querySelector('[data-field="' + field + '"]');
                return el ? el.value : null;
            };
            const getChecked = (field) => {
                const el = blocco.querySelector('[data-field="' + field + '"]');
                return el ? el.checked : false;
            };

            const modalitaEl = blocco.querySelector('[data-field="modalita_iscrizione"]:checked');
            const soloPranzoCun = modalitaEl ? modalitaEl.value === "pranzo_cun" : false;
            const boscoDomenica = soloPranzoCun ? false : getChecked("flag_bosco_domenica");
            const cenaRistoranteEl = blocco.querySelector('[data-field="flag_cena_ristorante_domenica"]:checked');
            const cenaRistorante = boscoDomenica && cenaRistoranteEl ? cenaRistoranteEl.value === "true" : null;

            partecipanti.push({
                nome: getVal("nome"),
                cognome: getVal("cognome"),
                data_nascita: getVal("data_nascita") || null,
                luogo_nascita: getVal("luogo_nascita") || null,
                zona_provenienza: getVal("zona_provenienza") || null,
                data_arrivo: soloPranzoCun ? null : (getVal("data_arrivo") || null),
                data_partenza: soloPranzoCun ? null : (getVal("data_partenza") || null),
                pasto_arrivo: soloPranzoCun ? "nessuno" : getVal("pasto_arrivo"),
                pasto_partenza: soloPranzoCun ? "nessuno" : getVal("pasto_partenza"),
                flag_solo_pranzo_cun: soloPranzoCun,
                flag_precun: soloPranzoCun ? false : getChecked("flag_precun"),
                flag_campo_famiglie: soloPranzoCun ? false : getChecked("flag_campo_famiglie"),
                flag_cun_fest: soloPranzoCun ? false : getChecked("flag_cun_fest"),
                flag_bosco_domenica: boscoDomenica,
                flag_cena_ristorante_domenica: cenaRistorante,
                note: getVal("note") || null,
                fascia_prezzo: "Altro",
            });
        });

        return partecipanti;
    }

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        alertBox.innerHTML = "";

        const formData = new FormData(form);
        const partecipanti = raccogliPartecipanti();

        if (partecipanti.length === 0) {
            mostraAlert("warning", "Aggiungi almeno un partecipante prima di inviare l'iscrizione.");
            return;
        }

        const payload = {
            partecipanti: partecipanti,
        };

        const tipo = getTipoIscrizione();
        if (tipo === "estensione") {
            payload.famiglia_esistente_email = formData.get("famiglia_esistente_email");
        } else {
            payload.referente = {
                nome: tipo === "singola" ? partecipanti[0].nome : formData.get("referente_nome"),
                cognome: tipo === "singola" ? partecipanti[0].cognome : formData.get("referente_cognome"),
                email: formData.get("referente_email"),
                telefono: formData.get("referente_telefono") || null,
            };
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;

        fetch("/iscriviti", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
            .then((response) => {
                return response.json().then((data) => ({ ok: response.ok, data }));
            })
            .then(({ ok, data }) => {
                if (ok) {
                    mostraAlert(
                        "success",
                        "Iscrizione inviata con successo! Famiglia #" +
                            data.famiglia_id +
                            ", partecipanti registrati: " +
                            data.partecipanti_ids.length
                    );
                    form.reset();
                    container.innerHTML = "";
                    partecipanteCounter = 0;
                    aggiungiPartecipante();
                    aggiornaTipoIscrizione();
                } else {
                    const dettaglio = data.detail || "Errore durante l'invio dell'iscrizione.";
                    mostraAlert("danger", "Errore: " + dettaglio);
                }
            })
            .catch(() => {
                mostraAlert("danger", "Errore di rete: impossibile contattare il server.");
            })
            .finally(() => {
                submitBtn.disabled = false;
            });
    });
});
