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
CABIN_CODE = "J"             # Business Class
SAVER_THRESHOLD = 125000     # Capture everything under 125k
STATE_FILE = "last_seen_savers.json"

API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

def get_pst_time():
    """Returns current time in PST (UTC-8) formatted for the header."""
    pst_tz = timezone(timedelta(hours=-8))
    # Matches format: 2025-12-17 07:48:43 PM PST
    return datetime.now(pst_tz).strftime('%Y-%m-%d %I:%M:%S %p PST')

def get_saver_fingerprint(saver_results):
    """Creates a unique fingerprint for state tracking."""
    fingerprint_parts = [
        f"{s['route']}:{s['date']}:{s['cost']}" for s in saver_results
    ]
    return "|".join(sorted(fingerprint_parts))

def load_last_fingerprint():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return f.read().strip()
        except: return ""
    return ""

def save_fingerprint(fingerprint):
    with open(STATE_FILE, "w") as f:
        f.write(fingerprint)

def check_flights(last_fingerprint):
    pst_now = get_pst_time()
    print(f"[{pst_now}] Searching {ORIGINS} -> {DESTINATIONS}...")
    
    url = "https://seats.aero/partnerapi/search"
    headers = {"Partner-Authorization": API_KEY, "accept": "application/json"}
    params = {
        "origin_airport": ORIGINS,
        "destination_airport": DESTINATIONS,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "sources": "qatar",
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json().get('data', [])
    except Exception as e:
        print(f"API Error: {e}")
        return last_fingerprint

    saver_results = []
    for item in data:
        # Check availability for the selected cabin
        if item.get(f"{CABIN_CODE}Available"):
            cost = int(item.get(f"{CABIN_CODE}MileageCost", "0"))
            
            if cost < SAVER_THRESHOLD:
                # FIX: Extract airport codes from the nested Route object
                route_obj = item.get('Route', {})
                origin = route_obj.get('OriginAirport') or item.get('OriginAirport', 'Unknown')
                dest = route_obj.get('DestinationAirport') or item.get('DestinationAirport', 'Unknown')
                
                saver_results.append({
                    "route": f"{origin}->{dest}",
                    "date": item.get("Date"),
                    "cost": f"{cost:,}",
                })

    if not saver_results:
        if last_fingerprint != "NONE":
            if DISCORD_WEBHOOK:
                requests.post(DISCORD_WEBHOOK, json={"content": f"ℹ️ [{pst_now}] No seats found under {SAVER_THRESHOLD:,} Avios."})
        return "NONE"

    current_fingerprint = get_saver_fingerprint(saver_results)

    # HEARTBEAT: If fingerprint hasn't changed, send a short verification message
    if current_fingerprint == last_fingerprint:
        heartbeat_msg = f"⏲️ [{pst_now}] Heartbeat: No changes in availability."
        print(heartbeat_msg)
        if DISCORD_WEBHOOK:
            requests.post(DISCORD_WEBHOOK, json={"content": heartbeat_msg})
        return current_fingerprint

    # NEW RESULTS OR CHANGES: Construct the message exactly as requested
    msg = f"🔥 SAVER UPDATE ({pst_now}) 🔥\n"
    for s in saver_results:
        msg += f"✅ {s['route']} | {s['date']} | {s['cost']} Avios\n"
    
    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": msg})
    
    print("Change detected! Notification sent.")
    save_fingerprint(current_fingerprint)
    return current_fingerprint

if __name__ == "__main__":
    current_last_fingerprint = load_last_fingerprint()
    start_time = time.time()
    # Continuous loop for 55 minutes
    while time.time() - start_time < 3300: 
        current_last_fingerprint = check_flights(current_last_fingerprint)
        time.sleep(300) # Wait 5 minutes
