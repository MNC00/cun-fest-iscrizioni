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

        const checkSoloPranzo = blocco.querySelector('[data-field="flag_solo_pranzo_cun"]');
        const checkParliamoLunedi = blocco.querySelector('[data-field="flag_parliamo_solo_lunedi"]');
        const campiPasto = blocco.querySelectorAll(".campo-pasto");
        const msgParliamoLunedi = blocco.querySelector(".msg-parliamo-lunedi");
        const btnRimuovi = blocco.querySelector(".btn-rimuovi-partecipante");

        checkSoloPranzo.addEventListener("change", function () {
            campiPasto.forEach((campo) => {
                const select = campo.querySelector("select");
                campo.classList.toggle("d-none", checkSoloPranzo.checked);
                select.disabled = checkSoloPranzo.checked;
            });
        });

        checkParliamoLunedi.addEventListener("change", function () {
            msgParliamoLunedi.classList.toggle("d-none", !checkParliamoLunedi.checked);
        });

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

            const soloPranzoCun = getChecked("flag_solo_pranzo_cun");

            partecipanti.push({
                nome: getVal("nome"),
                cognome: getVal("cognome"),
                data_nascita: getVal("data_nascita") || null,
                zona_provenienza: getVal("zona_provenienza") || null,
                data_arrivo: getVal("data_arrivo") || null,
                data_partenza: getVal("data_partenza") || null,
                pasto_arrivo: soloPranzoCun ? "nessuno" : getVal("pasto_arrivo"),
                pasto_partenza: soloPranzoCun ? "nessuno" : getVal("pasto_partenza"),
                flag_solo_pranzo_cun: soloPranzoCun,
                flag_parliamo_solo_lunedi: getChecked("flag_parliamo_solo_lunedi"),
                note: getVal("note") || null,
                fascia_prezzo: "Generale",
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
                zona_provenienza: formData.get("referente_zona_provenienza") || null,
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
