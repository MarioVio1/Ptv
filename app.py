from flask import Flask, Response, redirect, send_file, request, jsonify
import requests
import time
import os
import logging
import io
from datetime import datetime

app = Flask(__name__)

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurazione Pastebin
pastebin_url = "https://pastebin.com/raw/2JXd4cDJ"
pastebin_api_key = os.getenv("PASTEBIN_API_KEY", "hORVwXV_xxvjnW4B-mhabsU71Da32Idk")
pastebin_dev_key = os.getenv("PASTEBIN_DEV_KEY", "hORVwXV_xxvjnW4B-mhabsU71Da32Idk")
pastebin_username = os.getenv("PASTEBIN_USERNAME", "Mariovio")
pastebin_password = os.getenv("PASTEBIN_PASSWORD")
pastebin_paste_key = "2JXd4cDJ"
pastebin_user_key = None

# Configurazione cache su disco
CACHE_FILE = "/tmp/playlist.m3u"

# Variabili per lo stato
merged_playlist = "#EXTM3U\n"
last_update = None
total_channels = 0
logs = []

def add_log(message):
    """Aggiunge un messaggio ai log."""
    global logs
    logs.append(f"{datetime.now()}: {message}")
    logs = logs[-50:]
    logger.info(message)

def save_to_cache():
    """Salva la playlist su disco."""
    try:
        with open(CACHE_FILE, "w") as f:
            f.write(merged_playlist)
        add_log("Playlist salvata su disco")
    except Exception as e:
        add_log(f"Errore salvataggio cache su disco: {e}")

def get_from_cache():
    """Recupera la playlist dal disco."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                add_log("Playlist caricata da disco")
                return f.read()
        return None
    except Exception as e:
        add_log(f"Errore recupero cache da disco: {e}")
        return None

def get_m3u_urls():
    """Recupera la lista degli URL M3U dal Pastebin."""
    try:
        add_log(f"Tentativo di recupero della lista M3U da {pastebin_url}")
        response = requests.get(pastebin_url, timeout=30)
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

def update_playlist():
    """Aggiorna la playlist M3U unendo gli URL dal Pastebin."""
    global merged_playlist, last_update, total_channels
    try:
        merged_playlist = "#EXTM3U\n"
        seen_urls = set()
        total_channels = 0
        m3u_urls = get_m3u_urls()

        if not m3u_urls:
            add_log("Nessun URL M3U valido recuperato dal Pastebin")
            save_to_cache()
            return

        for url in m3u_urls:
            try:
                add_log(f"Tentativo di recupero M3U da {url}")
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    lines = response.text.splitlines()
                    if not lines:
                        add_log(f"Contenuto vuoto da {url}")
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
                                merged_playlist += line + '\n'
                                merged_playlist += channel_url + '\n'
                                seen_urls.add(channel_url)
                                channel_count += 1
                            i = j
                        else:
                            i += 1
                    add_log(f"Aggiunto contenuto da {url} (Canali: {channel_count})")
                    total_channels += channel_count
                else:
                    add_log(f"Errore nel recupero di {url}: Stato {response.status_code}")
            except requests.exceptions.RequestException as e:
                add_log(f"Errore nel recupero di {url}: {e}")
            except Exception as e:
                add_log(f"Errore imprevisto durante il recupero di {url}: {e}")

        last_update = datetime.now()
        add_log(f"Playlist aggiornata: {last_update} (Canali totali: {total_channels})")
        save_to_cache()
    except Exception as e:
        add_log(f"Errore critico in update_playlist: {e}")
        raise

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

@app.route("/")
def index():
    try:
        return jsonify({
            "status": "Playlist aggiornata" if total_channels > 0 else "Nessun canale disponibile",
            "last_update": str(last_update),
            "total_channels": total_channels,
            "m3u_link": "https://ptv-r1fg.onrender.com/Coconut.m3u"
        })
    except Exception as e:
        add_log(f"Errore nel rendering della pagina index: {e}")
        return Response(f"Errore interno: {str(e)}", status=500)

@app.route("/Coconut.m3u")
def serve_playlist():
    try:
        cached = get_from_cache()
        if cached:
            return Response(cached, mimetype="audio/mpegurl")
        if merged_playlist.strip() == "#EXTM3U":
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
        if merged_playlist.strip() == "#EXTM3U":
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
