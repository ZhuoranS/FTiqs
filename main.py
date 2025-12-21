import requests
import os
import time
import json
from datetime import datetime, timedelta, timezone

# --- Configuration ---
# You can add as many query blocks as you want here
SEARCH_QUERIES = [
    {
        "origins": "SFO,LAX,SEA",
        "destinations": "DOH,DXB,AUH,IST,HKG,SIN,AKL,SYD,SGN,HAN,HND,NRT,TPE,ICN,PEK,PVG,PKX",
        "start_date": "2026-12-10",
        "end_date": "2026-12-28",
        "label": "SFO->ASA"
    },
    {
        "origins": "HKG,SIN,HND,NRT,TPE,ICN,PEK,PVG,PKX",
        "destinations": "SFO,LAX,SEA,YVR,PHX,ORD,YYZ,JFK,EWR,BOS,DFW,IAH,SNA,ONT",
        "start_date": "2027-01-02",
        "end_date": "2027-01-11",
        "label": "ASA->SFO"
    }
]

CABIN_CODE = "J"
SAVER_THRESHOLD = 125000
STATE_FILE = "last_seen_savers.json"

# Credentials
API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
DISCORD_USER_ID = "787603445729329163"

# Heartbeat Settings
HEARTBEAT_INTERVAL = 1200  # 20 minutes
last_discord_time = 0     # Tracks when we last messaged Discord

REGIONS = {
    "MIDDLE EAST": ["DOH", "DXB", "AUH", "IST"],
    "EAST ASIA & OCEANIA": ["HKG", "SIN", "AKL", "SYD", "SGN", "HAN", "HND", "NRT", "TPE", "ICN", "PEK", "PVG", "PKX"],
    "NORAM": ["SFO", "SNA", "ONT", "LAX", "SEA", "YVR", "PHX", "ORD", "YYZ", "JFK", "EWR", "BOS", "DFW", "IAH"]
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
    
    print(f"[{pst_label}] [{mode_label}] Starting checks for {len(SEARCH_QUERIES)} queries...")
    
    headers = {"Partner-Authorization": API_KEY, "accept": "application/json"}
    url = "https://seats.aero/partnerapi/search"
    
    all_raw_data = []
    
    # 1. Execute all queries
    for query in SEARCH_QUERIES:
        params = {
            "origin_airport": query["origins"],
            "destination_airport": query["destinations"],
            "start_date": query["start_date"],
            "end_date": query["end_date"],
            "sources": "qatar",
            "take": 1000
        }
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json().get('data', [])
            all_raw_data.extend(data)
            # Short sleep between queries to respect API rate limits
            time.sleep(1) 
        except Exception as e:
            print(f"API Error on {query['label']}: {e}")

    # 2. Process and Deduplicate
    categorized = {region: [] for region in REGIONS.keys()}
    categorized["OTHER"] = [] # For destinations not in the REGIONS list
    
    all_results = []
    seen_flight_keys = set() # Prevent duplicates if queries overlap

    for item in all_raw_data:
        if item.get(f"{CABIN_CODE}Available"):
            cost = int(item.get(f"{CABIN_CODE}MileageCost", "0"))
            if cost < SAVER_THRESHOLD:
                route_data = item.get('Route', {})
                origin = route_data.get('OriginAirport') or item.get('OriginAirport') or "???"
                dest = route_data.get('DestinationAirport') or item.get('DestinationAirport') or "???"
                date = item.get("Date")
                
                # Unique key for deduplication
                flight_key = f"{origin}-{dest}-{date}-{cost}"
                if flight_key in seen_flight_keys:
                    continue
                seen_flight_keys.add(flight_key)
                
                search_url = f"https://seats.aero/search?origin={origin}&destination={dest}"
                flight = {
                    "route": f"{origin} ✈️ {dest}",
                    "date": date,
                    "cost": f"{cost:,}",
                    "last_seen": to_pst_clock(item.get("UpdatedAt", "")),
                    "link": search_url,
                    "dest": dest
                }
                
                assigned = False
                for region, codes in REGIONS.items():
                    if dest in codes:
                        categorized[region].append(flight)
                        assigned = True
                        break
                if not assigned:
                    categorized["OTHER"].append(flight)
                    
                all_results.append(flight)

    # 3. Fingerprinting (Sorted to ensure consistency)
    current_fp = "NONE" if not all_results else "|".join(sorted([f"{f['route']}:{f['date']}:{f['cost']}" for f in all_results]))
    current_time = time.time()

    # --- DISCORD LOGIC ---
    
    # NO CHANGES
    if current_fp == last_fingerprint:
        if (current_time - last_discord_time) >= HEARTBEAT_INTERVAL:
            msg = f"ℹ️ **Status Check** [{pst_label}]\nNo changes found across {len(SEARCH_QUERIES)} searches in {mode_label} mode."
            if DISCORD_WEBHOOK:
                requests.post(DISCORD_WEBHOOK, json={"content": msg})
            last_discord_time = current_time
            print("   -> Heartbeat sent.")
        else:
            print(f"   -> No changes. (Quiet)")
        return current_fp

    # CHANGE DETECTED
    last_discord_time = current_time
    
    if current_fp == "NONE":
        msg = f"📉 **Availability Cleared ({pst_label})** - No saver seats currently found in any searches."
    else:
        mention = f"<@{DISCORD_USER_ID}> "
        msg = f"{mention}🔥 **SAVER UPDATE ({pst_label})** 🔥\n"
        for region, flights in categorized.items():
            if not flights: continue
            msg += f"\n📍 **{region}**\n"
            for f in sorted(flights, key=lambda x: x['date']):
                msg += f"✅ {f['date']} | **{f['route']}** | {f['cost']} Avios | <[View Search]({f['link']})> | *Seen {f['last_seen']}*\n"

    if DISCORD_WEBHOOK:
        # Check Discord's 2000 character limit
        if len(msg) > 2000:
            for x in range(0, len(msg), 2000):
                requests.post(DISCORD_WEBHOOK, json={"content": msg[x:x+2000]})
        else:
            requests.post(DISCORD_WEBHOOK, json={"content": msg})
    
    with open(STATE_FILE, "w") as f: 
        f.write(current_fp)
    return current_fp

if __name__ == "__main__":
    last_fp = ""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: last_fp = f.read().strip()
        except: pass

    while True: 
        pst_now = get_pst_now()
        
        # Release window: 2:30 PM - 5:30 PM PST
        is_release_window = (pst_now.hour == 14 and pst_now.minute >= 30) or \
                             (pst_now.hour in [15, 16]) or \
                             (pst_now.hour == 17 and pst_now.minute <= 30)
        
        last_fp = check_flights(last_fp, is_release_window)
        
        # 90s frequency in window, 600s otherwise
        sleep_time = 90 if is_release_window else 600
        time.sleep(sleep_time)
