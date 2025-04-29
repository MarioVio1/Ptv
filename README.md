# M3U Playlist Merger with Italian EPG

This project provides a web service that merges multiple M3U playlists (listed in a remote text file) into a single M3U file and serves an Italian EPG (XMLTV format). The service auto-updates every hour and is deployed on [Render](https://render.com) using the free tier. It is compatible with IPTV apps like M3U IPTV or IPTV Smarters Pro on Samsung Smart TVs.

## Features
- Merges M3U playlists from a remote text file (`https://pastebin.com/raw/2JXd4cDJ`) into a unified M3U file.
- Serves an Italian EPG for IPTV channels.
- Auto-updates every hour to reflect changes in M3U playlists or EPG.
- Deployable on Render's free tier.
- Endpoints:
  - `/Coconut.m3u`: Unified M3U playlist.
  - `/epg.xml`: Italian EPG.

## Prerequisites
- A [Render](https://render.com) account (free tier).
- A [GitHub](https://github.com) account to host the code.
- A text file hosted online (e.g., Pastebin) listing M3U raw URLs (one per line).
- Legal and publicly accessible M3U playlists and EPG.

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/m3u-merger.git
cd m3u-merger
