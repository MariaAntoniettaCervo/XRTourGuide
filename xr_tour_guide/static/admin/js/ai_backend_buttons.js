// ai_backend_buttons.js
// Pulsanti per richiamare il modulo AI (XRTourGuide-AI-Backend) dall'admin Django.
// Il browser non parla mai direttamente col modulo FastAPI: passa sempre da una
// view Django (xr_tour_guide_core/views/ai_backend_views.py), che a sua volta
// accoda un task Celery (xr_tour_guide/tasks.py) per non bloccare la richiesta web.
//
// Pattern usato ovunque in questo file: avvio (risposta immediata) + polling
// (il browser richiede periodicamente lo stato, finché non è "ready").
//
// Layout: ogni campo (titolo, descrizione) viene avvolto in una riga flessibile
// con, a fianco, un'icona a ingranaggio (apre un popover col modello/motore da
// usare) e un'icona ad azione (bacchetta per il testo, altoparlante per
// l'audio) che si allarga in una "pillola" con lo stato durante l'elaborazione.
//
// Endpoint Django realmente usati:
//   POST /ai-backend/optimize-title/start/        { original_title, model }  -> { job_id }
//   POST /ai-backend/optimize-description/start/  { original_text, model }   -> { job_id }
//   GET  /ai-backend/optimize-text/status/?job_id=...
//        -> { status: "processing" } oppure { status: "ready", data: {...} }
//        - per il titolo, data.options (lista) + data.best_option
//        - per la descrizione, data.full_text_optimized
//   POST /ai-backend/generate-audio/start/  { waypoint_id, text, tts_engine }  -> { status: "processing" }
//   GET  /ai-backend/generate-audio/status/?waypoint_id=...
//        -> { status: "processing" } oppure { status: "ready" }
//        (il salvataggio vero avviene lato Django tramite il callback del modulo AI,
//        non tramite questo polling: il polling controlla solo se è già arrivato)

(function () {
    "use strict";

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(";").shift();
        return null;
    }

    async function callAiBackend(action, payload) {
        const response = await fetch(`/ai-backend/${action}/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const detail = await response.text().catch(() => "");
            throw new Error(`HTTP ${response.status} ${detail}`.trim());
        }
        return response.json();
    }

    // --- Layout: riga flessibile attorno a un campo esistente ---

    function wrapFieldWithControls(field, alignTop) {
        const wrapper = document.createElement("div");
        wrapper.style.cssText =
            "display:flex; gap:8px; align-items:" + (alignTop ? "flex-start" : "center") +
            "; position:relative; margin-top:4px;";
        field.insertAdjacentElement("beforebegin", wrapper);
        wrapper.appendChild(field);
        field.style.flex = "1";
        field.style.minWidth = "0";
        return wrapper;
    }

    function makePillButton(emoji, ariaLabel, accentColor) {
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("aria-label", ariaLabel);
        button.title = ariaLabel;
        button.dataset.originalAriaLabel = ariaLabel;
        button.style.cssText =
            "height:36px; min-width:36px; border-radius:18px; padding:0 9px; " +
            "display:flex !important; align-items:center; justify-content:center !important; gap:6px; text-align:center; " +
            "flex-shrink:0; white-space:nowrap; cursor:pointer; transition: all 0.2s ease; " +
            `background:${accentColor}22; border:1px solid ${accentColor}88; color:${accentColor};`;
        const icon = document.createElement("span");
        icon.textContent = emoji;
        icon.style.cssText = "font-size:16px; line-height:1; flex-shrink:0; transform: translateX(2px); display:inline-block;";
        const label = document.createElement("span");
        label.style.cssText = "font-size:13px; font-weight:600; max-width:0; overflow:hidden; white-space:nowrap; transition: max-width 0.25s ease;";
        button.appendChild(icon);
        button.appendChild(label);
        return { button, label };
    }

    function expandPill(button, label, text) {
        button.disabled = true;
        label.textContent = text;
        label.style.maxWidth = "220px";
    }

    function collapsePill(button, label) {
        button.disabled = false;
        label.style.maxWidth = "0";
        label.textContent = "";
    }

    function makePicker(options, ariaLabel, accentColor) {
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("aria-label", ariaLabel);
        button.title = ariaLabel;
        button.style.cssText =
            "height:36px; min-width:36px; border-radius:18px; padding:0 9px; " +
            "display:flex !important; align-items:center; justify-content:center !important; gap:6px; text-align:center; " +
            "flex-shrink:0; white-space:nowrap; cursor:pointer; transition: all 0.2s ease; " +
            `background:${accentColor}22; border:1px solid ${accentColor}88; color:${accentColor};`;

        const icon = document.createElement("span");
        icon.textContent = "⚙️";
        icon.style.cssText = "font-size:16px; line-height:1; flex-shrink:0; transform: translateX(2px); display:inline-block;";

        const label = document.createElement("span");
        label.style.cssText = "font-size:13px; font-weight:600;";

        button.appendChild(icon);
        button.appendChild(label);

        const menu = document.createElement("div");
        menu.style.cssText =
            "display:none; position:absolute; top:42px; right:0; z-index:20; " +
            "background:var(--surface-3, white); border:0.5px solid var(--border, #d1d5db); " +
            "border-radius:8px; box-shadow: var(--shadow-popover, 0 8px 24px rgba(0,0,0,0.12)); " +
            "padding:4px; min-width:190px;";

        let selected = options[0];

        options.forEach((opt) => {
            const item = document.createElement("button");
            item.type = "button";
            item.textContent = opt.label;
            item.style.cssText =
                "display:block; width:100%; text-align:left; padding:8px 10px; border-radius:6px; " +
                "cursor:pointer; font-size:13px; font-weight:500; background:transparent; border:none; color:#374151;";
            item.addEventListener("mouseenter", () => { item.style.background = "#f3f4f6"; });
            item.addEventListener("mouseleave", () => { item.style.background = "transparent"; });
            item.addEventListener("click", function (event) {
                event.stopPropagation();
                selected = opt;
                label.textContent = opt.short;
                menu.style.display = "none";
            });
            menu.appendChild(item);
        });

        button.addEventListener("click", function (event) {
            event.stopPropagation();
            const isOpen = menu.style.display !== "none";
            document.querySelectorAll("[data-ai-menu-open]").forEach((el) => {
                if (el !== menu) el.style.display = "none";
            });
            menu.style.display = isOpen ? "none" : "block";
            menu.dataset.aiMenuOpen = menu.style.display !== "none" ? "1" : "";
        });

        document.addEventListener("click", function (event) {
            if (!menu.contains(event.target) && event.target !== button) {
                menu.style.display = "none";
            }
        });

        return { button, menu, getValue: () => selected.value };
    }

    function makeModelPicker() {
        return makePicker(
            [
                { value: "llama3.1:8b", short: "Llama 3.1 8B", label: "Llama 3.1 8B (qualità)" },
                { value: "qwen2.5:7b", short: "Qwen 2.5 7B", label: "Qwen 2.5 7B (veloce)" },
            ],
            "Scegli modello AI",
            "#2563eb"
        );
    }

    function makeEnginePicker() {
        return makePicker(
            [
                { value: "coqui-xtts", short: "Coqui XTTS", label: "Coqui XTTS (qualità)" },
                { value: "piper", short: "Piper", label: "Piper (veloce)" },
            ],
            "Scegli motore audio",
            "#2563eb"
        );
    }

    // --- Titolo/descrizione: selezione tra opzioni generate ---

    function renderTitleOptions(afterElement, titleField, options, bestOption) {
        const existing = afterElement.nextElementSibling;
        if (existing && existing.dataset.aiTitleOptions) existing.remove();

        const container = document.createElement("div");
        container.dataset.aiTitleOptions = "1";
        container.style.cssText = "display:flex; flex-direction:column; gap:4px; margin-top:6px; max-width:480px;";

        options.forEach((option) => {
            const optionButton = document.createElement("button");
            optionButton.type = "button";
            const isBest = option === bestOption;
            optionButton.textContent = isBest ? `★ ${option}` : option;
            optionButton.style.cssText =
                "text-align:left; padding:6px 10px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:500; " +
                (isBest
                    ? "background:#ede9fe; border:1px solid #7c3aed; color:#5b21b6; font-weight:600;"
                    : "background:#f9fafb; border:1px solid #d1d5db; color:#374151;");
            optionButton.addEventListener("click", function () {
                titleField.value = option;
                container.remove();
            });
            container.appendChild(optionButton);
        });

        afterElement.insertAdjacentElement("afterend", container);
    }

    // --- Blocco riusabile: titolo con ingranaggio (modello) + bacchetta (ottimizza) ---

    function setupTitleControls(titleField) {
        if (titleField.dataset.aiButtonAdded) return;
        titleField.dataset.aiButtonAdded = "1";

        const wrapper = wrapFieldWithControls(titleField, false);
        const { button: pickerBtn, menu: pickerMenu, getValue: getModel } = makeModelPicker();
        const { button: wandBtn, label: wandLabel } = makePillButton("✨", "Ottimizza titolo", "#7c3aed");

        wrapper.appendChild(pickerBtn);
        wrapper.appendChild(wandBtn);
        wrapper.appendChild(pickerMenu);

        wandBtn.addEventListener("click", async function () {
            const text = titleField.value.trim();
            if (!text) return alert("Scrivi prima un titolo da ottimizzare.");
            expandPill(wandBtn, wandLabel, "Avvio...");
            try {
                const start = await callAiBackend("optimize-title/start", { original_title: text, model: getModel() });
                inFlightTextJobs.add(start.job_id);
                pollTextJob(wandBtn, wandLabel, start.job_id, (data) => {
                    if (data.options && data.options.length) {
                        renderTitleOptions(wrapper, titleField, data.options, data.best_option);
                    }
                });
            } catch (e) {
                alert("Errore ottimizzazione titolo: " + e.message);
                collapsePill(wandBtn, wandLabel);
            }
        });
    }

    // --- Blocco riusabile: descrizione con ingranaggio+bacchetta (ottimizza) e, se richiesto, ingranaggio+altoparlante (audio) ---

    function setupDescriptionControls(descField, options) {
        options = options || {};
        if (descField.dataset.aiButtonAdded) return;
        descField.dataset.aiButtonAdded = "1";

        const wrapper = wrapFieldWithControls(descField, true);

        const controlsColumn = document.createElement("div");
        controlsColumn.style.cssText = "display:flex; flex-direction:column; gap:6px; flex-shrink:0;";
        wrapper.appendChild(controlsColumn);

        const textRow = document.createElement("div");
        textRow.style.cssText = "display:flex; gap:8px; align-items:center; position:relative;";
        controlsColumn.appendChild(textRow);

        const { button: pickerBtn, menu: pickerMenu, getValue: getModel } = makeModelPicker();
        const { button: wandBtn, label: wandLabel } = makePillButton("✨", "Ottimizza descrizione", "#7c3aed");
        textRow.appendChild(pickerBtn);
        textRow.appendChild(wandBtn);
        textRow.appendChild(pickerMenu);

        wandBtn.addEventListener("click", async function () {
            const text = descField.value.trim();
            if (!text) return alert("Scrivi prima una descrizione da ottimizzare.");
            expandPill(wandBtn, wandLabel, "Avvio...");
            try {
                const start = await callAiBackend("optimize-description/start", {
                    original_text: text,
                    model: getModel(),
                    length_mode: options.lengthMode || "lungo",
                });
                inFlightTextJobs.add(start.job_id);
                pollTextJob(wandBtn, wandLabel, start.job_id, (data) => {
                    if (data.full_text_optimized) descField.value = data.full_text_optimized;
                });
            } catch (e) {
                alert("Errore ottimizzazione descrizione: " + e.message);
                collapsePill(wandBtn, wandLabel);
            }
        });

        if (options.audio) {
            const audioRow = document.createElement("div");
            audioRow.style.cssText = "display:flex; gap:8px; align-items:center; position:relative;";
            controlsColumn.appendChild(audioRow);

            const { button: enginePickerBtn, menu: enginePickerMenu, getValue: getEngine } = makeEnginePicker();
            const { button: audioBtn, label: audioLabel } = makePillButton("🎙️", options.audioLabel || "Genera audio", "#16a34a");
            audioRow.appendChild(enginePickerBtn);
            audioRow.appendChild(audioBtn);
            audioRow.appendChild(enginePickerMenu);

            if (options.disabledReason) {
                audioBtn.disabled = true;
                audioBtn.style.opacity = "0.5";
                audioBtn.title = options.disabledReason;
            } else {
                audioBtn.addEventListener("click", async function () {
                    const text = descField.value.trim();
                    if (!text) return alert("Scrivi prima una descrizione da convertire in audio.");

                    const waypointId = options.getWaypointId();
                    if (waypointId === undefined) {
                        alert("Nessun waypoint preliminare trovato. Crea un waypoint con 'Informazioni preliminari' attivo per abilitare l'audio del tour.");
                        return;
                    }
                    if (waypointId === null) {
                        alert("Salva prima (il waypoint deve avere un ID) prima di generare l'audio.");
                        return;
                    }

                    expandPill(audioBtn, audioLabel, "Avvio...");
                    try {
                        await callAiBackend("generate-audio/start", { waypoint_id: waypointId, text: text, tts_engine: getEngine() });
                        audioLabel.textContent = "In corso...";
                        pollAudioStatus(audioBtn, audioLabel, waypointId, wrapper);
                    } catch (e) {
                        alert("Errore avvio generazione audio: " + e.message);
                        collapsePill(audioBtn, audioLabel);
                    }
                });

                const resumeWaypointId = options.getWaypointId();
                if (resumeWaypointId) {
                    fetch(`/ai-backend/generate-audio/status/?waypoint_id=${encodeURIComponent(resumeWaypointId)}`)
                        .then((r) => r.json())
                        .then((result) => {
                            if (result.status === "processing") {
                                expandPill(audioBtn, audioLabel, result.stale_text ? "In corso (testo non salvato)..." : "In corso...");
                                pollAudioStatus(audioBtn, audioLabel, resumeWaypointId, wrapper);
                            } else if (result.status === "preview_ready") {
                                const widget = makePreviewAudioWidget(resumeWaypointId, result.stale_text);
                                wrapper.insertAdjacentElement("afterend", widget);
                        
                                watchResumedPreview(resumeWaypointId);
                            }
                        })
                        .catch(() => {}); // silenzioso: non è critico se questo controllo fallisce
                }
            }
        }
    }

    function initTourTextButtons(context) {
        const titleField = (context || document).querySelector("#id_title");
        if (titleField) setupTitleControls(titleField);

        const descField = (context || document).querySelector("#id_description");
        if (descField) {
            setupDescriptionControls(descField, { lengthMode: "lungo" });
        }
    }

    // --- Abbandono audio in corso (solo se si naviga via SENZA salvare) ---
    // Non possiamo fermare la sintesi vera (gira nel modulo AI, un processo
    // separato) — ci limitiamo a segnalare "quando arriva, buttalo via",
    // così l'utente non si ritrova un'anteprima basata su un testo mai
    // salvato. Se invece si sta salvando davvero (submit del form), NON
    // segnaliamo l'abbandono: quello è lo scenario in cui la generazione
    // deve continuare e essere ripresa normalmente al ritorno sulla pagina.
    const inFlightAudioWaypoints = new Set();
    let isSubmittingForm = false;

    document.addEventListener("submit", () => {
        isSubmittingForm = true;
    });

    function abandonInFlightAudio() {
        if (isSubmittingForm) return; // si sta salvando: la generazione deve continuare
        inFlightAudioWaypoints.forEach((waypointId) => {
            fetch("/ai-backend/generate-audio/abandon/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCookie("csrftoken"),
                },
                body: JSON.stringify({ waypoint_id: waypointId }),
                keepalive: true,
            }).catch(() => {});
        });
        inFlightAudioWaypoints.clear();
    }

    window.addEventListener("beforeunload", abandonInFlightAudio);
    window.addEventListener("pagehide", abandonInFlightAudio);

    // --- Annullamento ottimizzazioni testo in corso all'abbandono pagina ---
    // Riguarda solo titolo/descrizione/markdown: se navighi via prima che
    // l'IA risponda, il task continuerebbe a girare a vuoto sul server (il
    // risultato non verrebbe mai mostrato, dato che il testo non salvato non
    // torna comunque). Annullarlo evita solo lo spreco di calcolo, non tocca
    // in nessun modo il contenuto dei campi.
    //
    // Non riguarda l'audio: lì il comportamento voluto è l'opposto, la
    // generazione continua e viene ripresa al ritorno sulla pagina (vedi
    // watchResumedPreview).
    const inFlightTextJobs = new Set();

    function cancelInFlightTextJobs() {
        inFlightTextJobs.forEach((jobId) => {
            fetch("/ai-backend/optimize-text/cancel/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCookie("csrftoken"),
                },
                body: JSON.stringify({ job_id: jobId }),
                keepalive: true, // permette alla richiesta di completarsi anche mentre la pagina si scarica
            }).catch(() => {});
        });
        inFlightTextJobs.clear();
    }

    window.addEventListener("beforeunload", cancelInFlightTextJobs);
    window.addEventListener("pagehide", cancelInFlightTextJobs);

    async function pollTextJob(button, label, jobId, onReady, attempt = 0) {
        const POLL_INTERVAL_MS = 3000;
        const MAX_ATTEMPTS = 200; // ~10 minuti, allineato al nuovo timeout backend (600s)

        if (attempt >= MAX_ATTEMPTS) {
            label.textContent = "Timeout";
            setTimeout(() => collapsePill(button, label), 2000);
            inFlightTextJobs.delete(jobId);
            return;
        }

        label.textContent = "Elaborazione...";

        let result;
        try {
            const response = await fetch(`/ai-backend/optimize-text/status/?job_id=${encodeURIComponent(jobId)}`);
            result = await response.json();
        } catch (e) {
            setTimeout(() => pollTextJob(button, label, jobId, onReady, attempt + 1), POLL_INTERVAL_MS);
            return;
        }

        if (result.status === "ready") {
            onReady(result.data);
            collapsePill(button, label);
            inFlightTextJobs.delete(jobId);
            return;
        }
        if (result.status === "error") {
            alert("Errore durante l'elaborazione: " + (result.error || "sconosciuto"));
            collapsePill(button, label);
            inFlightTextJobs.delete(jobId);
            return;
        }

        setTimeout(() => pollTextJob(button, label, jobId, onReady, attempt + 1), POLL_INTERVAL_MS);
    }

    function makePreviewAudioWidget(waypointId, staleText) {
        // Rimuove un'eventuale anteprima precedente non ancora decisa per lo
        // stesso waypoint, per non accumulare widget se si rigenera più volte.
        document.querySelectorAll(`[data-ai-preview-for="${waypointId}"]`).forEach((el) => el.remove());

        const wrapper = document.createElement("div");
        wrapper.dataset.aiPreviewFor = waypointId;
        wrapper.style.cssText = "display:flex; flex-direction:column; gap:4px; margin-top:6px;";

        if (staleText) {
            const staleBadge = document.createElement("div");
            staleBadge.style.cssText =
                "display:inline-flex; align-items:center; gap:6px; padding:4px 10px; " +
                "border-radius:14px; background:#fef3c7; color:#92400e; font-size:12px; font-weight:600;";
            staleBadge.textContent = "⚠️ Generata da un testo non più salvato";
            wrapper.appendChild(staleBadge);
        }

        const container = document.createElement("div");
        container.dataset.aiPreviewFor = waypointId;
        container.style.cssText =
            "display:inline-flex; align-items:center; gap:8px; padding:6px 10px; " +
            "border-radius:20px; background:#eff6ff; border:1px solid #2563eb55;";
        wrapper.appendChild(container);

        const audio = document.createElement("audio");
        audio.src = `/ai-backend/generate-audio/preview/?waypoint_id=${encodeURIComponent(waypointId)}`;
        audio.preload = "metadata";
        audio.style.display = "none";

        const playBtn = document.createElement("button");
        playBtn.type = "button";
        playBtn.style.cssText =
            "height:30px; width:30px; min-width:30px; border-radius:50%; padding:0; display:flex; " +
            "align-items:center; justify-content:center; cursor:pointer; border:1px solid #2563eb88; " +
            "background:#2563eb22; color:#2563eb; flex-shrink:0;";
        const playIcon = document.createElement("span");
        playIcon.style.cssText =
            "display:inline-block; margin-left:2px; width:0; height:0; " +
            "border-top:5px solid transparent; border-bottom:5px solid transparent; border-left:8px solid currentColor;";
        const pauseIcon = document.createElement("span");
        pauseIcon.style.cssText = "display:none; align-items:center; gap:2px;";
        pauseIcon.innerHTML =
            '<span style="width:3px;height:10px;background:currentColor;display:inline-block;border-radius:1px;"></span>' +
            '<span style="width:3px;height:10px;background:currentColor;display:inline-block;border-radius:1px;"></span>';
        playBtn.appendChild(playIcon);
        playBtn.appendChild(pauseIcon);
        playBtn.addEventListener("click", () => {
            if (audio.paused) audio.play(); else audio.pause();
        });

        const track = document.createElement("div");
        track.style.cssText =
            "width:100px; height:6px; background:#2563eb26; border-radius:3px; position:relative; cursor:pointer;";
        const fill = document.createElement("div");
        fill.style.cssText = "width:0%; height:100%; background:#2563eb; border-radius:3px;";
        track.appendChild(fill);
        track.addEventListener("click", (event) => {
            if (!isFinite(audio.duration)) return;
            const rect = track.getBoundingClientRect();
            const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
            audio.currentTime = ratio * audio.duration;
        });

        function formatTime(sec) {
            if (!isFinite(sec)) return "0:00";
            const m = Math.floor(sec / 60);
            const s = Math.floor(sec % 60).toString().padStart(2, "0");
            return m + ":" + s;
        }

        const timeLabel = document.createElement("span");
        timeLabel.textContent = "0:00 / 0:00";
        timeLabel.style.cssText = "font-size:12px; font-weight:600; color:#2563eb; min-width:66px;";

        audio.addEventListener("play", () => {
            playIcon.style.display = "none";
            pauseIcon.style.display = "inline-flex";
        });
        audio.addEventListener("pause", () => {
            playIcon.style.display = "inline-block";
            pauseIcon.style.display = "none";
        });
        audio.addEventListener("ended", () => {
            playIcon.style.display = "inline-block";
            pauseIcon.style.display = "none";
        });
        audio.addEventListener("loadedmetadata", () => {
            timeLabel.textContent = "0:00 / " + formatTime(audio.duration);
        });
        audio.addEventListener("timeupdate", () => {
            const pct = isFinite(audio.duration) ? (audio.currentTime / audio.duration) * 100 : 0;
            fill.style.width = pct + "%";
            timeLabel.textContent = formatTime(audio.currentTime) + " / " + formatTime(audio.duration);
        });

        const badge = document.createElement("span");
        badge.textContent = "Anteprima";
        badge.style.cssText =
            "font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.03em; " +
            "color:#2563eb; background:#dbeafe; padding:2px 8px; border-radius:10px; flex-shrink:0;";

        const discardBtn = document.createElement("button");
        discardBtn.type = "button";
        discardBtn.title = "Scarta anteprima";
        discardBtn.style.cssText =
            "height:26px; width:26px; min-width:26px; border-radius:50%; padding:0; display:flex; " +
            "align-items:center; justify-content:center; cursor:pointer; border:1px solid #ef444488; " +
            "background:#ef444422; color:#dc2626; flex-shrink:0;";
        discardBtn.innerHTML =
            '<span style="font-size:15px; line-height:1; font-weight:700;">&times;</span>';

        discardBtn.addEventListener("click", async () => {
            discardBtn.disabled = true;
            audio.pause();
            try {
                await callAiBackend("generate-audio/discard", { waypoint_id: waypointId });
                wrapper.remove();
            } catch (e) {
                alert("Errore nello scarto dell'anteprima: " + e.message);
                discardBtn.disabled = false;
            }
        });

        container.appendChild(badge);
        container.appendChild(playBtn);
        container.appendChild(audio);
        container.appendChild(track);
        container.appendChild(timeLabel);
        container.appendChild(discardBtn);
        return wrapper;
    }

    async function pollAudioStatus(button, label, waypointId, anchorElement, attempt = 0) {
        const POLL_INTERVAL_MS = 4000;
        const MAX_ATTEMPTS = 90; // ~6 minuti, generoso per Coqui XTTS su CPU
        const anchor = anchorElement || button;

        if (attempt >= MAX_ATTEMPTS) {
            label.textContent = "Timeout";
            setTimeout(() => collapsePill(button, label), 2000);
            return;
        }

        let result;
        try {
            const response = await fetch(`/ai-backend/generate-audio/status/?waypoint_id=${encodeURIComponent(waypointId)}`);
            result = await response.json();
        } catch (e) {
            setTimeout(() => pollAudioStatus(button, label, waypointId, anchorElement, attempt + 1), POLL_INTERVAL_MS);
            return;
        }

        if (result.status === "preview_ready") {
            collapsePill(button, label);
            const widget = makePreviewAudioWidget(waypointId, result.stale_text);
            anchor.insertAdjacentElement("afterend", widget);
            return;
        }

        if (result.status === "ready") {
            // Confermato per un'altra via (es. rete di sicurezza già scattata)
            // prima che il polling arrivasse qui.
            label.textContent = "Pronto ✓";
            setTimeout(() => collapsePill(button, label), 3000);
            return;
        }

        button.title = result.stale_text
            ? "Questa generazione si riferisce a un testo non più salvato"
            : "";
        label.textContent = result.stale_text ? "In corso (testo non salvato)..." : "In corso...";

        setTimeout(() => pollAudioStatus(button, label, waypointId, anchorElement, attempt + 1), POLL_INTERVAL_MS);
    }

    function setupMarkdownControls(readmeField) {
        if (readmeField.dataset.aiButtonAdded) return;
        readmeField.dataset.aiButtonAdded = "1";

        const wrapper = wrapFieldWithControls(readmeField, true);
        const { button: pickerBtn, menu: pickerMenu, getValue: getModel } = makeModelPicker();
        const { button: wandBtn, label: wandLabel } = makePillButton("✨", "Ottimizza markdown", "#7c3aed");

        wrapper.appendChild(pickerBtn);
        wrapper.appendChild(wandBtn);
        wrapper.appendChild(pickerMenu);

        wandBtn.addEventListener("click", async function () {
            const text = readmeField.value.trim();
            if (!text) return alert("Scrivi prima del testo da correggere.");
            expandPill(wandBtn, wandLabel, "Avvio...");
            try {
                const start = await callAiBackend("optimize-markdown/start", { text: text, model: getModel() });
                inFlightTextJobs.add(start.job_id);
                pollTextJob(wandBtn, wandLabel, start.job_id, (data) => {
                    if (data.fixed_text) {
                        // SimpleMDE tiene il proprio editor separato dalla textarea:
                        // scrivere solo .value non basta, altrimenti l'editor visuale
                        // sovrascrive il nostro testo al prossimo aggiornamento/submit.
                        if (readmeField._simplemde) {
                            readmeField._simplemde.value(data.fixed_text);
                        } else {
                            readmeField.value = data.fixed_text;
                        }
                    }
                });
            } catch (e) {
                alert("Errore ottimizzazione markdown: " + e.message);
                collapsePill(wandBtn, wandLabel);
            }
        });
    }

    function setInnerHtmlAndRunScripts(container, html) {
        // Il browser non esegue automaticamente gli script inseriti via
        // innerHTML (per sicurezza) — il player audio dipende da uno script
        // inline per il play/pausa/barra di avanzamento, quindi va rieseguito
        // manualmente ricreando il tag <script>.
        container.innerHTML = html;
        container.querySelectorAll("script").forEach((oldScript) => {
            const newScript = document.createElement("script");
            newScript.textContent = oldScript.textContent;
            oldScript.replaceWith(newScript);
        });
    }

    function refreshConfirmedPlayers(waypointId) {
        // Aggiorna in-place entrambi i punti in cui il player può comparire
        // (vicino alla descrizione e nella sezione multimediale), senza
        // ricaricare l'intera pagina.
        ["near_desc", "multimedia"].forEach((location) => {
            const container = document.getElementById(`audio-player-container-${location}-${waypointId}`);
            if (!container) return; // questo waypoint potrebbe non avere quel punto (es. non mostrato)

            fetch(`/ai-backend/waypoint-audio-player/?waypoint_id=${encodeURIComponent(waypointId)}&location=${location}`)
                .then((r) => r.json())
                .then((result) => {
                    if (result.html !== undefined) {
                        setInnerHtmlAndRunScripts(container, result.html);
                    }
                })
                .catch(() => {});
        });
    }

    function watchResumedPreview(waypointId) {
        // Usata solo per un'anteprima RIPRISTINATA al caricamento pagina (non
        // per una appena generata dal click, che resta sotto il controllo
        // esplicito dell'utente). Se il commit era già in corso al momento
        // del ricaricamento e si risolve poco dopo, aggiorniamo il player
        // in-place e togliamo il widget "fantasma" — senza reload.
        let attempts = 0;
        const MAX_ATTEMPTS = 30; // ~1 minuto: l'utente potrebbe metterci un po' a decidere

        function check() {
            attempts++;
            fetch(`/ai-backend/generate-audio/status/?waypoint_id=${encodeURIComponent(waypointId)}`)
                .then((r) => r.json())
                .then((result) => {
                    if (result.status === "preview_ready") {
                        if (attempts < MAX_ATTEMPTS) setTimeout(check, 2000);
                        return;
                    }
                    if (result.status === "ready") {
                        // Confermato nel frattempo: il widget è ormai "fantasma",
                        // lo togliamo e aggiorniamo il player al suo posto.
                        document.querySelectorAll(`[data-ai-preview-for="${waypointId}"]`).forEach((el) => el.remove());
                        refreshConfirmedPlayers(waypointId);
                    }
                    // altrimenti (es. scartata altrove) ci fermiamo in silenzio
                })
                .catch(() => {});
        }

        setTimeout(check, 2000);
    }

    function watchForPendingConfirmation(waypointId) {
        // Se al caricamento della pagina il badge "audio differisce dal testo"
        // è presente, potrebbe essere un vero disallineamento (audio mai
        // rigenerato per il nuovo testo — nulla da fare, serve un click su
        // "Genera audio") OPPURE il commit dell'ultima anteprima è ancora in
        // corso (Celery non ha ancora finito di scrivere).
        //
        // IMPORTANTE: "status: ready" da solo NON basta per dedurre "la
        // conferma è appena arrivata" — un audio VECCHIO, mai aggiornato,
        // risulta "ready" fin dal primissimo controllo (esiste da sempre).
        // Ricarichiamo quindi SOLO se osserviamo prima uno stato realmente
        // "in corso/in sospeso" (processing o preview_ready) che POI si
        // risolve in "ready" — segno inequivocabile che stavamo aspettando
        // un commit vero, non un disallineamento permanente.
        const mismatchPresent = !!document.querySelector(`[data-ai-audio-mismatch-for="${waypointId}"]`);
        if (!mismatchPresent) return;

        let attempts = 0;
        const MAX_ATTEMPTS = 5; // ~10 secondi, poi ci si arrende (probabile disallineamento vero)
        let sawInFlight = false;

        function check() {
            attempts++;
            fetch(`/ai-backend/generate-audio/status/?waypoint_id=${encodeURIComponent(waypointId)}`)
                .then((r) => r.json())
                .then((result) => {
                    if (result.status === "processing" || result.status === "preview_ready") {
                        sawInFlight = true;
                        if (attempts < MAX_ATTEMPTS) setTimeout(check, 2000);
                        return;
                    }
                    if (result.status === "ready" && sawInFlight) {
                        // Era davvero in corso una conferma, ed è appena arrivata.
                        refreshConfirmedPlayers(waypointId);
                        return;
                    }
                    // "ready" senza aver mai visto nulla in corso: nessuna
                    // conferma pendente, il disallineamento è reale — non
                    // facciamo nulla, evitiamo un aggiornamento inutile (o un loop).
                })
                .catch(() => {});
        }

        setTimeout(check, 2000);
    }

    function initWaypointTextButtons(context) {
        const descriptionFields = (context || document).querySelectorAll('[name$="-description"]');

        descriptionFields.forEach(function (descField) {
            const name = descField.getAttribute("name") || "";
            if (!name.endsWith("-description")) return;
            if (name.includes("__prefix__")) return; // modello nascosto per nuove righe: non va inizializzato,
                                                       // altrimenti le righe clonate da qui erediterebbero i
                                                       // marcatori "già fatto" senza i relativi event listener
            const prefix = name.slice(0, name.length - "description".length);

            const titleField = document.querySelector(`[name="${prefix}title"]`);
            if (!titleField) return; // riga non è un waypoint (altro inline nested)

            setupTitleControls(titleField);

            const readmeField = document.querySelector(`[name="${prefix}readme_text"]`);
            if (readmeField) setupMarkdownControls(readmeField);

            const idField = document.querySelector(`[name="${prefix}id"]`);
            const audioField = document.querySelector(`[name="${prefix}audio_item"]`);
            const waypointId = idField ? idField.value : null;

            setupDescriptionControls(descField, {
                lengthMode: "breve",
                audio: !!audioField,
                audioLabel: "Genera audio da questa descrizione",
                disabledReason: waypointId ? null : "Salva prima il waypoint per generare l'audio",
                getWaypointId: () => (waypointId ? waypointId : null),
            });

            if (waypointId) watchForPendingConfirmation(waypointId);
        });
    }

    function initAll(context) {
        initTourTextButtons(context);
        initWaypointTextButtons(context);
    }

    document.addEventListener("DOMContentLoaded", () => initAll(document));

    // Righe waypoint aggiunte a runtime (nested_admin / formset dinamico)
    document.addEventListener("formset:added", (event) => initAll(event.target));
    if (typeof django !== "undefined" && django.jQuery) {
        django.jQuery(document).on("formset:added", (event) => initAll(event.target));
    }
})();