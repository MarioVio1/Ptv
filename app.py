from flask import Flask, Response, render_template, redirect
import requests
import schedule
import time
import threading
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = Flask(__name__)

# URL del Pastebin raw
pastebin_url = "https://pastebin.com/raw/2JXd4cDJ"

# Variabili per lo stato
merged_playlist = "#EXTM3U\n"
last_update = None
total_channels = 0
m3u_status = []  # Lista di tuple (url, stato, numero_canali)

def create_session():
    """Crea una sessione requests con retry."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def get_m3u_urls():
    """Recupera la lista degli URL M3U dal Pastebin."""
    try:
        session = create_session()
        print(f"Tentativo di recupero della lista M3U da {pastebin_url}")
        response = session.get(pastebin_url, timeout=30)
        if response.status_code == 200:
            urls = [url.strip() for url in response.text.splitlines() if url.strip() and not url.strip().startswith("#")]
            print(f"Recuperati {len(urls)} URL M3U dal Pastebin")
            return urls
        else:
            print(f"Errore nel recupero del Pastebin: Stato {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"Errore nel recupero del Pastebin: {e}")
        return []

def validate_channel_url(url):
    """Verifica se un URL di un canale è accessibile."""
    try:
        session = create_session()
        response = session.head(url, timeout=10, allow_redirects=True)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def update_playlist():
    """Aggiorna la playlist M3U unendo gli URL dal Pastebin."""
    global merged_playlist, last_update, total_channels, m3u_status
    merged_playlist = "#EXTM3U\n"
    seen_urls = set()
    m3u_status = []
    session = create_session()
    m3u_urls = get_m3u_urls()

    if not m3u_urls:
        print("Nessun URL M3U valido recuperato dal Pastebin")
        m3u_status.append(("Nessun URL", "Errore: Pastebin non accessibile", 0))
        return

    for url in m3u_urls:
        try:
            print(f"Tentativo di recupero M3U da {url}")
            response = session.get(url, timeout=30)
            if response.status_code == 200:
                lines = response.text.splitlines()
                if not lines:
                    print(f"Errore: Contenuto vuoto da {url}")
                    m3u_status.append((url, "Vuoto", 0))
                    continue
                if lines[0].startswith("#EXTM3U"):
                    lines = lines[1:]
                channel_count = 0
                for i in range(len(lines)):
                    line = lines[i].strip()
                    if line.startswith("#EXTINF"):
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if next_line and not next_line.startswith("#"):
                                if validate_channel_url(next_line) and next_line not in seen_urls:
                                    merged_playlist += line + '\n'
                                    merged_playlist += next_line + '\n'
                                    seen_urls.add(next_line)
                                    channel_count += 1
                    elif line.startswith("#EXTVLCOPT"):
                        merged_playlist += line + '\n'
                print(f"Successo: Aggiunto contenuto da {url} (Canali validi: {channel_count})")
                m3u_status.append((url, "Funzionante", channel_count))
            else:
                print(f"Errore nel recupero di {url}: Stato {response.status_code}")
                m3u_status.append((url, f"Errore: Stato {response.status_code}", 0))
        except requests.exceptions.RequestException as e:
            print(f"Errore nel recupero di {url}: {e}")
            m3u_status.append((url, f"Errore: {str(e)}", 0))

    total_channels = merged_playlist.count("#EXTINF")
    last_update = datetime.now()
    print(f"Playlist aggiornata: {last_update} (Canali totali: {total_channels})")

# Pianifica l'aggiornamento ogni ora
schedule.every(1).hours.do(update_playlist)

# Esegui il pianificatore in background
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Avvia il pianificatore in un thread separato
threading.Thread(target=run_scheduler, daemon=True).start()

# Endpoint per la pagina index
@app.route("/")
def index():
    status = "Playlist aggiornata" if total_channels > 0 else "Errore: Nessun canale disponibile"
    return render_template("index.html",
                          status=status,
                          last_update=last_update,
                          total_channels=total_channels,
                          m3u_status=m3u_status,
                          m3u_link="https://ptv-r1fg.onrender.com/Coconut.m3u")

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
    return redirect("/")

if __name__ == "__main__":
    # Esegui l'aggiornamento iniziale
    update_playlist()
    app.run(host="0.0.0.0", port=5000)
