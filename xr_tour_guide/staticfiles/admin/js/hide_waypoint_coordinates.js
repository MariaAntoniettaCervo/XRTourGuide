// (function($) {
//     $(document).ready(function() {
//         function toggleFields() {
//             var category = $("#id_category").val();

//             var tourCoordField = $("#id_coordinates").closest('.form-row, .form-group, .field, .form__field');
//             if (category === "GUIDE") {
//                 tourCoordField.hide();
//             } else {
//                 tourCoordField.show();
//             }

//             $("div.inline-related").each(function() {
//                 var $inline = $(this);

//                 var placeFieldsetInline = $inline.find("input[name$='-place'], select[name$='-place']")
//                                                 .closest("fieldset.module");

//                 var coordFieldsetInline = $inline.find("input[name$='-coordinates']")
//                                                 .closest("fieldset.module");

//                 if (category === "INDOOR" || category === "GUIDE") {
//                     placeFieldsetInline.hide();
//                     coordFieldsetInline.hide();
//                 } else {
//                     placeFieldsetInline.show();
//                     coordFieldsetInline.show();
//                 }
//             });

//             var subToursFieldset = $("#id_sub_tours").closest("fieldset.module");

//             if (category === "MIXED") {
//                 subToursFieldset.show();
//             } else {
//                 subToursFieldset.hide();
//             }
//         }

//         toggleFields();

//         $("#id_category").change(function() {
//             toggleFields();
//         });

//         $(document).on('formset:added', function(event, $row, formsetName) {
//             toggleFields();
//         });
//     });
// })(django.jQuery);


(function ($) {
    $(document).ready(function () {
        function toggleFields() {
            var category = $("#id_category").val();

            var tourCoordField = $("#id_coordinates").closest('.form-row, .form-group, .field, .form__field');
            if (category === "GUIDE") {
                tourCoordField.hide();
            } else {
                tourCoordField.show();
            }

            $("div.inline-related").each(function () {
                var $inline = $(this);

                var placeFieldsetInline = $inline.find("input[name$='-place'], select[name$='-place']")
                    .closest("fieldset.module");

                var coordFieldsetInline = $inline.find("input[name$='-coordinates']")
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

        toggleFields();
        scheduleWaypointImageLoading(document);

        $("#id_category").change(function () {
            toggleFields();
        });

        $(document).on("formset:added", function (event, $row) {
            toggleFields();
            scheduleWaypointImageLoading(($row && $row[0]) || event.target || document);
        });

        document.addEventListener("click", function () {
            scheduleWaypointImageLoading(document);
        }, true);

        document.addEventListener("transitionend", function () {
            scheduleWaypointImageLoading(document);
        }, true);

        document.addEventListener("animationend", function () {
            scheduleWaypointImageLoading(document);
        }, true);
    });

    function triggerLeafletResize() {
        window.dispatchEvent(new Event("resize"));
    }

    function scheduleLeafletResize() {
        [0, 120, 300, 600].forEach(function (delay) {
            setTimeout(triggerLeafletResize, delay);
        });
    }

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

        scheduleLeafletResize();
    }, true);

    document.addEventListener("transitionend", function (event) {
        var waypointContainer = event.target.closest(".form-group, .inline-related");
        if (!waypointContainer) {
            return;
        }

        if (!waypointContainer.querySelector("input[name$='-coordinates']")) {
            return;
        }

        scheduleLeafletResize();
    }, true);

    $(document).on("formset:added", function () {
        scheduleLeafletResize();
    });

    window.addEventListener("load", function () {
        scheduleLeafletResize();
    });
    
})(django.jQuery);
