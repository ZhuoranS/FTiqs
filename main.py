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

# Heartbeat Settings
HEARTBEAT_INTERVAL = 900  # 15 minutes (in seconds)
last_discord_time = 0     # Tracks when we last messaged Discord

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

def check_flights(last_fingerprint, is_high_freq):
    global last_discord_time
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

    # Generate current fingerprint
    current_fp = "NONE" if not all_results else "|".join(sorted([f"{f['route']}:{f['date']}:{f['cost']}" for f in all_results]))
    
    current_time = time.time()

    # --- DISCORD LOGIC ---
    
    # 1. NO CHANGES detected
    if current_fp == last_fingerprint:
        # Only send heartbeat if 15 minutes have passed
        if (current_time - last_discord_time) >= HEARTBEAT_INTERVAL:
            msg = f"ℹ️ **Status Check** [{pst_label}]\nNo changes found in {mode_label} mode."
            if DISCORD_WEBHOOK:
                requests.post(DISCORD_WEBHOOK, json={"content": msg})
            last_discord_time = current_time # Reset heartbeat timer
            print("   -> 15m Heartbeat sent.")
        else:
            print(f"   -> No changes. (Next heartbeat in {int((HEARTBEAT_INTERVAL - (current_time - last_discord_time))/60)} mins)")
        return current_fp

    # 2. CHANGE detected (Flights added or removed)
    last_discord_time = current_time # Reset heartbeat timer because we are sending an update
    
    if current_fp == "NONE":
        msg = f"📉 **Availability Cleared ({pst_label})** - No saver seats currently found."
    else:
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

    while True: 
        pst_now = get_pst_now()
        
        # RELEASE WINDOW LOGIC: 2:30 PM - 5:30 PM PST
        is_release_window = (pst_now.hour == 14 and pst_now.minute >= 30) or \
                             (pst_now.hour in [15, 16]) or \
                             (pst_now.hour == 17 and pst_now.minute <= 30)
        
        last_fp = check_flights(last_fp, is_release_window)
        
        # Sleep 30s during release window, 300s otherwise
        sleep_time = 30 if is_release_window else 300
        time.sleep(sleep_time)
