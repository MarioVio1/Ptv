# Ptv
# M3U Playlist Merger with EPG

This project provides a web service that merges multiple M3U playlists (raw URLs) into a single M3U file and serves an Italian EPG (Electronic Program Guide). The service auto-updates every hour and is designed to be deployed on [Render](https://render.com) for free. It is compatible with IPTV apps like M3U IPTV or IPTV Smarters Pro on Samsung Smart TVs.

## Features
- Merges multiple M3U playlists from a remote text file into one M3U file.
- Serves an Italian EPG (XMLTV format) for IPTV channels.
- Auto-updates every hour to reflect changes in M3U playlists or EPG.
- Deployable on Render's free tier.
- Provides two endpoints:
  - `/playlist.m3u`: Unified M3U playlist.
  - `/epg.xml`: Italian EPG.

## Prerequisites
- A [Render](https://render.com) account (free tier is sufficient).
- A [GitHub](https://github.com) account to host the code.
- A text file hosted online (e.g., Pastebin, GitHub Gist) containing a list of M3U raw URLs.
- M3U playlists and EPG must be legal and publicly accessible.

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/m3u-merger.git
cd m3u-merger
