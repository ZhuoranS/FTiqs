import requests
import os
import time
import json
from datetime import datetime, timedelta, timezone

# --- Configuration ---
ORIGINS = "SFO,LAX,SEA"
DESTINATIONS = "DOH,DXB,AUH,IST,HKG,SIN,AKL,SYD,SGN,HAN"
START_DATE = "2026-12-01"
END_DATE = "2026-12-28"
CABIN_CODE = "J"
SAVER_THRESHOLD = 125000
STATE_FILE = "last_seen_savers.json"

# Credentials
API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
DISCORD_USER_ID = "787603445729329163"

# Region Mapping
REGIONS = {
    "MIDDLE EAST": ["DOH", "DXB", "AUH", "IST"],
    "EAST ASIA & OCEANIA": ["HKG", "SIN", "AKL", "SYD", "SGN", "HAN"]
}

def get_pst_now():
    pst_tz = timezone(timedelta(hours=-8))
    return datetime.now(pst_tz)

def to_pst_clock(utc_str):
    try:
        utc_dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        pst_tz = timezone(timedelta(hours=-8))
        return utc_dt.astimezone(pst_tz).strftime('%I:%M %p')
    except:
        return "??:?? PM"

def check_flights(last_fingerprint, is_sniper_mode):
    pst_now = get_pst_now()
    pst_label = pst_now.strftime('%Y-%m-%d %I:%M:%S %p PST')
    mode_label = "🎯 SNIPER MODE (1m)" if is_sniper_mode else "📡 BACKGROUND (4m)"
    
    url = "https://seats.aero/partnerapi/search"
    headers = {"Partner-Authorization": API_KEY, "accept": "application/json"}
    params = {
        "origin_airport": ORIGINS,
        "destination_airport"
