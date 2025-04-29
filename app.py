from flask import Flask, Response, render_template, redirect, send_file, request, jsonify
import requests
import schedule
import time
import threading
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import io
import urllib.parse
import os
import logging
import redis
from redis.exceptions import ConnectionError, RedisError
from flask_compress import Compress
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
Compress(app)  # Abilita compressione Gzip
metrics = PrometheusMetrics(app)  # Metriche Prometheus

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurazione Pastebin
pastebin_url = "https://pastebin.com/raw/2JXd4cDJ"
pastebin_api_key = os.getenv("PASTEBIN_API_KEY", "hORVwXV_xxvjnW4B-mhabsU71Da32Idk")
pastebin_dev_key = os.getenv("PASTEBIN_DEV_KEY", "hORVwXV_xxvjnW4B-mhabsU71Da32Idk")
pastebin_username = os.getenv("PASTEBIN_USERNAME", "Mariovio")
pastebin_password = os.getenv("PASTEBIN_PASSWORD", "jinjo1-wagjev-hoTdon")
pastebin_paste_key = "2JXd4cDJ"
pastebin_user_key = None

# Configurazione Redis
CACHE_FILE = "/tmp/playlist.m3u"  # Percorso per fallback su disco
redis_client = None
try:
    redis_host = os.getenv("REDIS_HOST")
    redis_port = os.getenv("REDIS_PORT", "6379")
    if not redis_host:
        raise ValueError("REDIS_HOST non configurato")
    redis_client = redis.Redis(
        host=redis_host,
        port=int(redis_port),
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5
    )
    # Test connessione
    redis_client.ping()
    add_log("Connessione a Redis riuscita")
except (ConnectionError, ValueError, RedisError) as e:
    add_log(f"Errore connessione Redis: {e}. Cache disabilitata, uso fallback su disco")
    redis_client = None

# Variabili per lo stato
merged_playlist = "#EXTM3U\n"
last_update = None
total_channels = 0
m3u_status = []
update_message = None
update_time = 0
channels = []
logs = []
epg_url = ""

def create_session():
    """Crea una sessione requests con retry."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def add_log(message):
    """Aggiunge un messaggio ai log."""
    global logs
    logs.append(f"{datetime.now()}: {message}")
    logs = logs[-50:]
    logger.info(message)

def save_to_cache():
    """Salva la playlist in cache (Redis o disco)."""
    try:
        if redis_client:
            redis_client.set("playlist", merged_playlist, ex=3600)  # Cache per 1 ora
            add_log("Playlist salvata in cache Redis")
        else:
            with open(CACHE_FILE, "w") as f:
                f.write(merged_playlist)
            add_log("Playlist salvata su disco come fallback")
    except RedisError as e:
        add_log(f"Errore salvataggio cache Redis: {e}")
        with open(CACHE_FILE, "w") as f:
            f.write(merged_playlist)
        add_log("Playlist salvata su disco come fallback")
    except Exception as e:
        add_log(f"Errore salvataggio cache: {e}")

def get_from_cache():
    """Recupera la playlist dalla cache (Redis o disco)."""
    try:
        if redis_client:
            cached = redis_client.get("playlist")
            if cached:
                add_log("Playlist caricata da cache Redis")
                return cached
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                add_log("Playlist caricata da disco")
                return f.read()
        return None
    except RedisError as e:
        add_log(f"Errore recupero cache Redis: {e}")
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                add_log("Playlist caricata da disco")
                return f.read()
        return None
    except Exception as e:
        add_log(f"Errore recupero cache: {e}")
        return None

def get_m3u_urls():
    """Recupera la lista degli URL M3U dal Pastebin."""
    try:
        session = create_session()
        add_log(f"Tentativo di recupero della lista M3U da {pastebin_url}")
        response = session.get(pastebin_url, timeout=30)
        if response.status_code == 200:
            urls = [url.strip() for url in response.text.splitlines() if url.strip() and not url.strip().startswith("#")]
            add_log(f"Recuperati {len(urls)} URL M3U dal Pastebin")
            return urls
        else:
            add_log(f"Errore nel recupero del Pastebin: Stato {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        add_log(f"Errore nel recupero del Pastebin: {e}")
        return []

def validate_channel_url(url):
    """Verifica se un URL di un canale è accessibile e misura la latenza."""
    try:
        session = create_session()
        start_time = time.time()
        response = session.head(url, timeout=10, allow_redirects=True)
        latency = (time.time() - start_time) * 1000  # ms
        valid = response.status_code == 200
        return valid, {"latency": latency}
    except requests.exceptions.RequestException:
        return False, {"latency": None}

def update_playlist():
    """Aggiorna la playlist M3U unendo gli URL dal Pastebin."""
    global merged_playlist, last_update, total_channels, m3u_status, update_message, update_time, channels
    start_time = time.time()
    merged_playlist = f"#EXTM3U tvg-url=\"{epg_url}\"\n" if epg_url else "#EXTM3U\n"
    seen_urls = set()
    m3u_status = []
    channels = []
    session = create_session()
    m3u_urls = get_m3u_urls()

    if not m3u_urls:
        add_log("Nessun URL M3U valido recuperato dal Pastebin")
        m3u_status.append(("Nessun URL", "Errore: Pastebin non accessibile", 0))
        update_message = "Errore: Pastebin non accessibile"
        update_time = time.time() - start_time
        save_to_cache()
        return

    valid_channels = 0
    total_attempts = 0
    for url in m3u_urls:
        try:
            add_log(f"Tentativo di recupero M3U da {url}")
            response = session.get(url, timeout=30)
            if response.status_code == 200:
                lines = response.text.splitlines()
                if not lines:
                    add_log(f"Errore: Contenuto vuoto da {url}")
                    m3u_status.append((url, "Vuoto", 0))
                    continue
                channel_count = 0
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if line.startswith("#EXTINF"):
                        j = i + 1
                        channel_url = None
                        while j < len(lines):
                            next_line = lines[j].strip()
                            if next_line and not next_line.startswith("#"):
                                channel_url = next_line
                                break
                            j += 1
                        if channel_url and channel_url not in seen_urls:
                            name = line.split(',', 1)[-1] if ',' in line else "Unknown"
                            group = "Default"
                            language = "Unknown"
                            if 'group-title="' in line:
                                group = line.split('group-title="')[1].split('"')[0]
                            if 'tvg-language="' in line:
                                language = line.split('tvg-language="')[1].split('"')[0]
                            merged_playlist += line + '\n'
                            merged_playlist += channel_url + '\n'
                            seen_urls.add(channel_url)
                            valid, quality = validate_channel_url(channel_url)
                            channels.append({
                                "name": name,
                                "url": channel_url,
                                "source": url,
                                "group": group,
                                "language": language,
                                "valid": valid,
                                "quality": quality
                            })
                            channel_count += 1
                            total_attempts += 1
                            if valid:
                                valid_channels += 1
                            i = j
                        else:
                            if not channel_url:
                                add_log(f"Nessun URL valido trovato dopo #EXTINF: {line}")
                            else:
                                add_log(f"Canale duplicato scartato: {channel_url}")
                    i += 1
                status = "Funzionante" if channel_count > 0 else "Nessun canale valido"
                add_log(f"Successo: Aggiunto contenuto da {url} (Canali: {channel_count})")
                m3u_status.append((url, status, channel_count))
            else:
                add_log(f"Errore nel recupero di {url}: Stato {response.status_code}")
                m3u_status.append((url, f"Errore: Stato {response.status_code}", 0))
        except requests.exceptions.RequestException as e:
            add_log(f"Errore nel recupero di {url}: {e}")
            m3u_status.append((url, f"Errore: {str(e)}", 0))
        except Exception as e:
            add_log(f"Errore imprevisto durante il recupero di {url}: {e}")
            m3u_status.append((url, f"Errore imprevisto: {str(e)}", 0))

    total_channels = merged_playlist.count("#EXTINF")
    last_update = datetime.now()
    update_time = time.time() - start_time
    valid_percentage = (valid_channels / total_attempts * 100) if total_attempts > 0 else 0
    update_message = f"Playlist rigenerata: {total_channels} canali ({valid_percentage:.1f}% funzionanti)"
    add_log(f"Playlist aggiornata: {last_update} (Canali totali: {total_channels}, Tempo: {update_time:.2f}s)")
    save_to_cache()

@app.route("/test", methods=["POST"])
def test_m3u():
    url = request.form.get("test_url")
    if not url:
        return jsonify({"error": "URL non fornito"}), 400
    session = create_session()
    try:
        add_log(f"Test URL M3U: {url}")
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            lines = response.text.splitlines()
            if not lines:
                add_log(f"Test fallito: Contenuto vuoto da {url}")
                return jsonify({"status": "Vuoto", "channels": 0})
            channel_count = sum(1 for line in lines if line.strip().startswith("#EXTINF"))
            add_log(f"Test riuscito: {url} ({channel_count} canali)")
            return jsonify({"status": "Funzionante", "channels": channel_count})
        else:
            add_log(f"Test fallito: Stato {response.status_code} per {url}")
            return jsonify({"status": f"Errore: Stato {response.status_code}", "channels": 0})
    except requests.exceptions.RequestException as e:
        add_log(f"Test fallito: Errore {e} per {url}")
        return jsonify({"status": f"Errore: {str(e)}", "channels": 0})
    except Exception as e:
        add_log(f"Errore imprevisto nel test di {url}: {e}")
        return jsonify({"status": f"Errore imprevisto: {str(e)}", "channels": 0}), 500

@app.route("/update_pastebin", methods=["POST"])
def update_pastebin():
    global pastebin_user_key
    new_urls = request.form.get("pastebin_urls")
    if not new_urls:
        add_log("Errore: Nessun URL fornito per aggiornare il Pastebin")
        return jsonify({"error": "Nessun URL fornito"}), 400

    try:
        if not pastebin_user_key:
            login_data = {
                "api_dev_key": pastebin_dev_key,
                "api_user_name": pastebin_username,
                "api_user_password": pastebin_password
            }
            response = requests.post("https://pastebin.com/api/api_login.php", data=login_data)
            if response.status_code == 200 and response.text and not response.text.startswith("Bad API request"):
                pastebin_user_key = response.text
                add_log("Login a Pastebin riuscito")
            else:
                add_log(f"Errore nel login a Pastebin: {response.text}")
                return jsonify({"error": f"Errore nel login a Pastebin: {response.text}"}), 500

        paste_data = {
            "api_option": "paste",
            "api_dev_key": pastebin_dev_key,
            "api_user_key": pastebin_user_key,
            "api_paste_key": pastebin_paste_key,
            "api_paste_code": new_urls,
            "api_paste_private": "1",
            "api_paste_name": "M3U URLs",
            "api_paste_format": "text"
        }
        response = requests.post("https://pastebin.com/api/api_post.php", data=paste_data)
        if response.status_code == 200 and "pastebin.com" in response.text:
            add_log("Pastebin aggiornato con successo")
            update_playlist()
            return jsonify({"message": "Pastebin aggiornato con successo"})
        else:
            add_log(f"Errore nell'aggiornamento del Pastebin: {response.text}")
            return jsonify({"error": f"Errore nell'aggiornamento del Pastebin: {response.text}"}), 500
    except requests.exceptions.RequestException as e:
        add_log(f"Errore nell'aggiornamento del Pastebin: {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        add_log(f"Errore imprevisto nell'aggiornamento del Pastebin: {e}")
        return jsonify({"error": f"Errore imprevisto: {str(e)}"}), 500

@app.route("/set_epg", methods=["POST"])
def set_epg():
    global epg_url
    try:
        new_epg_url = request.form.get("epg_url", "").strip()
        epg_url = new_epg_url
        add_log(f"URL EPG configurato: {epg_url}")
        update_playlist()
        return jsonify({"message": f"URL EPG configurato: {epg_url}"})
    except Exception as e:
        add_log(f"Errore nella configurazione dell'EPG: {e}")
        return jsonify({"error": f"Errore: {str(e)}"}), 500

@app.route("/validate_epg", methods=["POST"])
def validate_epg():
    epg_url = request.form.get("epg_url")
    try:
        session = create_session()
        response = session.get(epg_url, timeout=10)
        if response.status_code == 200:
            add_log(f"EPG valido: {epg_url}")
            return jsonify({"message": "EPG valido", "size": len(response.text)})
        else:
            add_log(f"EPG non valido: Stato {response.status_code}")
            return jsonify({"error": f"Stato {response.status_code}"}), 400
    except Exception as e:
        add_log(f"Errore validazione EPG: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/check_channel", methods=["POST"])
def check_channel():
    url = request.form.get("url")
    if not url:
        return jsonify({"error": "URL non fornito"}), 400
    valid, quality = validate_channel_url(url)
    add_log(f"Controllo canale {url}: {'Online' if valid else 'Offline'}, Latenza: {quality['latency'] or 'N/A'} ms")
    return jsonify({"status": "Online" if valid else "Offline", "quality": quality})

@app.route("/export", methods=["POST"])
def export_playlist():
    selected_urls = request.form.getlist("selected_urls")
    if not selected_urls:
        return Response("Errore: Nessun canale selezionato.", mimetype="text/plain")
    custom_playlist = f"#EXTM3U tvg-url=\"{epg_url}\"\n" if epg_url else "#EXTM3U\n"
    for channel in channels:
        if channel["url"] in selected_urls:
            extinf_line = next((line for line in merged_playlist.splitlines() if channel["url"] in line and line.startswith("#EXTINF")), None)
            if extinf_line:
                custom_playlist += extinf_line + '\n'
                custom_playlist += channel["url"] + '\n'
    buffer = io.StringIO(custom_playlist)
    return send_file(
        io.BytesIO(buffer.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name="Custom_Coconut.m3u",
        mimetype="audio/mpegurl"
    )

@app.route("/export_by_group", methods=["POST"])
def export_by_group():
    group = request.form.get("group")
    if not group:
        return Response("Errore: Nessun gruppo selezionato.", mimetype="text/plain")
    custom_playlist = f"#EXTM3U tvg-url=\"{epg_url}\"\n" if epg_url else "#EXTM3U\n"
    for channel in channels:
        if channel["group"] == group:
            extinf_line = next((line for line in merged_playlist.splitlines() if channel["url"] in line and line.startswith("#EXTINF")), None)
            if extinf_line:
                custom_playlist += extinf_line + '\n'
                custom_playlist += channel["url"] + '\n'
    buffer = io.StringIO(custom_playlist)
    return send_file(
        io.BytesIO(buffer.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name=f"Coconut_{group}.m3u",
        mimetype="audio/mpegurl"
    )

@app.route("/redis_status")
def redis_status():
    """Verifica lo stato della connessione Redis."""
    try:
        if redis_client and redis_client.ping():
            return jsonify({"status": "Active"})
        return jsonify({"status": "Inactive"})
    except RedisError:
        return jsonify({"status": "Error"})

schedule.every(1).hours.do(update_playlist)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_scheduler, daemon=True).start()

@app.route("/")
def index():
    try:
        status = "Playlist aggiornata" if total_channels > 0 else "Errore: Nessun canale disponibile"
        valid_percentage = sum(1 for c in channels if c["valid"]) / len(channels) * 100 if channels else 0
        return render_template("index.html",
                              status=status,
                              last_update=last_update,
                              total_channels=total_channels,
                              m3u_status=m3u_status,
                              m3u_link="https://ptv-r1fg.onrender.com/Coconut.m3u",
                              update_message=update_message,
                              update_time=update_time,
                              channels=channels,
                              valid_percentage=valid_percentage,
                              epg_url=epg_url)
    except Exception as e:
        add_log(f"Errore nel rendering della pagina index: {e}")
        return Response(f"Errore interno: {str(e)}", status=500)

@app.route("/Coconut.m3u")
def serve_playlist():
    try:
        cached = get_from_cache()
        if cached:
            return Response(cached, mimetype="audio/mpegurl")
        if merged_playlist.strip() == "#EXTM3U" or merged_playlist.strip() == f"#EXTM3U tvg-url=\"{epg_url}\"":
            return Response("Errore: Nessun canale disponibile. Controlla i log su Render.", mimetype="text/plain")
        return Response(merged_playlist, mimetype="audio/mpegurl")
    except Exception as e:
        add_log(f"Errore nel servire la playlist: {e}")
        return Response(f"Errore interno: {str(e)}", status=500)

@app.route("/regenerate")
def regenerate_playlist():
    try:
        update_playlist()
        return redirect("/")
    except Exception as e:
        add_log(f"Errore nella rigenerazione della playlist: {e}")
        return Response(f"Errore interno: {str(e)}", status=500)

@app.route("/download")
def download_playlist():
    try:
        if merged_playlist.strip() == "#EXTM3U" or merged_playlist.strip() == f"#EXTM3U tvg-url=\"{epg_url}\"":
            return Response("Errore: Nessun canale disponibile.", mimetype="text/plain")
        buffer = io.StringIO(merged_playlist)
        return send_file(
            io.BytesIO(buffer.getvalue().encode('utf-8')),
            as_attachment=True,
            download_name="Coconut.m3u",
            mimetype="audio/mpegurl"
        )
    except Exception as e:
        add_log(f"Errore nel download della playlist: {e}")
        return Response(f"Errore interno: {str(e)}", status=500)

@app.route("/logs")
def get_logs():
    try:
        return jsonify({"logs": logs})
    except Exception as e:
        add_log(f"Errore nel recupero dei log: {e}")
        return jsonify({"error": f"Errore: {str(e)}"}), 500

if __name__ == "__main__":
    try:
        update_playlist()
        app.run(host="0.0.0.0", port=5000)
    except Exception as e:
        add_log(f"Errore avvio applicazione: {e}")
        raise
