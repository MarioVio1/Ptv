from flask import Flask, Response, render_template, redirect, request, jsonify
import requests
import schedule
import time
import threading
from datetime import datetime
import os
import logging

app = Flask(__name__)

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurazione Pastebin
pastebin_url = "https://pastebin.com/raw/2JXd4cDJ"  # Sostituisci con il nuovo Pastebin
pastebin_api_key = os.getenv("PASTEBIN_API_KEY", "YOUR_PASTEBIN_API_KEY")
pastebin_dev_key = os.getenv("PASTEBIN_DEV_KEY", "YOUR_PASTEBIN_DEV_KEY")
pastebin_username = os.getenv("PASTEBIN_USERNAME", "Mariovio")
pastebin_password = os.getenv("PASTEBIN_PASSWORD")
pastebin_paste_key = "YOUR_PASTEBIN_KEY"  # Sostituisci con il nuovo Pastebin
pastebin_user_key = None

# URL M3U di fallback
FALLBACK_M3U_URL = "https://iptv-org.github.io/iptv/channels/it.m3u"

# Variabili per lo stato
merged_playlist = "#EXTM3U\n"
last_update = None
total_channels = 0
m3u_status = []
update_message = None
update_time = 0
logs = []
epg_url = ""

def add_log(message):
    """Aggiunge un messaggio ai log."""
    global logs
    logs.append(f"{datetime.now()}: {message}")
    logs = logs[-50:]
    logger.info(message)

def get_m3u_urls():
    """Recupera la lista degli URL M3U dal Pastebin con fallback."""
    try:
        add_log(f"Tentativo di recupero della lista M3U da {pastebin_url}")
        response = requests.get(pastebin_url, timeout=10)
        add_log(f"Risposta Pastebin: Stato {response.status_code}, Contenuto: {response.text[:100]}...")
        if response.status_code == 200:
            urls = [url.strip() for url in response.text.splitlines() if url.strip() and not url.strip().startswith("#")]
            add_log(f"Recuperati {len(urls)} URL M3U dal Pastebin: {urls}")
            return urls if urls else [FALLBACK_M3U_URL]
        else:
            add_log(f"Errore nel recupero del Pastebin: Stato {response.status_code}")
            return [FALLBACK_M3U_URL]
    except Exception as e:
        add_log(f"Errore nel recupero del Pastebin: {e}")
        return [FALLBACK_M3U_URL]

def update_playlist():
    """Aggiorna la playlist M3U unendo gli URL dal Pastebin."""
    global merged_playlist, last_update, total_channels, m3u_status, update_message, update_time
    start_time = time.time()
    merged_playlist = f"#EXTM3U tvg-url=\"{epg_url}\"\n" if epg_url else "#EXTM3U\n"
    seen_urls = set()
    m3u_status = []
    m3u_urls = get_m3u_urls()

    add_log(f"URL M3U da processare: {m3u_urls}")
    if not m3u_urls:
        add_log("Nessun URL M3U valido recuperato")
        m3u_status.append(("Nessun URL", "Errore: Pastebin non accessibile", 0))
        update_message = "Errore: Pastebin non accessibile"
        update_time = time.time() - start_time
        return

    for url in m3u_urls:
        try:
            add_log(f"Tentativo di recupero M3U da {url}")
            response = requests.get(url, timeout=10)
            add_log(f"Risposta M3U {url}: Stato {response.status_code}, Lunghezza: {len(response.text)}")
            if response.status_code == 200:
                lines = response.text.splitlines()
                if not lines:
                    add_log(f"Contenuto vuoto da {url}")
                    m3u_status.append((url, "Vuoto", 0))
                    continue
                channel_count = 0
                i = 0
                while i < len(lines):
                    try:
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
                                merged_playlist += line + '\n'
                                merged_playlist += channel_url + '\n'
                                seen_urls.add(channel_url)
                                channel_count += 1
                            i = j
                        else:
                            i += 1
                    except Exception as e:
                        add_log(f"Errore nel parsing della riga {i} da {url}: {e}")
                        i += 1
                status = "Funzionante" if channel_count > 0 else "Nessun canale valido"
                add_log(f"Successo: Aggiunto contenuto da {url} (Canali: {channel_count})")
                m3u_status.append((url, status, channel_count))
            else:
                add_log(f"Errore nel recupero di {url}: Stato {response.status_code}")
                m3u_status.append((url, f"Errore: Stato {response.status_code}", 0))
        except Exception as e:
            add_log(f"Errore nel recupero di {url}: {e}")
            m3u_status.append((url, f"Errore: {str(e)}", 0))

    total_channels = merged_playlist.count("#EXTINF")
    last_update = datetime.now()
    update_time = time.time() - start_time
    update_message = f"Playlist rigenerata: {total_channels} canali"
    add_log(f"Playlist aggiornata: {last_update} (Canali totali: {total_channels}, Tempo: {update_time:.2f}s)")

@app.route("/update_pastebin", methods=["POST"])
def update_pastebin():
    global pastebin_user_key
    new_urls = request.form.get("pastebin_urls")
    if not new_urls:
        add_log("Errore: Nessun URL fornito per aggiornare il Pastebin")
        return jsonify({"error": "Nessun URL fornito"}), 400

    if not pastebin_password:
        add_log("Errore: PASTEBIN_PASSWORD non configurato")
        return jsonify({"error": "PASTEBIN_PASSWORD non configurato"}), 500

    try:
        if not pastebin_user_key:
            login_data = {
                "api_dev_key": pastebin_dev_key,
                "api_user_name": pastebin_username,
                "api_user_password": pastebin_password
            }
            response = requests.post("https://pastebin.com/api/api_login.php", data=login_data)
            add_log(f"Risposta login Pastebin: Stato {response.status_code}, Testo: {response.text[:100]}")
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
        add_log(f"Risposta update Pastebin: Stato {response.status_code}, Testo: {response.text[:100]}")
        if response.status_code == 200 and "pastebin.com" in response.text:
            add_log("Pastebin aggiornato con successo")
            update_playlist()
            return jsonify({"message": "Pastebin aggiornato con successo"})
        else:
            add_log(f"Errore nell'aggiornamento del Pastebin: {response.text}")
            return jsonify({"error": f"Errore nell'aggiornamento del Pastebin: {response.text}"}), 500
    except Exception as e:
        add_log(f"Errore nell'aggiornamento del Pastebin: {e}")
        return jsonify({"error": str(e)}), 500

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
        return render_template("index.html",
                              status=status,
                              last_update=last_update,
                              total_channels=total_channels,
                              m3u_status=m3u_status,
                              m3u_link="https://YOUR_RENDER_URL.onrender.com/Coconut.m3u",  # Sostituisci con il nuovo URL
                              update_message=update_message,
                              update_time=update_time,
                              epg_url=epg_url)
    except Exception as e:
        add_log(f"Errore nel rendering della pagina index: {e}")
        return Response(f"Errore interno: {str(e)}", status=500)

@app.route("/Coconut.m3u")
def serve_playlist():
    try:
        if merged_playlist.strip() == "#EXTM3U" or merged_playlist.strip() == f"#EXTM3U tvg-url=\"{epg_url}\"":
            return Response("Errore: Nessun canale disponibile. Controlla i log su Render.", mimetype="text/plain")
        return Response(merged_playlist, mimetype="audio/mpegurl")
    except Exception as e:
        add_log(f"Errore nel servire la playlist: {e}")
        return Response(f"Errore interno: {str(e)}", status=500)

@app.route("/regenerate")
def regenerate_playlist():
    try:
        add_log("Inizio rigenerazione playlist")
        update_playlist()
        add_log("Rigenerazione playlist completata")
        return redirect("/")
    except Exception as e:
        add_log(f"Errore nella rigenerazione della playlist: {str(e)}")
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
        add_log("Avvio applicazione")
        update_playlist()
        app.run(host="0.0.0.0", port=5000)
    except Exception as e:
        add_log(f"Errore avvio applicazione: {e}")
        raise
