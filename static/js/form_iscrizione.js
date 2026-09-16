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
            referente: {
                nome: formData.get("referente_nome"),
                cognome: formData.get("referente_cognome"),
                email: formData.get("referente_email"),
                telefono: formData.get("referente_telefono") || null,
                zona_provenienza: formData.get("referente_zona_provenienza") || null,
            },
            partecipanti: partecipanti,
        };

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
