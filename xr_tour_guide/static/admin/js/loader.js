document.addEventListener("DOMContentLoaded", function () {
    if (!document.getElementById("xr-loader-style")) {
        const style = document.createElement("style");
        style.id = "xr-loader-style";
        style.textContent = `
            @keyframes xr-spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }

            @keyframes xr-spin-reverse {
                0% { transform: rotate(360deg); }
                100% { transform: rotate(0deg); }
            }

            #xr-loading-overlay {
                position: fixed;
                inset: 0;
                z-index: 99999;
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(10, 15, 30, 0.72);
                backdrop-filter: blur(6px);
            }

            .xr-loader-card {
                min-width: 280px;
                max-width: 90vw;
                border-radius: 16px;
                padding: 28px 24px;
                background: #0f172a;
                border: 1px solid rgba(148, 163, 184, 0.18);
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35);
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
            }

            .xr-loader-logo-wrap {
                width: 104px;
                height: 104px;
                margin-bottom: 20px;
                border-radius: 16px;
                background: transparent;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 10px;
                box-shadow: none;
            }

            .xr-loader-logo {
                width: 84px;
                height: 84px;
                object-fit: contain;
                display: block;
                max-width: 100%;
                max-height: 100%;
            }

            .xr-loader-spinner-wrap {
                position: relative;
                width: 70px;
                height: 70px;
                margin-bottom: 18px;
            }

            .xr-loader-spinner,
            .xr-loader-spinner-reverse {
                position: absolute;
                inset: 0;
                margin: auto;
                border-radius: 9999px;
                border-style: solid;
                border-color: white;
            }

            .xr-loader-spinner {
                width: 64px;
                height: 64px;
                border-width: 4px;
                border-top-color: transparent;
                animation: xr-spin 1s linear infinite;
            }

            .xr-loader-spinner-reverse {
                width: 40px;
                height: 40px;
                border-width: 4px;
                border-bottom-color: transparent;
                animation: xr-spin-reverse 0.9s linear infinite;
                opacity: 0.85;
            }

            .xr-loader-title {
                color: #f8fafc;
                font-size: 1rem;
                font-weight: 600;
                margin: 0 0 6px 0;
            }

            .xr-loader-subtitle {
                color: #cbd5e1;
                font-size: 0.875rem;
                margin: 0;
            }
        `;
        document.head.appendChild(style);
    }

    function getLoaderConfig() {
        return window.XRLoaderConfig || {};
    }

    const xrLoaderState = {
        mode: null,
        keepVisible: false,
    };

    function getPreloadedLogo() {
        return document.getElementById("xr-preloaded-loader-logo");
    }

    function buildLoaderLogo() {
        const config = getLoaderConfig();
        const logoUrl = config.logoUrl || "/static/admin/img/XRTOURGUIDE.png";
        const preloaded = getPreloadedLogo();

        if (preloaded && preloaded.complete && preloaded.naturalWidth > 0) {
            const clone = preloaded.cloneNode(true);
            clone.removeAttribute("id");
            clone.removeAttribute("style");
            clone.removeAttribute("aria-hidden");
            clone.className = "xr-loader-logo";
            clone.alt = "XR Tour Guide";
            return clone;
        }

        const img = document.createElement("img");
        img.className = "xr-loader-logo";
        img.alt = "XR Tour Guide";
        img.src = logoUrl;
        img.addEventListener("error", function () {
            console.warn("XR loader logo not found at:", logoUrl);
        });
        return img;
    }

    function removeLoader() {
        const existing = document.getElementById("xr-loading-overlay");
        if (existing) {
            existing.remove();
        }
    }

    function showLoader(message, submessage, options) {
        removeLoader();

        const title = message || "Processing...";
        const subtitle = submessage || "Please wait while the operation completes.";
        const keepVisible = !!(options && options.keepVisible);
        const mode = (options && options.mode) || null;

        xrLoaderState.mode = mode;
        xrLoaderState.keepVisible = keepVisible;

        const overlay = document.createElement("div");
        overlay.id = "xr-loading-overlay";

        const card = document.createElement("div");
        card.className = "xr-loader-card";

        const logoWrap = document.createElement("div");
        logoWrap.className = "xr-loader-logo-wrap";
        logoWrap.appendChild(buildLoaderLogo());

        const spinnerWrap = document.createElement("div");
        spinnerWrap.className = "xr-loader-spinner-wrap";
        spinnerWrap.innerHTML = `
            <div class="xr-loader-spinner"></div>
            <div class="xr-loader-spinner-reverse"></div>
        `;

        const titleEl = document.createElement("p");
        titleEl.className = "xr-loader-title";
        titleEl.textContent = title;

        const subtitleEl = document.createElement("p");
        subtitleEl.className = "xr-loader-subtitle";
        subtitleEl.textContent = subtitle;

        card.appendChild(logoWrap);
        card.appendChild(spinnerWrap);
        card.appendChild(titleEl);
        card.appendChild(subtitleEl);
        overlay.appendChild(card);

        document.body.appendChild(overlay);
    }

    function bindFormLoaders() {
        document.querySelectorAll("form").forEach(function (form) {
            if (form.dataset.xrLoaderBound === "1") {
                return;
            }

            form.dataset.xrLoaderBound = "1";

            form.addEventListener("submit", function () {
                const message = form.dataset.loaderText || "Processing...";
                const submessage = form.dataset.loaderSubtext || "Please wait while the operation completes.";
                const keepVisible = form.dataset.loaderKeepVisibile === "true";

                showLoader(message, submessage, {
                    mode: "form",
                    keepVisible: keepVisible,
                });
            });
        });
    }

    function bindLinkLoaders() {
        document.querySelectorAll("[data-loader-link='true']").forEach(function (link) {
            if (link.dataset.xrLoaderBound === "1") {
                return;
            }

            link.dataset.xrLoaderBound = "1";

            link.addEventListener("click", function () {
                const message = link.dataset.loaderText || "Preparing export...";
                const submessage = link.dataset.loaderSubtext || "Please wait while the archive is being generated.";
                showLoader(message, submessage);

                // fallback: se il browser non naviga (download file), almeno non lascia il loader per sempre
                const hideAfter = parseInt(link.dataset.loaderHideAfter || "25000", 10);
                window.setTimeout(removeLoader, hideAfter);
            });
        });
    }

    bindFormLoaders();
    bindLinkLoaders();

    window.addEventListener("pageshow", removeLoader);
    window.addEventListener("focus", function () {
        // utile quando il browser mostra il dialog di download
        window.setTimeout(removeLoader, 800);
    });
});