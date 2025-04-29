from flask import Flask, Response
import requests
import schedule
import time
import threading
from datetime import datetime
import gzip
import io

app = Flask(__name__)

# Lista degli URL M3U integrati direttamente
m3u_urls = [
    "http://inthemix.altervista.org/tv.m3u",
    "https://mvajro-premiumt.hf.space/generated-m3u",
    "https://github.com/ciccioxm3/omg/raw/refs/heads/main/itaevents.m3u8",
    "https://github.com/ciccioxm3/omg/raw/refs/heads/main/channels_italy.m3u8",
    "https://github.com/ciccioxm3/omg/raw/refs/heads/main/247ita.m3u8",
    "https://github.com/ciccioxm3/omg/raw/refs/heads/main/fullita.m3u8"
]

# URL dell'EPG
epg_url = "http://epg-guide.com/it.gz"

# Variabili per memorizzare la playlist M3U e l'EPG
merged_playlist = "#EXTM3U\n"
epg_content = ""

def update_playlist():
    """Aggiorna la playlist M3U unendo gli URL."""
    global merged_playlist
    merged_playlist = '#EXTM3U url-tvg="http://epg-guide.com/it.gz"\n'
    seen_urls = set()  # Per evitare duplicati
    for url in m3u_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                lines = response.text.splitlines()
                if lines and lines[0].startswith("#EXTM3U"):
                    lines = lines[1:]  # Salta l'intestazione
                for i in range(len(lines)):
                    line = lines[i].strip()
                    if line.startswith("#EXTINF"):
                        # Aggiungi la riga #EXTINF
                        merged_playlist += line + '\n'
                        # Controlla la riga successiva (URL)
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if next_line and not next_line.startswith("#"):
                                # Evita duplicati
                                if next_line not in seen_urls:
                                    seen_urls.add(next_line)
                                    merged_playlist += next_line + '\n'
                    elif line.startswith("#EXTVLCOPT"):
                        # Mantieni opzioni VLC
                        merged_playlist += line + '\n'
                print(f"Successo: Aggiunto contenuto da {url}")
            else:
                print(f"Errore nel recupero di {url}: Stato {response.status_code}")
        except Exception as e:
            print(f"Errore nel recupero di {url}: {e}")
    print(f"Playlist aggiornata: {datetime.now()} (Canali totali: {merged_playlist.count('#EXTINF')})")

def update_epg():
    """Aggiorna l'EPG da epg-guide.com."""
    global epg_content
    try:
        response = requests.get(epg_url, timeout=10)
        if response.status_code == 200:
            # Decomprimi il file .gz
            epg_content = gzip.decompress(response.content).decode('utf-8')
            print(f"EPG aggiornato: {datetime.now()}")
        else:
            print(f"Errore nel recupero dell'EPG: Stato {response.status_code}")
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

# Endpoint per servire la playlist M3U
@app.route("/Coconut.m3u")
def serve_playlist():
    if merged_playlist.strip() == '#EXTM3U url-tvg="http://epg-guide.com/it.gz"':
        return Response("Errore: Nessun canale disponibile. Controlla i log su Render.", mimetype="text/plain")
    return Response(merged_playlist, mimetype="audio/mpegurl")

# Endpoint per servire l'EPG
@app.route("/epg.xml")
def serve_epg():
    if not epg_content:
        return Response("Errore: EPG non disponibile. Controlla i log su Render.", mimetype="text/plain")
    return Response(epg_content, mimetype="application/xml")

# Endpoint per rigenerare la playlist
@app.route("/regenerate")
def regenerate_playlist():
    update_playlist()
    return Response("Playlist rigenerata con successo.", mimetype="text/plain")

if __name__ == "__main__":
    # Esegui gli aggiornamenti iniziali
    update_playlist()
    update_epg()
    app.run(host="0.0.0.0", port=5000)
