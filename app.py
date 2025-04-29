from flask import Flask, Response
import requests
import schedule
import time
import threading
from datetime import datetime

app = Flask(__name__)

# Lista degli URL M3U
m3u_urls = [
    "https://github.com/ciccioxm3/omg/raw/refs/heads/main/itaevents.m3u8",
    "https://github.com/ciccioxm3/omg/raw/refs/heads/main/channels_italy.m3u8",
    "https://github.com/ciccioxm3/omg/raw/refs/heads/main/247ita.m3u8",
    "https://github.com/ciccioxm3/omg/raw/refs/heads/main/fullita.m3u8"
]

# Variabile per memorizzare la playlist M3U
merged_playlist = "#EXTM3U\n"

def update_playlist():
    """Aggiorna la playlist M3U unendo gli URL."""
    global merged_playlist
    merged_playlist = "#EXTM3U\n"
    seen_urls = set()  # Per evitare duplicati
    for url in m3u_urls:
        try:
            print(f"Tentativo di recupero M3U da {url}")
            response = requests.get(url, timeout=20)
            if response.status_code == 200:
                lines = response.text.splitlines()
                if lines and lines[0].startswith("#EXTM3U"):
                    lines = lines[1:]  # Salta l'intestazione
                for i in range(len(lines)):
                    line = lines[i].strip()
                    if line.startswith("#EXTINF"):
                        merged_playlist += line + '\n'
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if next_line and not next_line.startswith("#"):
                                if next_line not in seen_urls:
                                    seen_urls.add(next_line)
                                    merged_playlist += next_line + '\n'
                    elif line.startswith("#EXTVLCOPT"):
                        merged_playlist += line + '\n'
                print(f"Successo: Aggiunto contenuto da {url} (Canali: {response.text.count('#EXTINF')})")
            else:
                print(f"Errore nel recupero di {url}: Stato {response.status_code}")
        except Exception as e:
            print(f"Errore nel recupero di {url}: {e}")
    print(f"Playlist aggiornata: {datetime.now()} (Canali totali: {merged_playlist.count('#EXTINF')})")

# Pianifica l'aggiornamento ogni ora
schedule.every(1).hours.do(update_playlist)

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
    if merged_playlist.strip() == "#EXTM3U":
        return Response("Errore: Nessun canale disponibile. Controlla i log su Render.", mimetype="text/plain")
    return Response(merged_playlist, mimetype="audio/mpegurl")

# Endpoint per rigenerare la playlist
@app.route("/regenerate")
def regenerate_playlist():
    update_playlist()
    return Response("Playlist rigenerata con successo.", mimetype="text/plain")

if __name__ == "__main__":
    # Esegui l'aggiornamento iniziale
    update_playlist()
    app.run(host="0.0.0.0", port=5000)
