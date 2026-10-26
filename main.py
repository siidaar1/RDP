import shutil
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import re
import json
import threading
import sys
import argparse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse, parse_qs, quote_plus
import os
from pathlib import Path

from colorama import init as colorama_init, Fore, Style

colorama_init(autoreset=True)


# ═══════════════════════════════════════════════════════════════════
# SETTINGS — enter your secret values here
# IMPORTANT: Never share this file publicly. If a token was exposed,
# revoke it and create a replacement before using it here.
# ═══════════════════════════════════════════════════════════════════
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

GITHUB_REPO = os.environ.get("GITHUB_REPO", "siidaar1/RDP")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_FILE = os.environ.get("GITHUB_FILE", "ads_data.json")


class C:
    """Color helpers"""

    SUCCESS = Fore.GREEN
    ERROR = Fore.RED
    WARN = Fore.YELLOW
    INFO = Fore.CYAN
    HEADER = Fore.MAGENTA + Style.BRIGHT
    DIM = Fore.WHITE + Style.DIM
    URL = Fore.BLUE + Style.BRIGHT
    PROMPT = Fore.CYAN + Style.BRIGHT

    @staticmethod
    def success(msg):
        print(f"{C.SUCCESS}{msg}{Style.RESET_ALL}")

    @staticmethod
    def error(msg):
        print(f"{C.ERROR}{msg}{Style.RESET_ALL}")

    @staticmethod
    def warn(msg):
        print(f"{C.WARN}{msg}{Style.RESET_ALL}")

    @staticmethod
    def info(msg):
        print(f"{C.INFO}{msg}{Style.RESET_ALL}")

    @staticmethod
    def header(msg):
        print(f"{C.HEADER}{msg}{Style.RESET_ALL}")

    @staticmethod
    def dim(msg):
        print(f"{C.DIM}{msg}{Style.RESET_ALL}")

    @staticmethod
    def url(msg):
        print(f"{C.URL}{msg}{Style.RESET_ALL}")

    @staticmethod
    def prompt(msg):
        return f"{C.PROMPT}{msg}{Style.RESET_ALL}"


# ═══════════════════════════════════════════════════════════════════
# GITHUB UPLOAD (JSON -> ONE GITHUB FILE)
# ═══════════════════════════════════════════════════════════════════


def upload_json_to_github(data, file_name=None):
    """Send JSON to a NEW GitHub file. Returns the raw URL."""
    import requests
    import base64

    token = GITHUB_TOKEN
    if not token:
        C.error(
            "❌ Add your GitHub token in the SETTINGS section at the top of this file.\n"
        )
        return None

    file_name = file_name or GITHUB_FILE
    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    try:
        # Only needed if the file already exists (normally it won't)
        sha = None
        r = requests.get(
            api, headers=headers, params={"ref": GITHUB_BRANCH}, timeout=30
        )
        if r.status_code == 200:
            sha = r.json().get("sha")

        content = base64.b64encode(
            json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        ).decode()

        payload = {
            "message": f"Add ads data {file_name}",
            "content": content,
            "branch": GITHUB_BRANCH,
        }
        if sha:
            payload["sha"] = sha

        r = requests.put(api, headers=headers, json=payload, timeout=60)

        if r.status_code in (200, 201):
            raw_url = (
                f"https://raw.githubusercontent.com/"
                f"{GITHUB_REPO}/{GITHUB_BRANCH}/{file_name}"
            )
            C.success(f"✅ JSON sent to GitHub: {raw_url}\n")
            return raw_url

        C.error(f"❌ GitHub error {r.status_code}: {r.text}\n")
        return None

    except Exception as e:
        C.error(f"❌ GitHub upload failed: {e}\n")
        return None


# ═══════════════════════════════════════════════════════════════════
# JSON DATA MANAGER
# ═══════════════════════════════════════════════════════════════════


class JSONDataManager:
    """Handles saving and loading JSON ad data"""

    def __init__(self, output_dir="ad_results"):
        self.output_dir = output_dir
        Path(output_dir).mkdir(exist_ok=True)

    def save_ads_data(self, ads_data, metadata):
        """Save ads data and metadata to JSON"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ads_data_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)

        data = {
            "metadata": {
                "timestamp": metadata.get("timestamp"),
                "search_query": metadata.get("search_query"),
                "country": metadata.get("country"),
                "total_ads": len(ads_data),
                "unique_websites": metadata.get("unique_websites"),
                "skipped_too_new": metadata.get("skipped_too_new"),
            },
            "ads": ads_data,
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            C.success(f"💾 Data saved to JSON: {filepath}\n")
            return filepath
        except Exception as e:
            C.error(f"❌ Error saving JSON: {e}\n")
            return None

    def load_ads_data(self, filepath):
        """Load ads data from JSON"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            C.error(f"❌ Error loading JSON: {e}\n")
            return None


# ═══════════════════════════════════════════════════════════════════
# HTML GENERATOR - LOADS DATA FROM GITHUB (NO DATA INSIDE THE HTML)
# ═══════════════════════════════════════════════════════════════════


class BeautifulHTMLGenerator:
    """Generate HTML dashboard that fetches its data from a GitHub file"""

    def __init__(self, output_dir="ad_results"):
        self.output_dir = output_dir
        Path(output_dir).mkdir(exist_ok=True)

    def create_dashboard(self, data_url):
        """Create HTML dashboard that loads JSON data from data_url (GitHub raw)"""

        css = r"""
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg: #0a0c10;
            --panel: #12151b;
            --panel-2: #171b22;
            --line: #232833;
            --ink: #e5e9f0;
            --ink-dim: #8b93a3;
            --ink-faint: #565e6e;
            --signal: #ffb020;
            --signal-dim: #7a4d10;
            --live: #33d17a;
            --mono: 'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace;
            --sans: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        @media (prefers-reduced-motion: reduce) {
            * { animation: none !important; transition: none !important; }
        }

        body {
            background: var(--bg);
            color: var(--ink);
            font-family: var(--sans);
            line-height: 1.55;
            min-height: 100vh;
        }

        a { color: inherit; }

        .wrap { max-width: 1360px; margin: 0 auto; padding: 28px 24px 60px; }

        /* ---------- loading state ---------- */
        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            font-family: var(--mono);
            color: var(--ink-dim);
        }

        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid var(--line);
            border-top-color: var(--signal);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* ---------- header ---------- */
        .log-header {
            position: relative;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 4px;
            padding: 28px 32px;
            margin-bottom: 28px;
            overflow: hidden;
        }

        .log-header::before {
            content: '';
            position: absolute;
            left: 0; right: 0; top: -40%;
            height: 40%;
            background: linear-gradient(180deg, rgba(255,176,32,0.10), transparent);
            animation: sweep 2.4s ease-out 1;
        }

        @keyframes sweep {
            0% { top: -40%; }
            100% { top: 100%; }
        }

        .eyebrow {
            font-family: var(--mono);
            font-size: 0.72rem;
            letter-spacing: 0.18em;
            color: var(--signal);
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
        }

        .eyebrow .dot {
            width: 7px; height: 7px; border-radius: 50%;
            background: var(--live);
            box-shadow: 0 0 0 0 rgba(51,209,122,0.6);
            animation: pulse 1.8s infinite;
        }

        @keyframes pulse {
            0%   { box-shadow: 0 0 0 0 rgba(51,209,122,0.55); }
            70%  { box-shadow: 0 0 0 7px rgba(51,209,122,0); }
            100% { box-shadow: 0 0 0 0 rgba(51,209,122,0); }
        }

        .log-header h1 {
            font-family: var(--mono);
            font-weight: 600;
            font-size: 1.7rem;
            letter-spacing: -0.01em;
            margin-bottom: 6px;
        }

        .log-header h1 span { color: var(--signal); }

        .log-header p {
            color: var(--ink-dim);
            font-size: 0.95rem;
            max-width: 60ch;
        }

        .readouts {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1px;
            background: var(--line);
            border: 1px solid var(--line);
            border-radius: 3px;
            margin-top: 24px;
            overflow: hidden;
        }

        .readout {
            background: var(--panel-2);
            padding: 14px 16px;
        }

        .readout .val {
            font-family: var(--mono);
            font-size: 1.4rem;
            font-weight: 600;
            color: var(--ink);
        }

        .readout .lbl {
            font-family: var(--mono);
            font-size: 0.68rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: var(--ink-faint);
            margin-top: 2px;
        }

        /* ---------- filters ---------- */
        .filters {
            display: flex;
            gap: 6px;
            margin-bottom: 22px;
            font-family: var(--mono);
            flex-wrap: wrap;
        }

        .filter-btn {
            background: transparent;
            border: 1px solid var(--line);
            color: var(--ink-dim);
            padding: 8px 16px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.78rem;
            letter-spacing: 0.04em;
            font-family: var(--mono);
            transition: border-color 0.15s, color 0.15s;
        }

        .filter-btn:hover { border-color: var(--ink-faint); color: var(--ink); }
        .filter-btn.active { border-color: var(--signal); color: var(--signal); background: rgba(255,176,32,0.06); }
        .filter-btn:focus-visible { outline: 2px solid var(--signal); outline-offset: 2px; }

        /* ---------- grid ---------- */
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 18px;
        }

        .card {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 4px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: border-color 0.15s;
        }

        .card:hover { border-color: var(--ink-faint); }

        /* ---------- media stage ---------- */
        .stage {
            position: relative;
            width: 100%;
            height: 320px;
            background: #000;
            border-bottom: 1px solid var(--line);
            overflow: hidden;
        }

        .frame {
            position: absolute;
            inset: 0;
            display: none;
            background: #000;
        }

        .frame.active { display: flex; align-items: center; justify-content: center; }

        .frame video, .frame img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            background: #000;
            display: block;
        }

        .frame .preview-hint {
            position: absolute;
            top: 10px; left: 10px;
            font-family: var(--mono);
            font-size: 0.65rem;
            letter-spacing: 0.05em;
            color: var(--ink-dim);
            background: rgba(10,12,16,0.75);
            border: 1px solid var(--line);
            padding: 3px 8px;
            border-radius: 20px;
            pointer-events: none;
            z-index: 2;
        }

        .no-media, .media-error {
            width: 100%; 
            height: 100%;
            display: flex; 
            align-items: center; 
            justify-content: center;
            font-family: var(--mono);
            font-size: 0.75rem;
            color: var(--ink-faint);
            letter-spacing: 0.08em;
            flex-direction: column;
            gap: 8px;
            padding: 20px;
            text-align: center;
        }

        .thumbs {
            position: absolute;
            bottom: 8px; left: 8px; right: 8px;
            display: flex;
            gap: 5px;
            overflow-x: auto;
            z-index: 10;
        }

        .thumb {
            flex: 0 0 auto;
            width: 34px; height: 34px;
            border: 1px solid var(--line);
            border-radius: 3px;
            background: #000;
            cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            font-family: var(--mono);
            font-size: 0.62rem;
            color: var(--ink-dim);
            opacity: 0.6;
        }

        .thumb.active { border-color: var(--signal); color: var(--signal); opacity: 1; }
        .thumb:focus-visible { outline: 2px solid var(--signal); outline-offset: 1px; }

        .count-badge {
            position: absolute;
            top: 10px; right: 10px;
            font-family: var(--mono);
            font-size: 0.68rem;
            color: var(--ink);
            background: rgba(10,12,16,0.75);
            border: 1px solid var(--line);
            padding: 3px 9px;
            border-radius: 20px;
            pointer-events: none;
            z-index: 2;
        }

        /* ---------- card body ---------- */
        .body { padding: 16px 18px 18px; display: flex; flex-direction: column; flex: 1; }

        .sig-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
        }

        .sig-id {
            font-family: var(--mono);
            font-size: 0.72rem;
            color: var(--ink-faint);
            letter-spacing: 0.06em;
        }

        .cta {
            display: inline-block;
            font-family: var(--mono);
            font-size: 0.7rem;
            letter-spacing: 0.03em;
            color: var(--signal);
            border: 1px solid var(--signal-dim);
            background: rgba(255,176,32,0.06);
            padding: 3px 9px;
            border-radius: 3px;
        }

        .url-box {
            font-family: var(--mono);
            font-size: 0.78rem;
            color: var(--ink-dim);
            word-break: break-all;
            background: var(--panel-2);
            border: 1px solid var(--line);
            border-left: 2px solid var(--signal-dim);
            padding: 9px 10px;
            border-radius: 3px;
            margin-bottom: 12px;
        }

        .status-row {
            display: flex;
            align-items: center;
            gap: 6px;
            font-family: var(--mono);
            font-size: 0.76rem;
            margin-bottom: 4px;
        }

        .status-row.fresh { color: var(--live); }

        .status-row.fresh .dot {
            width: 6px; height: 6px; border-radius: 50%;
            background: var(--live);
            animation: pulse 1.8s infinite;
        }

        .status-row.settled { color: var(--ink-dim); }

        .found-at { font-family: var(--mono); font-size: 0.72rem; color: var(--ink-faint); margin-bottom: 14px; }

        .actions { display: flex; gap: 8px; margin-top: auto; }

        .btn {
            flex: 1;
            padding: 10px 14px;
            border: 1px solid var(--signal);
            background: var(--signal);
            color: #0a0c10;
            font-weight: 600;
            border-radius: 3px;
            cursor: pointer;
            text-decoration: none;
            text-align: center;
            font-size: 0.82rem;
            transition: opacity 0.15s;
        }

        .btn:hover { opacity: 0.85; }
        .btn:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }

        .btn-ghost {
            background: transparent;
            border: 1px solid var(--line);
            color: var(--ink-dim);
        }

        .btn-ghost:hover { border-color: var(--ink-faint); color: var(--ink); opacity: 1; }

        .btn-search {
            width: 100%;
            margin-top: 8px;
            padding: 9px;
            background: transparent;
            border: 1px solid var(--line);
            color: var(--ink-dim);
            font-family: var(--mono);
            font-size: 0.72rem;
            letter-spacing: 0.03em;
            border-radius: 3px;
            cursor: pointer;
            transition: border-color 0.15s, color 0.15s;
        }

        .btn-search:hover { border-color: var(--signal); color: var(--signal); }
        .btn-search:focus-visible { outline: 2px solid var(--signal); outline-offset: 2px; }

        /* ---------- empty state ---------- */
        .empty {
            grid-column: 1/-1;
            text-align: center;
            padding: 70px 20px;
            border: 1px dashed var(--line);
            border-radius: 4px;
        }

        .empty .eyebrow { justify-content: center; }
        .empty h2 { font-family: var(--mono); font-size: 1.1rem; margin: 8px 0 6px; color: var(--ink); }
        .empty p { color: var(--ink-dim); font-size: 0.9rem; }

        .footer {
            margin-top: 44px;
            padding-top: 20px;
            border-top: 1px solid var(--line);
            font-family: var(--mono);
            font-size: 0.72rem;
            color: var(--ink-faint);
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
        }

        @media (max-width: 640px) {
            .wrap { padding: 18px 14px 40px; }
            .log-header { padding: 20px; }
            .log-header h1 { font-size: 1.3rem; }
            .stage { height: 280px; }
            .grid { grid-template-columns: 1fr; }
            .readouts { grid-template-columns: repeat(2, 1fr); }
        }

        /* ---------- sort buttons ---------- */
        .sort-btn {
            background: transparent;
            border: 1px solid var(--line);
            color: var(--ink-dim);
            padding: 8px 16px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 0.78rem;
            letter-spacing: 0.04em;
            font-family: var(--mono);
            transition: border-color 0.15s, color 0.15s;
        }

        .sort-btn:hover { border-color: var(--ink-faint); color: var(--ink); }
        .sort-btn.active { border-color: var(--signal); color: var(--signal); background: rgba(255,176,32,0.06); }
        .sort-btn:focus-visible { outline: 2px solid var(--signal); outline-offset: 2px; }
        """

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ad signal feed</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>

<div id="loading" class="loading">
    <div style="text-align: center;">
        <div class="spinner"></div>
        <p style="margin-top: 16px;">Loading ad data from GitHub...</p>
    </div>
</div>

<div id="content" style="display: none;">
    <div class="wrap">
        <div class="log-header">
            <div class="eyebrow"><span class="dot"></span> Live capture</div>
            <h1>Ad signal feed — <span id="headerQuery">loading</span></h1>
            <p id="headerDesc">Creative intercepted from Meta's Ad Library. Previews load metadata only until you press play, to keep bandwidth down.</p>
            <div class="readouts">
                <div class="readout"><div class="val" id="readoutAds">0</div><div class="lbl">Signals captured</div></div>
                <div class="readout"><div class="val" id="readoutWebsites">0</div><div class="lbl">Unique targets</div></div>
                <div class="readout"><div class="val" id="readoutQuery">—</div><div class="lbl">Query</div></div>
                <div class="readout"><div class="val" id="readoutCountry">—</div><div class="lbl">Region</div></div>
            </div>
        </div>

        <div class="filters">
            <button class="filter-btn active" onclick="filterAds('all', event)">ALL</button>
            <button class="filter-btn" onclick="filterAds('new', event)">FRESH &lt; 5D</button>
            <button class="filter-btn" onclick="filterAds('old', event)">ESTABLISHED 5D+</button>
        </div>

        <div class="filters">
            <button class="sort-btn" onclick="sortAds('new', event)">SORT: NEW → OLD</button>
            <button class="sort-btn" onclick="sortAds('old', event)">SORT: OLD → NEW</button>
        </div>

        <div class="grid" id="gridContainer"></div>

        <div class="footer">
            <span>LOG CLOSED <span id="timestamp"></span></span>
            <span>META ADS LIBRARY — INTERCEPT DASHBOARD</span>
        </div>
    </div>
</div>

<script>

// Data comes from this GitHub file (nothing is stored inside this HTML)
const DATA_URL = "{data_url}";

async function loadData() {{
    try {{
        const res = await fetch(DATA_URL + '?t=' + Date.now(), {{ cache: 'no-store' }});
        if (!res.ok) throw new Error('GitHub returned ' + res.status);
        const data = await res.json();

        console.log('Loaded data:', data);
        renderDashboard(data);
    }} catch (error) {{
        console.error('Error loading JSON:', error);
        document.getElementById('content').innerHTML = 
            '<div style="padding: 40px; text-align: center; color: #e5e9f0;">' +
            '<h2>Error loading ad data</h2>' +
            '<p>' + error.message + '</p>' +
            '</div>';
        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';
    }}
}}

function ensureHttps(url) {{
    if (!url) return url;
    // Convert http to https for media
    return url.replace(/^http:/, 'https:');
}}

function renderDashboard(data) {{
    const metadata = data.metadata;
    const ads = data.ads;

    // Update header
    document.getElementById('headerQuery').textContent = metadata.search_query || 'all queries';
    document.getElementById('headerDesc').textContent = 
        'Creative intercepted from Meta\\'s Ad Library for this query, region ' + 
        (metadata.country || '—') + '. Previews load metadata only until you press play, to keep bandwidth down.';

    // Update readouts
    document.getElementById('readoutAds').textContent = ads.length;
    document.getElementById('readoutWebsites').textContent = metadata.unique_websites || 0;
    document.getElementById('readoutQuery').textContent = metadata.search_query || '—';
    document.getElementById('readoutCountry').textContent = metadata.country || '—';
    document.getElementById('timestamp').textContent = new Date(metadata.timestamp).toLocaleString();

    // Render cards
    const grid = document.getElementById('gridContainer');
    grid.innerHTML = '';

    if (ads.length === 0) {{
        grid.innerHTML = `
            <div class="empty" style="grid-column: 1/-1;">
                <div class="eyebrow"><span class="dot"></span> No signal</div>
                <h2>No creative captured yet</h2>
                <p>Run the scraper again with a different query, region, or scroll depth.</p>
            </div>
        `;
    }} else {{
        ads.forEach((ad, idx) => {{
            const card = createAdCard(ad, idx + 1);
            grid.appendChild(card);
        }});
    }}

    document.getElementById('loading').style.display = 'none';
    document.getElementById('content').style.display = 'block';
}}

function createAdCard(ad, index) {{
    const card = document.createElement('div');
    card.className = 'card';

    const adType = ad.running_days !== null && ad.running_days < 5 ? 'new' : 'old';
    card.dataset.type = adType;
    card.dataset.days = (ad.running_days !== null && ad.running_days !== undefined) ? ad.running_days : '';

    const mediaItems = ad.media_items || [];
    let stageHTML = '';

    if (mediaItems.length > 0) {{
        let frames = '';
        let thumbs = '';
        let videoCount = 0;

        mediaItems.forEach((media, mIdx) => {{
            const isActive = mIdx === 0 ? ' active' : '';
            const mediaSrc = ensureHttps(media.src);

            if (media.type === 'video') {{
                videoCount++;
                const posterAttr = media.poster ? `poster="${{ensureHttps(media.poster)}}"` : '';
                frames += `
                    <div class="frame${{isActive}}" data-idx="${{mIdx}}">
                        <video 
                            src="${{mediaSrc}}" 
                            ${{posterAttr}} 
                            controls 
                            preload="metadata" 
                            playsinline 
                            muted
                            crossorigin="anonymous"
                            onerror="handleMediaError(this)"
                            style="display:block;"
                        ></video>
                        <span class="preview-hint">◉ metadata only — press play</span>
                    </div>
                `;
                thumbs += `<button class="thumb${{isActive}}" data-idx="${{mIdx}}" onclick="showFrame(this)" aria-label="Show clip ${{mIdx+1}}">▶</button>`;
            }} else {{
                frames += `
                    <div class="frame${{isActive}}" data-idx="${{mIdx}}">
                        <img 
                            src="${{mediaSrc}}" 
                            loading="lazy" 
                            alt="Ad creative preview"
                            crossorigin="anonymous"
                            onerror="handleMediaError(this)"
                            style="display:block;"
                        />
                    </div>
                `;
                thumbs += `<button class="thumb${{isActive}}" data-idx="${{mIdx}}" onclick="showFrame(this)" aria-label="Show image ${{mIdx+1}}">▣</button>`;
            }}
        }});

        const thumbsHTML = mediaItems.length > 1 ? `<div class="thumbs">${{thumbs}}</div>` : '';
        const countBadge = mediaItems.length > 1 ? 
            `<div class="count-badge">${{mediaItems.length}} clip${{mediaItems.length !== 1 ? 's' : ''}}${{videoCount ? ' · ' + videoCount + ' video' : ''}}</div>` : '';

        stageHTML = `
            <div class="stage">
                <div style="position: absolute; inset: 0;">
                    ${{frames}}
                </div>
                ${{thumbsHTML}}
                ${{countBadge}}
            </div>
        `;
    }} else {{
        stageHTML = '<div class="stage"><div class="no-media">NO PREVIEW CAPTURED</div></div>';
    }}

    // Status
    let statusHTML = '';
    if (ad.running_days !== null && ad.running_days !== undefined) {{
        if (ad.running_days < 5) {{
            statusHTML = `<div class="status-row fresh"><span class="dot"></span> ${{ad.running_days}}D — fresh</div>`;
        }} else {{
            statusHTML = `<div class="status-row settled">${{ad.running_days}}D running — established</div>`;
        }}
    }} else {{
        statusHTML = '<div class="status-row settled">Duration unknown</div>';
    }}

    // Format time
    let timeStr = 'Unknown';
    try {{
        const dt = new Date(ad.found_at);
        const month = dt.toLocaleString('en-US', {{ month: 'short' }});
        const day = dt.getDate();
        const hours = String(dt.getHours()).padStart(2, '0');
        const mins = String(dt.getMinutes()).padStart(2, '0');
        timeStr = `${{month}} ${{day}}, ${{hours}}:${{mins}}`;
    }} catch (e) {{
        timeStr = ad.found_at;
    }}

    const urlDisplay = ad.url.length > 64 ? ad.url.substring(0, 64) + '…' : ad.url;

    card.innerHTML = `
        ${{stageHTML}}
        <div class="body">
            <div class="sig-row">
                <span class="sig-id">SIG-${{String(index).padStart(3, '0')}}</span>
                <span class="cta">${{ad.button_text}}</span>
            </div>
            <div class="url-box">${{urlDisplay}}</div>
            ${{statusHTML}}
            <div class="found-at">Captured ${{timeStr}}</div>
            <div class="actions">
                <a href="${{ad.url}}" target="_blank" class="btn">Visit site</a>
                <button class="btn btn-ghost" onclick="copyURL('${{ad.url.replace(/'/g, "\\'")}}')" >Copy</button>
            </div>
            <button class="btn-search" onclick="searchInLibrary('${{ad.url.replace(/'/g, "\\'")}}')">◎ Find in Ads Library</button>
        </div>
    `;

    return card;
}}

function handleMediaError(element) {{
    const frame = element.closest('.frame');
    if (frame) {{
        const src = element.src || element.getAttribute('src');
        console.warn('Media failed to load:', src);
        frame.innerHTML = '<div class="media-error">⚠️ Media unavailable<br><small>CDN link may have expired</small></div>';
    }}
}}

function filterAds(type, evt) {{
    document.querySelectorAll('.card').forEach(card => {{
        card.style.display = (type === 'all' || card.dataset.type === type) ? '' : 'none';
    }});
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    if (evt && evt.target) evt.target.classList.add('active');
}}

function sortAds(direction, evt) {{
    const grid = document.getElementById('gridContainer');
    const cards = Array.from(grid.querySelectorAll('.card'));
    const getDays = c => c.dataset.days === '' ? null : Number(c.dataset.days);

    cards.sort((a, b) => {{
        const da = getDays(a), db = getDays(b);
        if (da === null && db === null) return 0;
        if (da === null) return 1;
        if (db === null) return -1;
        return direction === 'new' ? da - db : db - da;
    }});

    cards.forEach(c => grid.appendChild(c));

    document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
    if (evt && evt.target) evt.target.classList.add('active');
}}

function showFrame(btn) {{
    const stage = btn.closest('.stage');
    const idx = btn.dataset.idx;

    const frameContainer = stage.querySelector('div[style*="position: absolute"]') || stage;
    frameContainer.querySelectorAll('.frame').forEach(f => {{
        const isTarget = f.dataset.idx === idx;
        f.classList.toggle('active', isTarget);
        if (!isTarget) {{ 
            const v = f.querySelector('video'); 
            if (v) v.pause(); 
        }}
    }});

    stage.querySelectorAll('.thumb').forEach(t => t.classList.toggle('active', t === btn));
}}

function copyURL(url) {{
    navigator.clipboard.writeText(url).then(() => {{
        alert('URL copied to clipboard');
    }}).catch(() => {{}});
}}

function searchInLibrary(url) {{
    let domain = url;
    try {{
        domain = new URL(url).hostname.replace(/^www\\./, '');
    }} catch (e) {{}}
    const q = encodeURIComponent(domain);
    const target = 'https://www.facebook.com/ads/library/?active_status=active&ad_type=all' +
        '&country=AE&is_targeted_country=false&media_type=all' +
        '&q=' + q + '&search_type=keyword_unordered';
    window.open(target, '_blank');
}}

// Load on page load
document.addEventListener('DOMContentLoaded', loadData);

</script>

</body>
</html>
"""
        return html

    def save_dashboard(self, html_content, filename="dashboard.html"):
        """Save HTML to file"""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        return filepath


# ═══════════════════════════════════════════════════════════════════
# SCRAPER
# ═══════════════════════════════════════════════════════════════════


class MetaAdsScraper:
    LOW_DATA_VIDEO_GUARD_JS = r"""
(function(){
    if (window.__lowDataGuardInstalled) return;
    window.__lowDataGuardInstalled = true;

    function neuter(v){
        try{
            v.autoplay = false;
            v.preload = 'metadata';
            v.muted = true;
            v.pause();
        }catch(e){}
    }

    try{
        HTMLMediaElement.prototype.play = function(){
            neuter(this);
            return Promise.resolve();
        };
    }catch(e){}

    function scan(root){
        try{
            var vids = root.querySelectorAll ? root.querySelectorAll('video') : [];
            vids.forEach(neuter);
        }catch(e){}
    }

    scan(document);

    try{
        var mo = new MutationObserver(function(muts){
            muts.forEach(function(m){
                (m.addedNodes || []).forEach(function(n){
                    if (n.nodeType === 1){
                        if (n.tagName === 'VIDEO') neuter(n);
                        scan(n);
                    }
                });
            });
        });
        mo.observe(document.documentElement || document, {childList:true, subtree:true});
    }catch(e){}

    setInterval(function(){ scan(document); }, 800);
})();
"""

    # Strict date matcher: only captures a real date, never extra words
    DATE_RE = re.compile(
        r"Started running on\s+("
        r"\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}"  # 12 Oct 2025
        r"|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"  # Oct 12, 2025
        r")",
        re.I,
    )

    def __init__(
        self,
        domain_filter=None,
        scroll_limit=None,
        slow_internet=False,
        min_days_running=5,
    ):
        self.results = []
        self.websites = set()
        self.driver = None
        self.domain_filter = domain_filter
        self.min_days_running = min_days_running
        self.skipped_too_new = 0
        self.scroll_limit = scroll_limit
        self.slow_internet = slow_internet

        # Data managers
        self.json_manager = JSONDataManager()
        self.html_generator = BeautifulHTMLGenerator()

        # Timeouts
        if slow_internet:
            self.page_load_wait = 25
            self.scroll_wait = 4
            self.no_growth_limit = 6
            self.page_load_timeout = 150
            self.element_wait_timeout = 20
        else:
            self.page_load_wait = 18
            self.scroll_wait = 3
            self.no_growth_limit = 5
            self.page_load_timeout = 90
            self.element_wait_timeout = 15

        # For deduplication
        self.url_to_result_index = {}
        self._seen_button_fingerprints = set()

        # Stop event
        self.stop_event = threading.Event()
        self._stop_listener_started = False

    def _start_stop_listener(self):
        """Listen for ENTER key to stop"""
        if self._stop_listener_started or not sys.stdin.isatty():
            return
        self._stop_listener_started = True

        def _listen():
            try:
                input()
            except EOFError:
                return
            except Exception:
                return
            if not self.stop_event.is_set():
                self.stop_event.set()
                C.warn("\n⏹️  Stop requested — wrapping up...\n")

        t = threading.Thread(target=_listen, daemon=True)
        t.start()

    def setup_driver(self):
        """Setup Chrome driver for Replit"""

        chrome_options = Options()

        # Facebook performance settings
        chrome_options.page_load_strategy = "eager"

        # Anti-detection flags
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        # Replit / Linux settings
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--autoplay-policy=user-gesture-required")

        # Force English so "Started running on" is always parseable
        chrome_options.add_argument("--lang=en-US")

        # Disable images/fonts to save bandwidth
        chrome_prefs = {
            "profile.default_content_setting_values": {
                "images": 2,
                "plugins": 2,
                "notifications": 2,
            },
            "intl.accept_languages": "en-US,en",
        }

        chrome_options.add_experimental_option("prefs", chrome_prefs)

        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        # Find Chrome / Chromium installed by Replit
        chrome_paths = [
    shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"),
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    shutil.which("chromium"),
    shutil.which("chromium-browser"),
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
        ]

        chrome_binary = None

        for path in chrome_paths:
            if path and os.path.exists(path):
                chrome_binary = path
                break

        if not chrome_binary:
            C.error("❌ Chrome/Chromium was not found on this Replit environment.")
            return False

        chrome_options.binary_location = chrome_binary

        try:
            self.driver = webdriver.Chrome(options=chrome_options)

            self.driver.set_page_load_timeout(self.page_load_timeout)

            self.driver.set_script_timeout(self.page_load_timeout)

            self._install_low_data_guard()

            C.success(f"✅ Chrome started: {chrome_binary}\n")

            C.success("✅ Low-data mode enabled\n")

            if self.slow_internet:
                C.info("🐢 Slow internet mode ON\n")

            return True

        except Exception as e:
            C.error(f"❌ ChromeDriver error: {e}\n")
            return False

    def _install_low_data_guard(self):
        try:
            self.driver.execute_cdp_cmd("Network.enable", {})
            self.driver.execute_cdp_cmd(
                "Network.setBlockedURLs",
                {
                    "urls": [
                        "*.woff",
                        "*.woff2",
                        "*.ttf",
                        "*.otf",
                        "*.eot",
                        "*/tr/*",
                        "*/pixel/*",
                    ]
                },
            )
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": self.LOW_DATA_VIDEO_GUARD_JS},
            )
        except:
            pass

    def _neuter_videos_now(self):
        try:
            self.driver.execute_script("""
                document.querySelectorAll('video').forEach(function(v){
                    try{ v.autoplay=false; v.preload='metadata'; v.muted=true; v.pause(); }catch(e){}
                });
            """)
        except:
            pass

    def _wait_for_ad_elements(self):
        """Wait until Facebook has rendered a usable result DOM."""
        C.dim("⏳ Waiting for Meta Ads Library DOM...\n")
        try:
            wait = WebDriverWait(self.driver, self.element_wait_timeout)

            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            deadline = time.time() + min(self.element_wait_timeout, 15)
            while time.time() < deadline and not self.stop_event.is_set():
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                    if (
                        "Started running on" in body_text
                        or "Sponsored" in body_text
                        or "No ads" in body_text
                        or "No results" in body_text
                    ):
                        C.success("✅ Meta Ads Library content detected\n")
                        return True
                except Exception:
                    pass
                time.sleep(0.5)

            C.warn(
                "⚠️  Result text not detected yet; continuing with incremental parsing...\n"
            )
            return False

        except Exception:
            C.warn("⚠️  DOM wait timed out; continuing...\n")
            return False

    def _trigger_page_interactions(self):
        """Trigger scrolls to wake up dynamic content"""
        C.dim("⚙️  Triggering page interactions...\n")
        try:
            self.driver.execute_script(
                "window.scrollBy(0, 300); window.scrollBy(0, -300);"
            )
            time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
        except:
            pass

    def search_meta_ads_library(self, search_query, country="AE"):
        """Search and scrape ads with incremental parsing."""
        if not self.setup_driver():
            return

        C.info(f"🔍 Searching: '{search_query}' | Country: {country}\n")
        C.warn("⏹️  Press ENTER to stop; the current page will still be parsed.\n")
        self._start_stop_listener()

        encoded_query = quote_plus(search_query.strip())
        url = (
            "https://www.facebook.com/ads/library/"
            f"?active_status=active&ad_type=all&country={country}"
            "&is_targeted_country=false&media_type=video"
            f"&q={encoded_query}&search_type=keyword_unordered"
            "&sort_data[direction]=desc&sort_data[mode]=total_impressions"
        )

        try:
            C.dim(f"📍 Opening: {url}\n")

            opened = False
            for attempt in range(1, 4):
                if self.stop_event.is_set():
                    break
                try:
                    self.driver.get(url)
                    opened = True
                    break
                except Exception as e:
                    if attempt < 3:
                        C.warn(f"⚠️  Page-load retry {attempt}: {type(e).__name__}\n")
                        time.sleep(3)

            if not opened and self.stop_event.is_set():
                return

            C.dim(f"⏳ Waiting {self.page_load_wait}s for dynamic content...\n")
            deadline = time.time() + self.page_load_wait
            while time.time() < deadline and not self.stop_event.is_set():
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                    if "Started running on" in body_text or "Sponsored" in body_text:
                        break
                except Exception:
                    pass
                time.sleep(0.5)

            self._trigger_page_interactions()
            self._wait_for_ad_elements()
            self._neuter_videos_now()

            C.info("🔎 Parsing initial DOM...\n")
            self._extract_current_page()

            try:
                self.driver.save_screenshot("page_initial.png")
                C.dim("📸 Initial screenshot saved\n")
            except Exception:
                pass

            if not self.stop_event.is_set():
                C.info("📜 Scrolling + parsing incrementally...\n")
                self._scroll_page_only(self.scroll_limit)
            else:
                C.warn("⏹️  Stop requested — parsing the current DOM...\n")
                self._extract_current_page()

            C.info("🔎 Final DOM parse...\n")
            self._extract_current_page(save_debug=True)

            C.success(f"\n✅ Found {len(self.results)} total ads\n")
            if self.skipped_too_new:
                C.warn(f"⏭️  Skipped {self.skipped_too_new} too-new ads\n")

        except KeyboardInterrupt:
            C.warn("\n⏹️  Stopped — parsing current page...\n")
            self.stop_event.set()
            try:
                self._extract_current_page(save_debug=True)
            except Exception:
                pass
            raise

        except Exception as e:
            C.error(f"\n❌ Error: {e}\n")
            import traceback

            traceback.print_exc()

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    C.success("✅ Driver closed")
                except Exception:
                    pass

            if self.results:
                C.success(f"\n✅ Extracted {len(self.results)} ads\n")

    def _extract_current_page(self, save_debug=False):
        """Capture and parse the CURRENT browser DOM immediately."""
        if not self.driver:
            return 0

        try:
            page_source = self.driver.page_source
        except Exception as e:
            C.warn(f"⚠️  Could not read current DOM: {e}")
            return 0

        if not page_source or len(page_source) < 500:
            C.warn("⚠️  Current DOM is too small to parse yet.")
            return 0

        if save_debug:
            try:
                with open("page_source_debug.html", "w", encoding="utf-8") as f:
                    f.write(page_source)
                C.dim(f"💾 Page source saved ({len(page_source):,} chars)\n")
            except Exception:
                pass

        before = len(self.results)
        self._extract_all_ads(page_source)
        added = len(self.results) - before
        C.dim(
            f"   Parsed {len(page_source):,} chars | "
            f"+{added} new ads | {len(self.results)} total\n"
        )
        return added

    def _scroll_page_only(self, scroll_limit=None):
        """Scroll and PARSE after every scroll so virtualized ads are not lost."""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        last_source_len = 0
        no_growth_count = 0
        i = 0

        C.dim(f"Starting scroll (limit: {scroll_limit or 'unlimited'})\n")

        while True:
            if self.stop_event.is_set():
                C.warn(f"⏹️  ENTER received after {i} scrolls. Parsing current DOM...\n")
                self._extract_current_page(save_debug=True)
                break

            if scroll_limit and i >= scroll_limit:
                C.warn(f"Reached limit of {scroll_limit} scrolls\n")
                break

            self.driver.execute_script(
                "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight));"
            )
            i += 1

            wait_until = time.time() + self.scroll_wait
            while time.time() < wait_until:
                if self.stop_event.is_set():
                    break
                time.sleep(0.25)

            self._neuter_videos_now()

            current_source_len = 0
            try:
                current_source_len = len(self.driver.page_source)
            except Exception:
                pass

            if current_source_len != last_source_len or i == 1:
                self._extract_current_page()
                last_source_len = current_source_len

            if self.stop_event.is_set():
                C.warn(f"⏹️  ENTER received during scroll {i}. Parsing current DOM...\n")
                self._extract_current_page(save_debug=True)
                break

            new_height = self.driver.execute_script("return document.body.scrollHeight")

            if new_height <= last_height:
                no_growth_count += 1
                C.dim(
                    f"   Scroll {i}: no height growth "
                    f"({no_growth_count}/{self.no_growth_limit}) | "
                    f"ads={len(self.results)}\n"
                )

                if no_growth_count >= self.no_growth_limit:
                    C.success(
                        f"✅ Page finished after {i} scrolls | ads={len(self.results)}\n"
                    )
                    break
            else:
                no_growth_count = 0
                growth = new_height - last_height
                C.dim(f"   Scroll {i}: +{growth}px | ads={len(self.results)}\n")

            last_height = new_height

    def _extract_all_ads(self, page_source):
        """Extract ads from the current DOM."""
        soup = BeautifulSoup(page_source, "html.parser")

        position_index, date_positions = self._index_ad_start_dates(soup)

        button_keywords = [
            "order now",
            "shop now",
            "buy now",
            "get offer",
            "learn more",
            "contact",
            "visit website",
            "download",
            "sign up",
            "subscribe",
            "book now",
            "call now",
            "send message",
            "send whatsapp",
            "whatsapp",
            "message",
            "shop",
            "order",
            "buy",
            "get",
            "view",
            "see",
        ]

        buttons = soup.find_all(["button", "a"])
        C.dim(f"Processing {len(buttons)} links/buttons...\n")

        for button in buttons:
            raw_text = button.get_text(" ", strip=True)
            button_text = " ".join(raw_text.split()).lower()

            if not button_text:
                continue

            if not any(keyword in button_text for keyword in button_keywords):
                continue

            url = self._extract_url(button)
            if not url:
                continue

            url = self._normalize_external_url(url)
            if not self._is_valid_url(url):
                continue

            # Prefer the date inside the same ad card; fall back to nearest date
            running_days = self._running_days_for_element(button)
            if running_days is None:
                running_days = self._nearest_running_days(
                    button, position_index, date_positions
                )

            if running_days is not None and running_days < self.min_days_running:
                self.skipped_too_new += 1
                continue

            media_items = self._find_media_for_button(button)
            merged_media, is_new = self._record_ad(
                raw_text, url, running_days, media_items
            )

            if is_new is None:
                continue

            video_count = sum(1 for m in merged_media if m["type"] == "video")
            age_note = f" [{running_days}d]" if running_days is not None else " [age?]"
            media_note = (
                f" 🎥x{video_count}" if video_count else (" 🖼️" if merged_media else "")
            )
            action = "Found" if is_new else "Merged into"

            print(
                f"{C.SUCCESS}✅ {action}{age_note}{media_note}: "
                f"{raw_text[:30]}... → {C.URL}{url}{Style.RESET_ALL}\n"
            )

        # Fallback: find each ad card by "Started running on"
        started_nodes = soup.find_all(string=re.compile(r"Started running on", re.I))

        fallback_count = 0

        for started_node in started_nodes:
            running_days = self._parse_running_days_from_text(
                started_node.parent.get_text(" ", strip=True)
                if started_node.parent
                else str(started_node)
            )

            if running_days is not None and running_days < self.min_days_running:
                self.skipped_too_new += 1
                continue

            container = started_node.parent
            chosen_links = []

            for _ in range(9):
                if not container or not hasattr(container, "find_all"):
                    break

                links = container.find_all("a", href=True)
                external = []

                for link in links:
                    href = self._normalize_external_url(link.get("href"))
                    if not href or not self._is_valid_url(href):
                        continue
                    external.append((link, href))

                if external:
                    chosen_links = external
                    break

                container = container.parent

            if not chosen_links:
                continue

            def link_score(item):
                link, href = item
                txt = " ".join(link.get_text(" ", strip=True).split()).lower()
                score = 0

                for word in (
                    "shop",
                    "buy",
                    "order",
                    "learn",
                    "contact",
                    "message",
                    "whatsapp",
                    "website",
                    "visit",
                    "get",
                ):
                    if word in txt:
                        score += 10

                if "l.facebook.com" not in href.lower():
                    score += 2

                return score

            chosen_links.sort(key=link_score, reverse=True)

            link, url = chosen_links[0]

            button_text = " ".join(link.get_text(" ", strip=True).split())
            if not button_text:
                button_text = "Ad destination"

            media_items = self._find_media_for_button(link, max_items=10)

            merged_media, is_new = self._record_ad(
                button_text, url, running_days, media_items
            )

            if is_new is None:
                continue

            fallback_count += 1
            video_count = sum(1 for m in merged_media if m["type"] == "video")
            age_note = f" [{running_days}d]" if running_days is not None else " [age?]"
            media_note = (
                f" 🎥x{video_count}" if video_count else (" 🖼️" if merged_media else "")
            )

            print(
                f"{C.SUCCESS}✅ Fallback ad{age_note}{media_note}: "
                f"{button_text[:30]}... → {C.URL}{url}{Style.RESET_ALL}\n"
            )

        if started_nodes:
            C.dim(
                f"   Robust ad-card scan: {len(started_nodes)} cards checked, "
                f"{fallback_count} new ads found.\n"
            )

    def _normalize_external_url(self, url):
        """Decode Meta redirect URLs and normalize destination URLs."""
        if not url:
            return None

        try:
            url = unquote(str(url).strip())
        except Exception:
            url = str(url).strip()

        if "l.facebook.com" in url.lower():
            decoded = self._decode_facebook_url(url)
            if decoded:
                url = decoded

        if url.startswith("www."):
            url = "https://" + url

        return url.rstrip(".,;:!?')]}")

    def _parse_running_days_from_text(self, text):
        """Parse 'Started running on ...' into age in days."""
        if not text:
            return None

        m = self.DATE_RE.search(text)
        if not m:
            return None

        date_str = re.sub(r"[.,]", "", m.group(1))
        date_str = " ".join(date_str.split()).replace("Sept", "Sep")

        for fmt in ("%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
            try:
                start_date = datetime.strptime(date_str, fmt).date()
                return max(0, (datetime.now().date() - start_date).days)
            except ValueError:
                continue

        return None

    def _running_days_for_element(self, element, max_levels=14):
        """Climb from the element to the closest container that has a start date."""
        node = element
        for _ in range(max_levels):
            if node is None or not hasattr(node, "get_text"):
                break
            text = node.get_text(" ", strip=True)
            if "Started running on" in text:
                return self._parse_running_days_from_text(text)
            node = node.parent
        return None

    def _extract_url(self, button):
        """Extract URL from button"""
        if button.get("href"):
            return button.get("href")

        if button.get("onclick"):
            urls = self._extract_urls_from_text(button.get("onclick"))
            if urls:
                return urls[0]

        parent = button.find_parent("a")
        if parent and parent.get("href"):
            return parent.get("href")

        return None

    def _decode_facebook_url(self, facebook_url):
        try:
            parsed = urlparse(facebook_url)
            params = parse_qs(parsed.query)
            if "u" in params:
                return unquote(params["u"][0])
        except:
            pass
        return None

    def _index_ad_start_dates(self, soup):
        position_index = {}
        for i, el in enumerate(soup.descendants):
            position_index[id(el)] = i

        date_positions = []
        for string_node in soup.find_all(string=re.compile(r"Started running on")):
            idx = position_index.get(id(string_node))
            if idx is None:
                continue

            container = string_node.parent
            context_text = (
                container.get_text(" ", strip=True) if container else str(string_node)
            )

            running_days = self._parse_running_days_from_text(context_text)
            if running_days is not None:
                date_positions.append((idx, running_days))

        return position_index, date_positions

    def _nearest_running_days(
        self, element, position_index, date_positions, max_distance=400
    ):
        if not date_positions:
            return None

        idx = position_index.get(id(element))
        if idx is None:
            return None

        best_days = None
        best_dist = None
        for pos, running_days in date_positions:
            dist = abs(pos - idx)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_days = running_days

        if best_dist is not None and best_dist <= max_distance:
            return best_days
        return None

    def _find_media_for_button(self, element, max_items=10):
        """Find media (videos/images) for a button"""

        def collect_videos(node):
            items, seen = [], set()
            for video in node.find_all("video"):
                src = video.get("src")
                if not src:
                    source_tag = video.find("source")
                    if source_tag:
                        src = source_tag.get("src")
                if src and src not in seen:
                    seen.add(src)
                    items.append(
                        {"type": "video", "src": src, "poster": video.get("poster")}
                    )
                    if len(items) >= max_items:
                        break
            return items

        def collect_images(node):
            items, seen = [], set()
            for img in node.find_all("img"):
                src = img.get("src")
                if src and src not in seen:
                    seen.add(src)
                    items.append({"type": "image", "src": src, "poster": None})
                    if len(items) >= max_items:
                        break
            return items

        container = element
        for _ in range(6):
            if not container or not hasattr(container, "find_all"):
                break
            videos = collect_videos(container)
            if videos:
                return videos
            container = container.parent

        container = element
        for _ in range(6):
            if not container or not hasattr(container, "find_all"):
                break
            images = collect_images(container)
            if images:
                return images
            container = container.parent

        return []

    def _record_ad(self, button_text, url, running_days, media_items):
        is_new_url = url not in self.websites
        self.websites.add(url)

        if url in self.url_to_result_index:
            existing = self.results[self.url_to_result_index[url]]

            # Fill in a missing running_days from a later sighting
            filled_days = False
            if existing.get("running_days") is None and running_days is not None:
                existing["running_days"] = running_days
                filled_days = True

            existing_srcs = {m["src"] for m in existing["media_items"]}
            added_any = False
            for m in media_items:
                if m["src"] not in existing_srcs:
                    existing_srcs.add(m["src"])
                    existing["media_items"].append(m)
                    added_any = True
            if not added_any and not filled_days:
                return existing["media_items"], None
            return existing["media_items"], False

        self.url_to_result_index[url] = len(self.results)
        self.results.append(
            {
                "button_text": button_text,
                "url": url,
                "running_days": running_days,
                "found_at": datetime.now().isoformat(),
                "media_items": list(media_items),
            }
        )
        return media_items, True

    def _is_valid_url(self, url):
        if not url:
            return False

        url = str(url).strip()
        if not url or url.startswith("#") or url.startswith("javascript:"):
            return False
        if "facebook.com" in url.lower() and "l.facebook.com" not in url.lower():
            return False
        if not (
            url.lower().startswith("http://")
            or url.lower().startswith("https://")
            or url.lower().startswith("www.")
        ):
            return False

        if self.domain_filter:
            hostname = urlparse(url if "//" in url else "https://" + url).netloc.lower()
            if not any(
                hostname == tld.lstrip(".") or hostname.endswith(tld)
                for tld in self.domain_filter
            ):
                return False

        return True

    def _extract_urls_from_text(self, text):
        urls = []
        pattern1 = r'https?://[^\s\'"<>)}\]]*'
        urls.extend(re.findall(pattern1, text))

        pattern2 = r'www\.[^\s\'"<>)}\]]*'
        www_matches = re.findall(pattern2, text)
        urls.extend(["https://" + url for url in www_matches])

        cleaned = []
        for url in urls:
            url = url.rstrip(".,;:!?'\")}]")
            if len(url) > 10 and "." in url:
                cleaned.append(url)

        return list(set(cleaned))

    def print_summary(self):
        """Print summary"""
        C.header("\n" + "=" * 70)
        C.header("📊 RESULTS SUMMARY")
        C.header("=" * 70 + "\n")

        unique_urls = sorted(set(self.websites))
        C.info(f"Total unique URLs: {len(unique_urls)}\n")
        C.info(f"Total ads (merged): {len(self.results)}\n")

        if self.skipped_too_new:
            C.warn(f"Skipped (too new): {self.skipped_too_new}\n")

        if unique_urls:
            C.header("URLS:")
            C.dim("-" * 70)
            for i, url in enumerate(unique_urls, 1):
                print(f"{Fore.WHITE}{i}. {C.URL}{url}{Fore.RESET}\n")
        else:
            C.error("❌ No URLs found")

        C.header("=" * 70 + "\n")


def read_domains_from_file(filename="list.txt"):
    """Read URLs from list.txt and get just the domain"""
    domains = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                url = line.strip()
                if not url or url.startswith("#"):
                    continue
                try:
                    parsed = urlparse(url if "//" in url else "https://" + url)
                    domain = parsed.netloc.lower()
                    if domain and domain not in domains:
                        domains.append(domain)
                except:
                    continue
        C.success(f"✅ Loaded {len(domains)} domains from list.txt\n")
        return domains
    except FileNotFoundError:
        C.error(
            f"❌ list.txt not found. Create it and add one domain or URL per line.\n"
        )
        return []


def send_to_telegram(file_path, bot_token, chat_id, ship_page_url=None):
    """Send HTML file + URL to Telegram bot with clickable link"""
    if not bot_token or not chat_id:
        C.error(
            "❌ Add BOT_TOKEN and CHAT_ID in the SETTINGS section at the top of this file.\n"
        )
        return False

    try:
        import requests

        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

        with open(file_path, "rb") as f:
            files = {"document": f}

            if ship_page_url:
                message_text = (
                    "✨ <b>Ad Dashboard Ready!</b>\n\n"
                    "🌐 <b>Live URL:</b>\n"
                    f"<a href='{ship_page_url}'>🔗 Open Dashboard</a>\n\n"
                    "⏱️ <b>Live for:</b> 7 days\n"
                    "📊 <b>Status:</b> ✅ Active"
                )
            else:
                message_text = "📊 <b>Ad Dashboard</b>\n\nFile attached below"

            data = {"chat_id": chat_id, "caption": message_text, "parse_mode": "HTML"}

            response = requests.post(url, files=files, data=data)

        if response.ok:
            C.success(f"✅ Sent to Telegram!\n")
            if ship_page_url:
                C.success(f"🔗 Dashboard live: {ship_page_url}\n")
            return True
        else:
            C.error(f"❌ Telegram error: {response.text}\n")
            return False
    except Exception as e:
        C.error(f"❌ Failed to send: {e}\n")
        return False


def upload_to_ship_page(file_path, ttl=604800):
    """Upload HTML file to ship.page and return the URL"""
    try:
        cmd = [
            "curl",
            "-X",
            "POST",
            "https://ship.page/deploy?ttl=604800",
            "-H",
            "Content-Type: text/html",
            "--data-binary",
            f"@{file_path}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            response_text = result.stdout.strip()

            try:
                response_json = json.loads(response_text)
                ship_url = response_json.get("url")
                slug = response_json.get("slug")
                expires = response_json.get("expires_at")

                if ship_url:
                    C.success(f"✅ Uploaded to ship.page!\n")
                    C.info(f"📍 Slug: {slug}\n")
                    C.url(f"🔗 URL: {ship_url}\n")
                    C.info(f"⏰ Expires: {expires}\n")
                    return ship_url
                else:
                    C.error(f"❌ No URL in response\n")
                    return None
            except json.JSONDecodeError:
                C.error(f"❌ Could not parse response: {response_text}\n")
                return None
        else:
            C.error(f"❌ Ship.page error: {result.stderr}\n")
            return None
    except Exception as e:
        C.error(f"❌ Failed to upload to ship.page: {e}\n")
        return None


def parse_command_line_args():
    parser = argparse.ArgumentParser(description="Scrape Meta Ads Library domains.")
    parser.add_argument("--country", help="Country code, for example AE")
    parser.add_argument("--scrolls", type=int, help="Maximum scrolls per domain")
    slow_group = parser.add_mutually_exclusive_group()
    slow_group.add_argument(
        "--slow-internet",
        dest="slow_internet",
        action="store_true",
        help="Use slower network timings",
    )
    slow_group.add_argument(
        "--no-slow-internet",
        dest="slow_internet",
        action="store_false",
        help="Use normal network timings",
    )
    parser.set_defaults(slow_internet=None)
    parser.add_argument(
        "--min-days", type=int, help="Minimum days an ad must have been running"
    )
    return parser.parse_args()


def publish_dashboard(json_filepath, status_note=None):
    """Send JSON to GitHub, build HTML (loads from GitHub), share it."""
    json_manager = JSONDataManager()
    html_generator = BeautifulHTMLGenerator()

    ads_json = json_manager.load_ads_data(json_filepath)
    if not ads_json:
        C.error("❌ Could not read the local JSON file\n")
        return None

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    github_file = f"data/ads_data_{stamp}.json"
    data_url = upload_json_to_github(ads_json, github_file)
    if not data_url:
        C.error("❌ Stopped: JSON was not sent to GitHub\n")
        return None

    C.info("\n💾 Creating HTML dashboard...\n")
    html_content = html_generator.create_dashboard(data_url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = "dashboard_all_domains_STOPPED_" if status_note else "dashboard_all_domains_"
    dashboard_path = html_generator.save_dashboard(
        html_content, filename=f"{name}{timestamp}.html"
    )

    ship_page_url = upload_to_ship_page(dashboard_path)
    send_to_telegram(
        dashboard_path,
        BOT_TOKEN,
        CHAT_ID,
        ship_page_url=ship_page_url,
    )

    if status_note:
        C.warn(f"⚠️  Status: {status_note}\n")
    C.success(f"📄 JSON file (local copy):\n")
    C.url(f"   {json_filepath}\n")
    C.success(f"🌐 HTML file:\n")
    C.url(f"   {dashboard_path}\n")
    return dashboard_path


def main():
    C.header("\n" + "🚀" * 15)
    C.header("Meta Ads Scraper - JSON -> GitHub -> HTML (loads from GitHub)")
    C.header("🚀" * 15 + "\n")

    json_filepath = None
    all_ads = []
    total_websites = set()

    try:
        domains = read_domains_from_file("list.txt")
        if not domains:
            return

        args = parse_command_line_args()

        country = (
            args.country
            or input(C.prompt("🌍 Country (default AE): ")).strip().upper()
            or "AE"
        )

        if args.scrolls is not None:
            scroll_limit = max(0, args.scrolls)
        else:
            raw = input(C.prompt("📜 Number of scrolls (default 10): ")).strip() or "10"
            scroll_limit = int(raw) if raw.isdigit() else 10

        slow_internet = args.slow_internet
        if slow_internet is None:
            slow_internet = (
                input(C.prompt("🐌 Slow internet? (y/n): ")).strip().lower() == "y"
            )

        if args.min_days is not None:
            min_days_running = max(0, args.min_days)
        else:
            raw_min_days = input(C.prompt("⏳ Min days running (default: 5): ")).strip()
            min_days_running = int(raw_min_days) if raw_min_days.isdigit() else 5

        C.info("\n📌 Controls:\n")
        C.info("   • ENTER = Stop current site and go to next\n")
        C.info("   • CTRL+C = Stop everything and save\n\n")

        json_manager = JSONDataManager()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = f"ads_data_batch_{timestamp}.json"
        json_filepath = os.path.join(json_manager.output_dir, json_filename)

        initial_data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "search_query": f"{len(domains)} domains",
                "country": country,
                "total_ads": 0,
                "unique_websites": 0,
                "skipped_too_new": 0,
            },
            "ads": [],
        }

        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, indent=2, ensure_ascii=False)

        C.success(f"📄 Created JSON: {json_filepath}\n")

        for idx, domain in enumerate(domains, 1):
            C.header(f"\n[{idx}/{len(domains)}] Searching: {domain}\n")

            scraper = MetaAdsScraper(
                domain_filter=None,
                scroll_limit=scroll_limit,
                slow_internet=slow_internet,
                min_days_running=min_days_running,
            )

            scraper.search_meta_ads_library(domain, country)

            all_ads.extend(scraper.results)
            total_websites.update(scraper.websites)

            updated_data = {
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "search_query": f"{len(domains)} domains",
                    "country": country,
                    "total_ads": len(all_ads),
                    "unique_websites": len(total_websites),
                    "skipped_too_new": 0,
                },
                "ads": all_ads,
            }

            with open(json_filepath, "w", encoding="utf-8") as f:
                json.dump(updated_data, f, indent=2, ensure_ascii=False)

            C.success(f"✅ Found {len(scraper.results)} ads from {domain}\n")
            C.success(f"📝 Updated JSON: {len(all_ads)} total ads\n")

            if idx < len(domains):
                C.info(f"⏳ Waiting 3s...\n")
                time.sleep(3)

        publish_dashboard(json_filepath)

        C.success(f"\n✨ DONE!\n")
        C.success(f"📊 Total ads collected: {len(all_ads)}\n")
        C.success(f"🌐 From {len(total_websites)} websites\n")

    except KeyboardInterrupt:
        C.warn("\n\n⏹️  CTRL+C detected - Stopping everything...\n")

        if json_filepath and all_ads:
            publish_dashboard(json_filepath, status_note="Stopped by user (CTRL+C)")
        elif json_filepath:
            C.error(f"❌ No ads collected (script stopped early)\n")

    except Exception as e:
        C.error(f"\n❌ ERROR: {str(e)}\n")
        import traceback

        traceback.print_exc()

        if json_filepath and all_ads:
            publish_dashboard(json_filepath, status_note=f"Error: {str(e)}")
        elif json_filepath:
            C.error(f"❌ Could not create HTML (no ads collected)\n")


if __name__ == "__main__":
    main()
