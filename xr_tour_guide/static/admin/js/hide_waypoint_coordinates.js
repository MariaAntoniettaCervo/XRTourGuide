(function ($) {
    function toggleFields() {
        var category = $("#id_category").val();

        var tourCoordField = $("#id_coordinates").closest(".form-row, .form-group, .field, .form__field");
        if (category === "GUIDE") {
            tourCoordField.hide();
        } else {
            tourCoordField.show();
        }

        $("div.inline-related").each(function () {
            var $inline = $(this);

            var placeFieldsetInline = $inline
                .find("input[name$='-place'], select[name$='-place']")
                .closest("fieldset.module");

            var coordFieldsetInline = $inline
                .find("input[name$='-coordinates']")
                .closest("fieldset.module");

            if (category === "INDOOR" || category === "GUIDE") {
                placeFieldsetInline.hide();
                coordFieldsetInline.hide();
            } else {
                placeFieldsetInline.show();
                coordFieldsetInline.show();
            }
        });

        var subToursFieldset = $("#id_sub_tours").closest("fieldset.module");

        if (category === "MIXED") {
            subToursFieldset.show();
        } else {
            subToursFieldset.hide();
        }
    }

    function isElementVisible(el) {
        if (!el) {
            return false;
        }

        var style = window.getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") {
            return false;
        }

        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }

    function loadWaypointImages(root, onlyVisible) {
        var scope = root || document;
        var lazyImages = scope.querySelectorAll("img[data-waypoint-lazy-src]");

        lazyImages.forEach(function (img) {
            if (img.getAttribute("data-waypoint-lazy-loaded") === "1") {
                return;
            }

            var gallery = img.closest("[data-waypoint-gallery='1']");
            if (onlyVisible && gallery && !isElementVisible(gallery)) {
                return;
            }

            var src = img.getAttribute("data-waypoint-lazy-src");
            if (!src) {
                return;
            }

            img.setAttribute("src", src);
            img.setAttribute("data-waypoint-lazy-loaded", "1");
            img.removeAttribute("data-waypoint-lazy-src");
        });
    }

    function scheduleWaypointImageLoading(root) {
        var scope = root || document;

        window.requestAnimationFrame(function () {
            loadWaypointImages(scope, true);
        });
    }

    function wakeUpLeafletMap(map) {
        if (!map) {
            return;
        }

        var center = map.getCenter();
        var zoom = map.getZoom();

        map.invalidateSize({ pan: false, debounceMoveend: true });
        map.setView(center, zoom, { animate: false });
    }

    function refreshMapsInContainer(container) {
        if (!container) {
            return;
        }

        container.querySelectorAll(".leaflet-container").forEach(function (mapEl) {
            var map = mapEl._locationFieldMap;
            if (!map || mapEl.offsetParent === null) {
                return;
            }

            wakeUpLeafletMap(map);

            setTimeout(function () {
                wakeUpLeafletMap(map);
            }, 150);
        });
    }

    function scheduleMapWakeUp(container) {
        var scope = container || document;

        requestAnimationFrame(function () {
            refreshMapsInContainer(scope);
        });

        setTimeout(function () {
            refreshMapsInContainer(scope);
        }, 150);
    }

    function protectLeafletFromSortable(root) {
        var scope = root || document;

        $(scope).find(".djn-items.ui-sortable").each(function () {
            var $sortable = $(this);

            try {
                var currentCancel = $sortable.nestedSortable("option", "cancel") || "";
                var leafletCancel = ".leaflet-container, .leaflet-container *, .leaflet-control-container, .leaflet-control-container *";

                if (currentCancel.indexOf(".leaflet-container") !== -1) {
                    return;
                }

                var nextCancel = currentCancel
                    ? currentCancel + ", " + leafletCancel
                    : leafletCancel;

                $sortable.nestedSortable("option", "cancel", nextCancel);
            } catch (e) {
                // sortable non ancora inizializzato
            }
        });
    }

    $(document).ready(function () {
        toggleFields();
        scheduleWaypointImageLoading(document);

        setTimeout(function () {
            protectLeafletFromSortable(document);
            scheduleMapWakeUp(document);
        }, 0);

        $("#id_category").change(function () {
            toggleFields();
            scheduleMapWakeUp(document);
        });

        $(document).on("formset:added", function (event, $row) {
            var rowNode = ($row && $row[0]) || event.target || document;

            toggleFields();
            scheduleWaypointImageLoading(rowNode);

            setTimeout(function () {
                protectLeafletFromSortable(document);
                scheduleMapWakeUp(rowNode);
            }, 0);
        });

        document.addEventListener("click", function () {
            scheduleWaypointImageLoading(document);
        }, true);

        document.addEventListener("transitionend", function (event) {
            scheduleWaypointImageLoading(document);

            var waypointContainer = event.target.closest(".form-group, .inline-related");
            if (!waypointContainer) {
                return;
            }

            if (!waypointContainer.querySelector("input[name$='-coordinates']")) {
                return;
            }

            scheduleMapWakeUp(waypointContainer);
        }, true);

        document.addEventListener("animationend", function () {
            scheduleWaypointImageLoading(document);
        }, true);

        document.addEventListener("click", function (event) {
            var header = event.target.closest("h3.cursor-pointer");
            if (!header) {
                return;
            }

            var waypointContainer = header.closest(".form-group, .inline-related");
            if (!waypointContainer) {
                return;
            }

            if (!waypointContainer.querySelector("input[name$='-coordinates']")) {
                return;
            }

            scheduleMapWakeUp(waypointContainer);
        }, true);

        window.addEventListener("load", function () {
            scheduleMapWakeUp(document);
        });
    });
})(django.jQuery);