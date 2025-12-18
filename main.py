import requests
import os
import json

# Configuration - Change these!
ORIGIN = "SFO"
DESTINATION = "DOH"
START_DATE = "2026-12-01"
END_DATE = "2026-12-26"
CABIN = "business" # economy, business, first

# Load secrets from GitHub Environment
API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK") # Optional

def send_notification(message):
    print(message)
    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": message})

def check_flights():
    url = "https://seats.aero/partnerapi/search"
    headers = {"Partner-Authorization": API_KEY, "accept": "application/json"}
    params = {
        "origin_airport": ORIGIN,
        "destination_airport": DESTINATION,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "sources": "qatar",
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        return

    data = response.json().get('data', [])
    for f in data:
        print(f)
    found_seats = [f for f in data if f['Route']['Cabin'].lower() == CABIN.lower()]

    if found_seats:
        msg = f"✈️ Found {len(found_seats)} Qatar {CABIN} seats from {ORIGIN} to {DESTINATION}!"
        for s in found_seats[:5]: # Show first 5 results
            msg += f"\n- {s['Date']}: {s['Route']['MileageCost']} Avios"
        send_notification(msg)
    else:
        print("No availability found for this check.")

if __name__ == "__main__":
    check_flights()
