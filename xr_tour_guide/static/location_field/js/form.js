var SequentialLoader = function () {
    var SL = {
        loadJS: function (src, onload) {
            this._load_pending.push({ src: src, onload: onload });

            if (!this._loading) {
                this._loading = true;
                this.loadNextJS();
            }
        },

        loadNextJS: function () {
            var next = this._load_pending.shift();

            if (next == undefined) {
                this._loading = false;
                return;
            }

            if (this._load_cache[next.src] != undefined) {
                next.onload();
                this.loadNextJS();
                return;
            } else {
                this._load_cache[next.src] = 1;
            }

            var el = document.createElement("script");
            el.type = "application/javascript";
            el.src = next.src;

            var self = this;
            el.onload = function () {
                next.onload();
                self.loadNextJS();
            };

            document.body.appendChild(el);
        },

        _loading: false,
        _load_pending: [],
        _load_cache: {},
    };

    return {
        loadJS: SL.loadJS.bind(SL),
    };
};

!(function ($) {
    var LocationFieldCache = {
        load: [],
        onload: {},
        isLoading: false,
    };

    var LocationFieldResourceLoader;

    function isNodeAttached(node) {
        return !!(
            node &&
            node.isConnected &&
            document.body &&
            document.body.contains(node)
        );
    }

    function isEmptyInlineLocationField(el) {
        var $el = $(el);
        var name = $el.attr("name") || "";
        var id = $el.attr("id") || "";

        return (
            $el.closest(".empty-form").length > 0 ||
            name.indexOf("__prefix__") !== -1 ||
            id.indexOf("__prefix__") !== -1
        );
    }

    function unobserveLocationField(inputEl) {
        if (inputEl) {
            $(inputEl).removeAttr("data-location-field-observed");
        }
    }

    $.locationField = function (options) {
        var LocationField = {
            options: $.extend(
                {
                    provider: "google",
                    providerOptions: {
                        google: {
                            api: "//maps.google.com/maps/api/js",
                            mapType: "ROADMAP",
                        },
                    },
                    searchProvider: "google",
                    id: "map",
                    latLng: "0,0",
                    mapOptions: {
                        zoom: 9,
                    },
                    basedFields: $(),
                    inputField: $(),
                    suffix: "",
                    path: "",
                    fixMarker: true,
                },
                options
            ),

            providers: /google|openstreetmap|mapbox/,
            searchProviders: /google|yandex|nominatim|addok/,

            render: function () {
                this.$id = $("#" + this.options.id);

                if (!this.$id.length) {
                    unobserveLocationField(
                        this.options.inputField && this.options.inputField.get
                            ? this.options.inputField.get(0)
                            : null
                    );
                    return;
                }

                if (!this.providers.test(this.options.provider)) {
                    this.error(
                        "render failed, invalid map provider: " +
                        this.options.provider
                    );
                    return;
                }

                if (!this.searchProviders.test(this.options.searchProvider)) {
                    this.error(
                        "render failed, invalid search provider: " +
                        this.options.searchProvider
                    );
                    return;
                }

                var self = this;

                this.loadAll(function () {
                    var mapElement = self.$id.get(0);

                    if (!isNodeAttached(mapElement)) {
                        unobserveLocationField(
                            self.options.inputField &&
                                self.options.inputField.get
                                ? self.options.inputField.get(0)
                                : null
                        );
                        return;
                    }

                    var mapOptions = self._getMapOptions();
                    var map;

                    try {
                        map = self._getMap(mapOptions);
                    } catch (e) {
                        console.error(
                            "LocationField map init failed:",
                            e,
                            self.options.id
                        );
                        unobserveLocationField(
                            self.options.inputField &&
                                self.options.inputField.get
                                ? self.options.inputField.get(0)
                                : null
                        );
                        return;
                    }

                    if (!map) {
                        unobserveLocationField(
                            self.options.inputField &&
                                self.options.inputField.get
                                ? self.options.inputField.get(0)
                                : null
                        );
                        return;
                    }

                    var marker = self._getMarker(map, mapOptions.center);

                    mapElement._locationFieldMap = map;

                    if (mapElement && window.L && L.DomEvent) {
                        L.DomEvent.disableClickPropagation(mapElement);
                        L.DomEvent.disableScrollPropagation(mapElement);

                        L.DomEvent.on(
                            mapElement,
                            "mousedown touchstart pointerdown dblclick contextmenu",
                            L.DomEvent.stopPropagation
                        );

                        if (map._controlContainer) {
                            L.DomEvent.disableClickPropagation(map._controlContainer);
                            L.DomEvent.on(
                                map._controlContainer,
                                "mousedown touchstart pointerdown dblclick contextmenu",
                                L.DomEvent.stopPropagation
                            );
                        }
                    }

                    function refreshMapSize() {
                        if (!mapElement || mapElement.offsetParent === null) {
                            return;
                        }

                        requestAnimationFrame(function () {
                            map.invalidateSize({
                                pan: false,
                                debounceMoveend: true,
                            });
                        });
                    }

                    map.whenReady(function () {
                        refreshMapSize();
                        setTimeout(refreshMapSize, 150);
                        setTimeout(refreshMapSize, 400);
                    });

                    if (
                        self.options.provider == "google" &&
                        self.options.fixMarker
                    ) {
                        self.__fixMarker();
                    }

                    self._watchBasedFields(map, marker);
                });
            },

            fill: function (latLng) {
                this.options.inputField.val(latLng.lat + "," + latLng.lng);
            },

            search: function (map, marker, address) {
                if (this.options.searchProvider === "google") {
                    var provider = new GeoSearch.GoogleProvider({
                        apiKey: this.options.providerOptions.google.apiKey,
                    });
                    provider.search({ query: address }).then((data) => {
                        if (data.length > 0) {
                            var result = data[0],
                                latLng = new L.LatLng(result.y, result.x);

                            marker.setLatLng(latLng);
                            map.panTo(latLng);
                        }
                    });
                } else if (this.options.searchProvider === "yandex") {
                    var url =
                        "https://geocode-maps.yandex.ru/1.x/?format=json&geocode=" +
                        address;

                    if (
                        typeof this.options.providerOptions.yandex.apiKey !==
                        "undefined"
                    ) {
                        url +=
                            "&apikey=" +
                            this.options.providerOptions.yandex.apiKey;
                    }

                    var request = new XMLHttpRequest();
                    request.open("GET", url, true);

                    request.onload = function () {
                        if (request.status >= 200 && request.status < 400) {
                            var data = JSON.parse(request.responseText);
                            var pos =
                                data.response.GeoObjectCollection.featureMember[0].GeoObject.Point.pos.split(
                                    " "
                                );
                            var latLng = new L.LatLng(pos[1], pos[0]);
                            marker.setLatLng(latLng);
                            map.panTo(latLng);
                        } else {
                            console.error("Yandex geocoder error response");
                        }
                    };

                    request.onerror = function () {
                        console.error("Check connection to Yandex geocoder");
                    };

                    request.send();
                } else if (this.options.searchProvider === "addok") {
                    var url =
                        "https://api-adresse.data.gouv.fr/search/?limit=1&q=" +
                        address;

                    var request = new XMLHttpRequest();
                    request.open("GET", url, true);

                    request.onload = function () {
                        if (request.status >= 200 && request.status < 400) {
                            var data = JSON.parse(request.responseText);
                            var pos = data.features[0].geometry.coordinates;
                            var latLng = new L.LatLng(pos[1], pos[0]);
                            marker.setLatLng(latLng);
                            map.panTo(latLng);
                        } else {
                            console.error("Addok geocoder error response");
                        }
                    };

                    request.onerror = function () {
                        console.error("Check connection to Addok geocoder");
                    };

                    request.send();
                } else if (this.options.searchProvider === "nominatim") {
                    var url =
                        "//nominatim.openstreetmap.org/search?format=json&q=" +
                        address;

                    var request = new XMLHttpRequest();
                    request.open("GET", url, true);

                    request.onload = function () {
                        if (request.status >= 200 && request.status < 400) {
                            var data = JSON.parse(request.responseText);
                            if (data.length > 0) {
                                var pos = data[0];
                                var latLng = new L.LatLng(pos.lat, pos.lon);
                                marker.setLatLng(latLng);
                                map.panTo(latLng);
                            } else {
                                console.error(
                                    address + ": not found via Nominatim"
                                );
                            }
                        } else {
                            console.error("Nominatim geocoder error response");
                        }
                    };

                    request.onerror = function () {
                        console.error("Check connection to Nominatim geocoder");
                    };

                    request.send();
                }
            },

            loadAll: function (onload) {
                this.$id.html("Loading...");

                if (LocationFieldResourceLoader == undefined) {
                    LocationFieldResourceLoader = SequentialLoader();
                }

                this.load.loader = LocationFieldResourceLoader;
                this.load.path = this.options.path;

                var self = this;

                this.load.common(function () {
                    var mapProvider = self.options.provider,
                        onLoadMapProvider = function () {
                            var searchProvider =
                                self.options.searchProvider +
                                "SearchProvider",
                                onLoadSearchProvider = function () {
                                    self.$id.html("");
                                    onload();
                                };

                            if (
                                self.load[searchProvider] != undefined
                            ) {
                                self.load[searchProvider](
                                    self.options.providerOptions[
                                    self.options.searchProvider
                                    ] || {},
                                    onLoadSearchProvider
                                );
                            } else {
                                onLoadSearchProvider();
                            }
                        };

                    if (self.load[mapProvider] != undefined) {
                        self.load[mapProvider](
                            self.options.providerOptions[mapProvider] || {},
                            onLoadMapProvider
                        );
                    } else {
                        onLoadMapProvider();
                    }
                });
            },

            load: {
                google: function (options, onload) {
                    var js = [
                        this.path + "/@googlemaps/js-api-loader/index.min.js",
                        this.path + "/Leaflet.GoogleMutant.js",
                    ];

                    this._loadJSList(js, function () {
                        const loader = new google.maps.plugins.loader.Loader({
                            apiKey: options.apiKey,
                            version: "weekly",
                        });
                        loader.load().then(() => onload());
                    });
                },

                googleSearchProvider: function (options, onload) {
                    onload();
                },

                yandexSearchProvider: function (options, onload) {
                    onload();
                },

                mapbox: function (options, onload) {
                    onload();
                },

                openstreetmap: function (options, onload) {
                    onload();
                },

                common: function (onload) {
                    var self = this,
                        js = [
                            this.path + "/leaflet/leaflet.js",
                            this.path + "/leaflet-geosearch/geosearch.umd.js",
                        ],
                        css = [this.path + "/leaflet/leaflet.css"];

                    this._loadCSSList(css, function () {
                        self._loadJSList(js, onload);
                    });
                },

                _loadJS: function (src, onload) {
                    this.loader.loadJS(src, onload);
                },

                _loadJSList: function (srclist, onload) {
                    this.__loadList(this._loadJS, srclist, onload);
                },

                _loadCSS: function (src, onload) {
                    if (LocationFieldCache.onload[src] != undefined) {
                        onload();
                    } else {
                        LocationFieldCache.onload[src] = 1;
                        onloadCSS(loadCSS(src), onload);
                    }
                },

                _loadCSSList: function (srclist, onload) {
                    this.__loadList(this._loadCSS, srclist, onload);
                },

                __loadList: function (fn, srclist, onload) {
                    if (srclist.length > 1) {
                        for (var i = 0; i < srclist.length - 1; ++i) {
                            fn.call(this, srclist[i], function () { });
                        }
                    }

                    fn.call(this, srclist[srclist.length - 1], onload);
                },
            },

            error: function (message) {
                console.log(message);
                this.$id.html(message);
            },

            _getMap: function (mapOptions) {
                var mapContainer = this.$id.get(0);

                if (!isNodeAttached(mapContainer)) {
                    return null;
                }

                var map = new L.Map(mapContainer, mapOptions), layer;

                if (this.options.provider == "google") {
                    layer = new L.gridLayer.googleMutant({
                        type: this.options.providerOptions.google.mapType.toLowerCase(),
                    });
                } else if (this.options.provider == "openstreetmap") {
                    layer = new L.tileLayer(
                        "//{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                        { 
                            maxZoom: 18,
                            updateWhenIdle: false,
                            updateWhenZooming: false,
                            keepBuffer: 2,
                            reuseTiles: true 
                        }
                    );
                } else if (this.options.provider == "mapbox") {
                    layer = new L.tileLayer(
                        "https://api.mapbox.com/styles/v1/{id}/tiles/{z}/{x}/{y}?access_token={accessToken}",
                        {
                            maxZoom: 18,
                            accessToken:
                                this.options.providerOptions.mapbox.access_token,
                            id: "mapbox/streets-v11",
                        }
                    );
                }

                map.addLayer(layer);
                // map._deferredBaseLayer = layer;
                return map;
            },

            _getMapOptions: function () {
                return $.extend(this.options.mapOptions, {
                    center: this._getLatLng(),
                });
            },

            // _getLatLng: function () {
            //     var l = this.options.latLng.split(",").map(parseFloat);
            //     return new L.LatLng(l[0], l[1]);
            // },

            _getLatLng: function () {
                var raw = (this.options.latLng || "").trim();
                var romeLat = 41.9028;
                var romeLng = 12.4964;

                if (!raw || raw === "0.0, 0.0" || raw === "0,0" || raw === "0.0,0.0") {
                    return new L.LatLng(romeLat, romeLng);
                }

                var l = raw.split(",").map(function (value) {
                    return parseFloat(String(value).trim());
                });

                if (!isFinite(l[0]) || !isFinite(l[1])) {
                    return new L.LatLng(romeLat, romeLng);
                }

                return new L.LatLng(l[0], l[1]);
            },

            _getMarker: function (map, center) {
                var self = this,
                    markerOptions = {
                        draggable: true,
                    };

                var marker = L.marker(center, markerOptions).addTo(map);

                marker.on("dragend move", function () {
                    self.fill(this.getLatLng());
                });

                map.on("click", function (e) {
                    marker.setLatLng(e.latlng);
                });

                return marker;
            },

            _watchBasedFields: function (map, marker) {
                var self = this,
                    basedFields = this.options.basedFields,
                    onchangeTimer,
                    onchange = function () {
                        var values = basedFields.map(function () {
                            var value = $(this).val();
                            return value === "" ? null : value;
                        });
                        var address = values.toArray().join(", ");
                        clearTimeout(onchangeTimer);
                        onchangeTimer = setTimeout(function () {
                            self.search(map, marker, address);
                        }, 300);
                    };

                basedFields.each(function () {
                    var el = $(this);

                    if (el.is("select")) {
                        el.change(onchange);
                    } else {
                        el.keyup(onchange);
                    }
                });
            },

            __fixMarker: function () {
                $(".leaflet-map-pane").css("z-index", "2 !important");
                $(".leaflet-google-layer").css("z-index", "1 !important");
            },
        };

        return {
            render: LocationField.render.bind(LocationField),
        };
    };

    function enableLocationField(inputEl) {
        var el = $(inputEl);

        if (!inputEl || !isNodeAttached(el.get(0))) {
            unobserveLocationField(inputEl);
            return;
        }

        var name = el.attr("name"),
            options = el.data("location-field-options");

        if (!name || !options) {
            unobserveLocationField(inputEl);
            return;
        }

        var basedFields =
            options.field_options && options.field_options.based_fields
                ? options.field_options.based_fields.slice()
                : [],
            pluginOptions = {
                id: "map_" + name,
                inputField: el,
                latLng: el.val() || "0,0",
                suffix: options["search.suffix"],
                path: options["resources.root_path"],
                provider: options["map.provider"],
                searchProvider: options["search.provider"],
                providerOptions: {
                    google: {
                        api: options["provider.google.api"],
                        apiKey: options["provider.google.api_key"],
                        mapType: options["provider.google.map_type"],
                    },
                    mapbox: {
                        access_token: options["provider.mapbox.access_token"],
                    },
                    yandex: {
                        apiKey: options["provider.yandex.api_key"],
                    },
                },
                mapOptions: {
                    zoom: options["map.zoom"],
                },
            };

        var prefixNumber;

        try {
            prefixNumber = name.match(/-(\d+)-/)[1];
        } catch (e) { }

        if (options.field_options && options.field_options.prefix) {
            var prefix = options.field_options.prefix;

            if (prefixNumber != null) {
                prefix = prefix.replace(/__prefix__/, prefixNumber);
            }

            basedFields = basedFields.map(function (n) {
                return prefix + n;
            });
        }

        pluginOptions.basedFields = $(basedFields.map(function (n) {
            return "#id_" + n;
        }).join(","));

        var mapElement = document.getElementById(pluginOptions.id);
        if (!isNodeAttached(mapElement)) {
            unobserveLocationField(inputEl);
            return;
        }

        $.locationField(pluginOptions).render();
    }

    function dataLocationFieldObserver(callback) {
        function findAndEnableDataLocationFields() {
            var dataLocationFields = $("input[data-location-field-options]");

            dataLocationFields
                .filter(function () {
                    return !isEmptyInlineLocationField(this);
                })
                .filter(":not([data-location-field-observed])")
                .each(function () {
                    if (!isNodeAttached(this)) {
                        return;
                    }

                    $(this).attr("data-location-field-observed", true);
                    callback.call(this);
                });
        }

        var observer = new MutationObserver(function () {
            findAndEnableDataLocationFields();
        });

        var container = document.documentElement || document.body;

        $(container).ready(function () {
            findAndEnableDataLocationFields();
        });

        observer.observe(container, {
            attributes: true,
            childList: true,
            subtree: true,
        });
    }

    dataLocationFieldObserver(function () {
        enableLocationField(this);
    });
})(jQuery || django.jQuery);

(function (w) {
    "use strict";
    var loadCSS = function (href, before, media) {
        var doc = w.document;
        var ss = doc.createElement("link");
        var ref;

        if (before) {
            ref = before;
        } else {
            var refs = (doc.body || doc.getElementsByTagName("head")[0]).childNodes;
            ref = refs[refs.length - 1];
        }

        var sheets = doc.styleSheets;
        ss.rel = "stylesheet";
        ss.href = href;
        ss.media = "only x";

        ref.parentNode.insertBefore(ss, before ? ref : ref.nextSibling);

        var onloadcssdefined = function (cb) {
            var resolvedHref = ss.href;
            var i = sheets.length;
            while (i--) {
                if (sheets[i].href === resolvedHref) {
                    return cb();
                }
            }
            setTimeout(function () {
                onloadcssdefined(cb);
            });
        };

        ss.onloadcssdefined = onloadcssdefined;
        onloadcssdefined(function () {
            ss.media = media || "all";
        });

        return ss;
    };

    if (typeof module !== "undefined") {
        module.exports = loadCSS;
    } else {
        w.loadCSS = loadCSS;
    }
})(typeof global !== "undefined" ? global : this);

function onloadCSS(ss, callback) {
    ss.onload = function () {
        ss.onload = null;
        if (callback) {
            callback.call(ss);
        }
    };

    if ("isApplicationInstalled" in navigator && "onloadcssdefined" in ss) {
        ss.onloadcssdefined(callback);
    }
}