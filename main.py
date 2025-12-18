import requests
import os
import time

# --- Configuration ---
ORIGIN = "SFO"
DESTINATION = "DOH"
START_DATE = "2026-12-01"
END_DATE = "2026-12-28"
CABIN_CODE = "J"          # Business Class
SAVER_THRESHOLD = 125000   # Catch 125k- seats

API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

def check_flights():
    print(f"[{time.strftime('%H:%M:%S')}] Searching {ORIGIN} -> {DESTINATION}...")
    
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
        return

    saver_results = []
    flexi_results = []

    for item in data:
        if item.get(f"{CABIN_CODE}Available"):
            cost = int(item.get(f"{CABIN_CODE}MileageCost", "0"))
            flight_info = {
                "date": item.get("Date"),
                "cost": f"{cost:,}",
                "direct": "Yes" if item.get("Direct") else "No"
            }
            if cost < SAVER_THRESHOLD:
                saver_results.append(flight_info)
            else:
                flexi_results.append(flight_info)

    if saver_results:
        msg = f"🔥 **SAVER QSUITES FOUND! (SFO -> DOH)**\n"
        for s in saver_results:
            msg += f"✅ {s['date']} - {s['cost']} Avios (Direct: {s['direct']})\n"
        
        if DISCORD_WEBHOOK:
            requests.post(DISCORD_WEBHOOK, json={"content": msg})
        print("Saver found! Notification sent.")
    else:
        print("No saver seats found this check.")

if __name__ == "__main__":
    # Script runs for 55 minutes, checking every 5 minutes (300 seconds)
    start_time = time.time()
    while time.time() - start_time < 3300: 
        check_flights()
        time.sleep(300)
