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
    """Returns current datetime object in PST."""
    pst_tz = timezone(timedelta(hours=-8))
    return datetime.now(pst_tz)

def to_pst_clock(utc_str):
    """Converts API UTC timestamp to PST clock time."""
    try:
        utc_dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        pst_tz = timezone(timedelta(hours=-8))
        return utc_dt.astimezone(pst_tz).strftime('%I:%M %p')
    except:
        return "??:?? PM"

def check_flights(last_fingerprint, is_high_freq):
    pst_now = get_pst_now()
    pst_label = pst_now.strftime('%Y-%m-%d %I:%M:%S %p PST')
    mode_label = "🚀 HIGH FREQUENCY" if is_high_freq else "⏲️ STANDARD"
    
    print(f"[{pst_label}] [{mode_label}] Querying availability...")
    
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
                route_data = item.get('Route', {})
                origin = route_data.get('OriginAirport') or item.get('OriginAirport') or "???"
                dest = route_data.get('DestinationAirport') or item.get('DestinationAirport') or "???"
                
                flight = {
                    "route": f"{origin}->{dest}",
                    "date": item.get("Date"),
                    "cost": f"{cost:,}",
                    "last_seen": to_pst_clock(item.get("UpdatedAt", "")),
                    "dest": dest
                }
                for region, codes in REGIONS.items():
                    if dest in codes:
                        categorized[region].append(flight)
                        break
                all_results.append(flight)

    if not all_results:
        return "NONE"

    current_fp = "|".join(sorted([f"{f['route']}:{f['date']}:{f['cost']}" for f in all_results]))
    
    if current_fp == last_fingerprint:
        # Heartbeat
        if DISCORD_WEBHOOK:
            requests.post(DISCORD_WEBHOOK, json={"content": f"{mode_label} [{pst_label}] No changes."})
        return current_fp

    # ALERT
    mention = f"<@{DISCORD_USER_ID}> "
    msg = f"{mention}🔥 **SAVER UPDATE ({pst_label})** 🔥\n"
    for region, flights in categorized.items():
        if not flights: continue
        msg += f"\n📍 **{region}**\n"
        for f in sorted(flights, key=lambda x: x['date'], reverse=True):
            msg += f"✅ {f['route']} | {f['date']} | {f['cost']} Avios | *Seen {f['last_seen']}*\n"

    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": msg})
    
    with open(STATE_FILE, "w") as f: f.write(current_fp)
    return current_fp

if __name__ == "__main__":
    last_fp = ""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: last_fp = f.read().strip()
        except: pass

    start_time = time.time()
    # Continuous loop for 55 minutes
    while time.time() - start_time < 3300: 
        pst_now = get_pst_now()
        
        # LOGIC: If between 2:30 PM and 5:30 PM PST, increase frequency
        # This covers the 4:00 PM release window with a buffer
        is_release_window = (pst_now.hour == 14 and pst_now.minute >= 30) or \
                             (pst_now.hour in [15, 16]) or \
                             (pst_now.hour == 17 and pst_now.minute <= 30)
        
        last_fp = check_flights(last_fp, is_release_window)
        
        # Sleep 60s during release window, 300s otherwise
        sleep_time = 60 if is_release_window else 300
        time.sleep(sleep_time)
