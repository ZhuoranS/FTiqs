import requests
import os
import time
import json
from datetime import datetime, timedelta, timezone

# --- Configuration ---
ORIGINS = "SFO,LAX,SEA"
DESTINATIONS = "DOH,DXB,AUH,IST,HKG,SIN,AKL,SYD,SGN,HAN"

START_DATE = "2026-12-01"
# Narrowed to Dec to match your search range, adjust if you want broader
END_DATE = "2026-12-28" 
CABIN_CODE = "J"             # Business Class
SAVER_THRESHOLD = 125000
STATE_FILE = "last_seen_savers.json"

API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# Categorization Mapping
REGIONS = {
    "MIDDLE EAST": ["DOH", "DXB", "AUH", "IST"],
    "EAST ASIA & OCEANIA": ["HKG", "SIN", "AKL", "SYD", "SGN", "HAN"]
}

def to_pst(utc_str):
    """Converts UTC ISO string to PST formatted string."""
    try:
        # Seats.aero uses UTC ISO format (e.g. 2025-12-17T20:01:00Z)
        utc_dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        pst_tz = timezone(timedelta(hours=-8))
        return utc_dt.astimezone(pst_tz).strftime('%I:%M %p')
    except:
        return "Unknown"

def get_pst_now():
    """Returns current PST time for the header."""
    pst_tz = timezone(timedelta(hours=-8))
    return datetime.now(pst_tz).strftime('%Y-%m-%d %I:%M:%S %p PST')

def check_flights(last_fingerprint):
    pst_now = get_pst_now()
    print(f"[{pst_now}] Querying {ORIGINS} to {DESTINATIONS}...")
    
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

    # Organize results by region
    categorized = {region: [] for region in REGIONS.keys()}
    all_results = []

    for item in data:
        if item.get(f"{CABIN_CODE}Available"):
            cost = int(item.get(f"{CABIN_CODE}MileageCost", "0"))
            if cost < SAVER_THRESHOLD:
                # Extract Route
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
                
                # Assign to region
                found_region = False
                for region, codes in REGIONS.items():
                    if dest in codes:
                        categorized[region].append(flight)
                        found_region = True
                        break
                if not found_region:
                    # Fallback for unexpected airports
                    if "OTHER" not in categorized: categorized["OTHER"] = []
                    categorized["OTHER"].append(flight)
                
                all_results.append(flight)

    if not all_results:
        return "NONE"

    # Fingerprinting for deduplication (same as before)
    current_fp = "|".join(sorted([f"{f['route']}:{f['date']}:{f['cost']}" for f in all_results]))
    if current_fp == last_fingerprint:
        heartbeat = f"⏲️ [{pst_now}] Heartbeat: No changes."
        if DISCORD_WEBHOOK: requests.post(DISCORD_WEBHOOK, json={"content": heartbeat})
        return current_fp

    # Build Message
    msg = f"🔥 SAVER UPDATE ({pst_now}) 🔥\n"
    
    for region, flights in categorized.items():
        if not flights: continue
        
        msg += f"\n📍 **{region}**\n"
        # Sort by date DESCENDING (latest date on top)
        sorted_flights = sorted(flights, key=lambda x: x['date'], reverse=True)
        
        for f in sorted_flights:
            msg += f"✅ {f['route']} | {f['date']} | {f['cost']} Avios | *Seen {f['last_seen']}*\n"

    if DISCORD_WEBHOOK:
        # Split message if it exceeds Discord's 2000 char limit
        if len(msg) > 2000:
            for chunk in [msg[i:i+1900] for i in range(0, len(msg), 1900)]:
                requests.post(DISCORD_WEBHOOK, json={"content": chunk})
        else:
            requests.post(DISCORD_WEBHOOK, json={"content": msg})
    
    print(f"Update sent at {pst_now}")
    with open(STATE_FILE, "w") as f: f.write(current_fp)
    return current_fp

if __name__ == "__main__":
    last_fp = ""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f: last_fp = f.read().strip()

    start_time = time.time()
    while time.time() - start_time < 3300: 
        last_fp = check_flights(last_fp)
        time.sleep(300)
