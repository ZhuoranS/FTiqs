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
DISCORD_USER_ID = "787603445729329163" # Your ID integrated

# Region Mapping
REGIONS = {
    "MIDDLE EAST": ["DOH", "DXB", "AUH", "IST"],
    "EAST ASIA & OCEANIA": ["HKG", "SIN", "AKL", "SYD", "SGN", "HAN"]
}

def to_pst(utc_str):
    """Converts API UTC timestamp to PST clock time."""
    try:
        utc_dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        pst_tz = timezone(timedelta(hours=-8))
        return utc_dt.astimezone(pst_tz).strftime('%I:%M %p')
    except:
        return "??:?? PM"

def get_pst_now():
    """Returns the current PST time for the header."""
    pst_tz = timezone(timedelta(hours=-8))
    return datetime.now(pst_tz).strftime('%Y-%m-%d %I:%M:%S %p PST')

def check_flights(last_fingerprint):
    pst_now = get_pst_now()
    print(f"[{pst_now}] Checking availability for {ORIGINS}...")
    
    url = "https://seats.aero/partnerapi/search"
    headers = {"Partner-Authorization": API_KEY, "accept": "application/json"}
    params = {
        "origin_airport": ORIGINS,
        "destination_airport": DESTINATIONS,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "sources": "qatar",
        "take": 1000
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json().get('data', [])
    except Exception as e:
        print(f"API Error: {e}")
        return last_fingerprint

    categorized = {region: [] for region in REGIONS.keys()}
    all_results = []

    for item in data:
        if item.get(f"{CABIN_CODE}Available"):
            cost = int(item.get(f"{CABIN_CODE}MileageCost", "0"))
            if cost < SAVER_THRESHOLD:
                # Correctly extract airport codes
                route_data = item.get('Route', {})
                origin = route_data.get('OriginAirport') or item.get('OriginAirport') or "???"
                dest = route_data.get('DestinationAirport') or item.get('DestinationAirport') or "???"
                
                flight = {
                    "route": f"{origin}->{dest}",
                    "date": item.get("Date"),
                    "cost": f"{cost:,}",
                    "last_seen": to_pst(item.get("UpdatedAt", "")),
                    "dest": dest
                }
                
                # Sort into region
                for region, codes in REGIONS.items():
                    if dest in codes:
                        categorized[region].append(flight)
                        break
                all_results.append(flight)

    if not all_results:
        return "NONE"

    # Fingerprint check
    current_fp = "|".join(sorted([f"{f['route']}:{f['date']}:{f['cost']}" for f in all_results]))
    
    if current_fp == last_fingerprint:
        # HEARTBEAT (No Mention)
        if DISCORD_WEBHOOK:
            requests.post(DISCORD_WEBHOOK, json={"content": f"⏲️ [{pst_now}] Heartbeat: No changes."})
        return current_fp

    # ALERT (With Mention)
    ment
