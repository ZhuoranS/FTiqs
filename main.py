import requests
import os
import time
import json
from datetime import datetime, timedelta, timezone

# --- Configuration ---
# You can now customize sources and intervals per query.
# Intervals are in seconds.
SEARCH_QUERIES = [
    {
        "label": "SFO->ASA (Qatar/PST Release Focus)",
        "origins": "SFO,LAX,SEA",
        "destinations": "DOH,DXB,AUH,IST,HKG,SIN,AKL,SYD,SGN,HAN,HND,NRT,TPE,ICN,PEK,PVG,PKX",
        "sources": "qatar",  # Custom source
        "start_date": "2026-12-10",
        "end_date": "2026-12-28",
        "high_freq_interval": 180,   # Check every 180s during release window
        "std_interval": 900,        # Check every 10m normally
        "last_run": 0,
        "fingerprint": ""
    },
    {
        "label": "ASA->SFO (Multi-Source)",
        "origins": "HKG,SIN,HND,NRT,TPE,ICN,PEK,PVG,PKX",
        "destinations": "SFO,LAX,SEA,YVR,PHX,ORD,YYZ,JFK,EWR,BOS,DFW,IAH,SNA,ONT",
        "sources": "qatar,lifemiles,alaska", # Multiple custom sources
        "start_date": "2026-12-05",
        "end_date": "2026-12-29",
        "high_freq_interval": 90,  # Check every 1.5m during release window
        "std_interval": 600,        # Check every 10m normally
        "last_run": 0,
        "fingerprint": ""
    }
]

CABIN_CODE = "J"
SAVER_THRESHOLD = 125000
STATE_FILE = "last_seen_savers.json"

# Credentials
API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
DISCORD_USER_ID = "787603445729329163"

HEARTBEAT_INTERVAL = 1200
last_discord_heartbeat = 0

REGIONS = {
    "MIDDLE EAST": ["DOH", "DXB", "AUH", "IST"],
    "EAST ASIA & OCEANIA": ["HKG", "SIN", "AKL", "SYD", "SGN", "HAN", "HND", "NRT", "TPE", "ICN", "PEK", "PVG", "PKX"],
    "NORAM": ["SFO", "SNA", "ONT", "LAX", "SEA", "YVR", "PHX", "ORD", "YYZ", "JFK", "EWR", "BOS", "DFW", "IAH"]
}

def get_pst_now():
    return datetime.now(timezone(timedelta(hours=-8)))

def to_pst_clock(utc_str):
    try:
        utc_dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        return utc_dt.astimezone(timezone(timedelta(hours=-8))).strftime('%I:%M %p')
    except:
        return "??:?? PM"

def process_query(query, is_high_freq):
    pst_now = get_pst_now()
    pst_label = pst_now.strftime('%I:%M:%S %p')
    
    print(f"[{pst_label}] Running: {query['label']} (Sources: {query['sources']})")
    
    headers = {"Partner-Authorization": API_KEY, "accept": "application/json"}
    url = "https://seats.aero/partnerapi/search"
    params = {
        "origin_airport": query["origins"],
        "destination_airport": query["destinations"],
        "start_date": query["start_date"],
        "end_date": query["end_date"],
        "sources": query["sources"],
        "take": 1000
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json().get('data', [])
    except Exception as e:
        print(f"   ! API Error: {e}")
        return query['fingerprint']

    all_results = []
    categorized = {region: [] for region in REGIONS.keys()}
    categorized["OTHER"] = []

    for item in data:
        if item.get(f"{CABIN_CODE}Available"):
            cost = int(item.get(f"{CABIN_CODE}MileageCost", "0"))
            if cost < SAVER_THRESHOLD:
                route_data = item.get('Route', {})
                origin = route_data.get('OriginAirport') or item.get('OriginAirport') or "???"
                dest = route_data.get('DestinationAirport') or item.get('DestinationAirport') or "???"
                date = item.get("Date")
                
                flight = {
                    "route": f"{origin} ✈️ {dest}",
                    "date": date,
                    "cost": f"{cost:,}",
                    "last_seen": to_pst_clock(item.get("UpdatedAt", "")),
                    "link": f"https://seats.aero/search?origin={origin}&destination={dest}",
                    "source": item.get("Source", "Unknown")
                }
                
                assigned = False
                for region, codes in REGIONS.items():
                    if dest in codes:
                        categorized[region].append(flight)
                        assigned = True
                        break
                if not assigned: categorized["OTHER"].append(flight)
                all_results.append(flight)

    # Fingerprint includes source to detect if the same seat appears on a different program
    new_fp = "NONE" if not all_results else "|".join(sorted([f"{f['route']}:{f['date']}:{f['cost']}:{f['source']}" for f in all_results]))

    if new_fp != query['fingerprint']:
        send_discord_alert(query['label'], categorized, new_fp == "NONE")
        return new_fp
    
    return query['fingerprint']

def send_discord_alert(label, categorized, cleared):
    pst_now = get_pst_now().strftime('%Y-%m-%d %I:%M %p PST')
    if cleared:
        msg = f"📉 **Availability Cleared: {label}** ({pst_now})"
    else:
        msg = f"<@{DISCORD_USER_ID}> 🔥 **SAVER UPDATE: {label}** 🔥\n*Refreshed at {pst_now}*\n"
        for region, flights in categorized.items():
            if not flights: continue
            msg += f"\n📍 **{region}**\n"
            for f in sorted(flights, key=lambda x: x['date']):
                msg += f"✅ {f['date']} | **{f['route']}** | {f['cost']} ({f['source']}) | [Link]({f['link']}) | *{f['last_seen']}*\n"

    if DISCORD_WEBHOOK:
        if len(msg) > 2000:
            for x in range(0, len(msg), 2000):
                requests.post(DISCORD_WEBHOOK, json={"content": msg[x:x+2000]})
        else:
            requests.post(DISCORD_WEBHOOK, json={"content": msg})

if __name__ == "__main__":
    # Load state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                saved_states = json.load(f)
                for q in SEARCH_QUERIES:
                    q['fingerprint'] = saved_states.get(q['label'], "")
        except: pass

    print("Checking started. Per-query intervals active.")

    while True:
        pst_now = get_pst_now()
        current_ts = time.time()
        
        # Determine if we are in the Release Window (2:30 PM - 5:30 PM PST)
        is_release_window = (pst_now.hour == 14 and pst_now.minute >= 30) or \
                             (pst_now.hour in [15, 16]) or \
                             (pst_now.hour == 17 and pst_now.minute <= 30)

        any_query_run = False

        for query in SEARCH_QUERIES:
            interval = query['high_freq_interval'] if is_release_window else query['std_interval']
            
            # Check if it is time to run this specific query
            if current_ts - query['last_run'] >= interval:
                query['fingerprint'] = process_query(query, is_release_window)
                query['last_run'] = current_ts
                any_query_run = True

        # Save state if any changes happened
        if any_query_run:
            with open(STATE_FILE, "w") as f:
                json.dump({q['label']: q['fingerprint'] for q in SEARCH_QUERIES}, f)

        # Heartbeat (Global status)
        if current_ts - last_discord_heartbeat >= HEARTBEAT_INTERVAL:
            mode = "🚀 HIGH FREQ" if is_release_window else "⏲️ STANDARD"
            requests.post(DISCORD_WEBHOOK, json={"content": f"ℹ️ **Status Check**: Bot is active. Mode: {mode}. Monitoring {len(SEARCH_QUERIES)} queries."})
            last_discord_heartbeat = current_ts

        # Small sleep to prevent CPU spiking
        time.sleep(5)
