from flask import Flask, Response
import requests
import schedule
import time
import threading
from datetime import datetime

app = Flask(__name__)

# URL del file di testo con i link M3U raw
m3u_list_url = "https://pastebin.com/raw/2JXd4cDJ"

# URL dell'EPG italiano (pubblico e legale)
epg_url = "https://raw.githubusercontent.com/iptv-org/epg/master/guides/it.xml"
# Alternativa: https://epg.goddo.xyz/xmltv.xml

# Variabili per memorizzare la playlist M3U e l'EPG
merged_playlist = "#EXTM3U\n"
epg_content = ""

def get_m3u_urls():
    """Recupera l'elenco degli URL M3U dal file di testo remoto."""
    try:
        response = requests.get(m3u_list_url, timeout=10)
        if response.status_code == 200:
            # Filtra righe vuote e commenti
            urls = [line.strip() for line in response.text.splitlines() if line.strip() and not line.startswith("#")]
            return urls
        else:
            print(f"Errore nel recupero del file M3U list: {response.status_code}")
            return []
    except Exception as e:
        print(f"Errore nel recupero del file M3U list: {e}")
        return []

def update_playlist():
    global merged_playlist
    merged_playlist = "#EXTM3U\n"
    m3u_urls = get_m3u_urls()
    for url in m3u_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # Salta la riga #EXTM3U se presente
                lines = response.text.splitlines()
                if lines and lines[0].startswith("#EXTM3U"):
                    lines = lines[1:]
                # Aggiungi informazioni EPG se disponibili
                for line in lines:
                    if line.startswith("#EXTINF"):
                        merged_playlist += line + '\n'
                    elif not line.startswith("#"):
                        merged_playlist += line + '\n'
        except Exception as e:
            print(f"Errore nel recupero di {url}: {e}")
    print(f"Playlist aggiornata: {datetime.now()}")

def update_epg():
    global epg_content
    try:
        response = requests.get(epg_url, timeout=10)
        if response.status_code == 200:
            epg_content = response.text
            print(f"EPG aggiornato: {datetime.now()}")
        else:
            print(f"Errore nel recupero dell'EPG: {response.status_code}")
    except Exception as e:
        print(f"Errore nel recupero dell'EPG: {e}")

# Pianifica l'aggiornamento ogni ora
schedule.every(1).hours.do(update_playlist)
schedule.every(1).hours.do(update_epg)

# Esegui il pianificatore in background
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Avvia il pianificatore in un thread separato
threading.Thread(target=run_scheduler, daemon=True).start()

# Rotta per servire la playlist M3U
@app.route("/Coconut.m3u")
def serve_playlist():
    return Response(merged_playlist, mimetype="audio/mpegurl")

# Rotta per servire l'EPG
@app.route("/epg.xml")
def serve_epg():
    return Response(epg_content, mimetype="application/xml")

if __name__ == "__main__":
    # Esegui gli aggiornamenti iniziali
    update_playlist()
    update_epg()
    app.run(host="0.0.0.0", port=5000)
