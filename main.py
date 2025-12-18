import requests
import os
import time
import json

# --- Configuration ---
ORIGIN = "SFO"
DESTINATION = "DOH"
START_DATE = "2026-12-01"
END_DATE = "2026-12-28"
CABIN_CODE = "J"          # Business Class
SAVER_THRESHOLD = 125000   # Catch 125k seats
STATE_FILE = "last_seen_savers.json"

API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

def get_saver_fingerprint(saver_results):
    """Creates a unique string representing current saver availability."""
    sorted_results = sorted(saver_results, key=lambda x: x['date'])
    return "|".join([f"{s['date']}:{s['cost']}" for s in sorted_results])

def load_last_fingerprint():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return f.read().strip()
        except:
            return ""
    return ""

def save_fingerprint(fingerprint):
    with open(STATE_FILE, "w") as f:
        f.write(fingerprint)

def check_flights(last_fingerprint):
    now_str = time.strftime('%H:%M:%S')
    print(f"[{now_str}] Searching {ORIGIN} -> {DESTINATION}...")
    
    url = "https://seats.aero/partnerapi/search"
    headers = {"Partner-Authorization": API_KEY, "accept": "application/json"}
    params = {
        "origin_airport": ORIGIN,
        "destination_airport": DESTINATION,
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
        if item.get(f"{CABIN_CODE}Available"):
            cost = int(item.get(f"{CABIN_CODE}MileageCost", "0"))
            if cost < SAVER_THRESHOLD:
                saver_results.append({
                    "date": item.get("Date"),
                    "cost": f"{cost:,}",
                    "direct": "Yes" if item.get("Direct") else "No"
                })

    if not saver_results:
        # If absolutely no seats exist, send a status update
        if last_fingerprint != "NONE":
            if DISCORD_WEBHOOK:
                requests.post(DISCORD_WEBHOOK, json={"content": f"ℹ️ [{now_str}] No saver seats currently available for {ORIGIN}-{DESTINATION}."})
        return "NONE"

    current_fingerprint = get_saver_fingerprint(saver_results)

    if current_fingerprint == last_fingerprint:
        # FINGERPRINT MATCH: Send a short heartbeat message
        heartbeat_msg = f"⏲️ [{now_str}] Checked {ORIGIN}-{DESTINATION}: No changes in availability."
        print(heartbeat_msg)
        if DISCORD_WEBHOOK:
            requests.post(DISCORD_WEBHOOK, json={"content": heartbeat_msg})
        return current_fingerprint

    # NEW RESULTS OR CHANGES FOUND!
    msg = f"🔥 **SAVER QSUITES UPDATE! ({ORIGIN} -> {DESTINATION})** 🔥\n"
    for s in saver_results:
        msg += f"✅ {s['date']} - {s['cost']} Avios (Direct: {s['direct']})\n"
    
    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": msg})
    
    print("Change detected! Full notification sent.")
    save_fingerprint(current_fingerprint)
    return current_fingerprint

if __name__ == "__main__":
    current_last_fingerprint = load_last_fingerprint()

    start_time = time.time()
    # Script runs for 55 minutes, checking every 5 minutes
    while time.time() - start_time < 3300: 
        current_last_fingerprint = check_flights(current_last_fingerprint)
        time.sleep(300)
