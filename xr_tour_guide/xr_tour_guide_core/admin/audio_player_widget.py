import hashlib

from django.core.cache import caches
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _


def render_audio_player(waypoint, location="main"):
    """
    Player audio riusabile: bottone play/pausa in CSS (nessuna emoji), barra di
    avanzamento cliccabile, badge di avviso se la descrizione è stata modificata
    dopo l'ultima generazione confermata.

    waypoint: istanza Waypoint (quello che possiede il file audio_item)
    location: stringa usata per rendere unici gli id HTML quando lo stesso
              waypoint viene mostrato in più punti della pagina (es. vicino
              alla descrizione E nella sezione multimediale), o quando è
              richiamato dalla pagina Tour (introduzione) invece che dal
              Waypoint stesso.
    """
    if not waypoint or not waypoint.pk or not waypoint.audio_item:
        return mark_safe(
            '<div style="display:inline-flex; align-items:center; gap:6px; padding:6px 12px; '
            'border-radius:18px; background:#f3f4f6; color:#6b7280; font-size:13px;">'
            '🔇 ' + str(_('Nessun audio')) +
            '</div>'
        )

    # "file" qui è la CATEGORIA (audio/pdf/video/readme), non il nome file
    # esatto: coerente con get_waypoint_resources, che per un singolo campo
    # come audio_item risolve lui stesso il percorso interno.
    # "&v=" rompe la cache del browser: senza, l'URL resta identico anche
    # quando il file sottostante cambia (es. rigenerato con un altro motore),
    # e il browser continuerebbe a mostrare l'audio vecchio.
    audio_version = caches["redis"].get(f"audio_version:{waypoint.pk}") or "0"
    audio_url = f"/stream_minio_resource/?waypoint={waypoint.pk}&file=audio&v={audio_version}"

    mismatch_badge = ""
    try:
        confirmed_hash = caches["redis"].get(f"audio_confirmed_hash:{waypoint.pk}")
        if confirmed_hash:
            current_hash = hashlib.md5((waypoint.description or "").encode("utf-8")).hexdigest()
            if confirmed_hash != current_hash:
                mismatch_badge = (
                    f'<div data-ai-audio-mismatch-for="{waypoint.pk}" style="display:inline-flex; align-items:center; gap:6px; padding:4px 10px; '
                    'border-radius:14px; background:#fef3c7; color:#92400e; font-size:12px; '
                    'font-weight:600; margin-bottom:6px;">'
                    '⚠️ ' + str(_('Testo modificato dopo la generazione')) +
                    '</div><br>'
                )
    except Exception:
        pass

    # ID unici per posizione: lo stesso waypoint può comparire in più punti
    # della pagina (o essere richiamato dalla pagina Tour) — senza il
    # suffisso "location" avremmo elementi con id duplicati, non validi in HTML.
    uid = f"{location}_{waypoint.pk}"

    return mark_safe(f'''
        {mismatch_badge}
        <div style="display:inline-flex; align-items:center; gap:10px;">
            <button type="button" id="audioToggle_{uid}"
                style="height:36px; width:36px; min-width:36px; border-radius:50%; padding:0;
                       display:flex; align-items:center; justify-content:center;
                       cursor:pointer; border:1px solid #16a34a88; background:#16a34a22;
                       color:#16a34a; transition: all 0.2s ease;">
                <span id="audioPlayIcon_{uid}" style="display:inline-block; margin-left:2px;
                      width:0; height:0; border-top:6px solid transparent; border-bottom:6px solid transparent;
                      border-left:10px solid currentColor;"></span>
                <span id="audioPauseIcon_{uid}" style="display:none; align-items:center; gap:3px;">
                    <span style="width:4px; height:12px; background:currentColor; display:inline-block; border-radius:1px;"></span>
                    <span style="width:4px; height:12px; background:currentColor; display:inline-block; border-radius:1px;"></span>
                </span>
            </button>
            <div id="audioTrack_{uid}" style="width:110px; height:6px; background:#16a34a26;
                 border-radius:3px; position:relative; cursor:pointer;">
                <div id="audioFill_{uid}" style="width:0%; height:100%; background:#16a34a; border-radius:3px;"></div>
            </div>
            <span id="audioTime_{uid}" style="font-size:12px; font-weight:600; color:#16a34a; min-width:70px;">0:00 / 0:00</span>
            <audio id="audioEl_{uid}" src="{audio_url}" preload="metadata" style="display:none;"></audio>
        </div>
        <script>
        (function() {{
            var btn = document.getElementById("audioToggle_{uid}");
            var playIcon = document.getElementById("audioPlayIcon_{uid}");
            var pauseIcon = document.getElementById("audioPauseIcon_{uid}");
            var track = document.getElementById("audioTrack_{uid}");
            var fill = document.getElementById("audioFill_{uid}");
            var timeLabel = document.getElementById("audioTime_{uid}");
            var audio = document.getElementById("audioEl_{uid}");
            if (!btn || btn.dataset.aiPlayerBound) return;
            btn.dataset.aiPlayerBound = "1";

            function formatTime(sec) {{
                if (!isFinite(sec)) return "0:00";
                var m = Math.floor(sec / 60);
                var s = Math.floor(sec % 60).toString().padStart(2, "0");
                return m + ":" + s;
            }}

            function showPlaying(isPlaying) {{
                playIcon.style.display = isPlaying ? "none" : "inline-block";
                pauseIcon.style.display = isPlaying ? "inline-flex" : "none";
            }}

            btn.addEventListener("click", function() {{
                if (audio.paused) {{
                    document.querySelectorAll("audio").forEach(function(a) {{ if (a !== audio) a.pause(); }});
                    audio.play();
                }} else {{
                    audio.pause();
                }}
            }});

            track.addEventListener("click", function(event) {{
                if (!isFinite(audio.duration)) return;
                var rect = track.getBoundingClientRect();
                var ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1);
                audio.currentTime = ratio * audio.duration;
            }});

            audio.addEventListener("play", function() {{ showPlaying(true); }});
            audio.addEventListener("pause", function() {{ showPlaying(false); }});
            audio.addEventListener("ended", function() {{ showPlaying(false); }});
            audio.addEventListener("timeupdate", function() {{
                var pct = isFinite(audio.duration) ? (audio.currentTime / audio.duration) * 100 : 0;
                fill.style.width = pct + "%";
                timeLabel.textContent = formatTime(audio.currentTime) + " / " + formatTime(audio.duration);
            }});
            audio.addEventListener("loadedmetadata", function() {{
                timeLabel.textContent = "0:00 / " + formatTime(audio.duration);
            }});
        }})();
        </script>
    ''')