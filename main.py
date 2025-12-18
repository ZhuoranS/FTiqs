import requests
import os

# Configuration
ORIGIN = "SFO"
DESTINATION = "DOH"
START_DATE = "2026-12-05"
END_DATE = "2026-12-30"

# Set desired cabin: 'J' = Business, 'F' = First, 'Y' = Economy, 'W' = Premium Economy
CABIN_CODE = "J" 

# Load secrets from GitHub
# Ensure your secret is exactly the key (e.g. seats:pro:123...)
API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

def send_notification(message):
    print(message)
    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": message})

def check_flights():
    url = "https://seats.aero/partnerapi/search"
    
    headers = {
        "Partner-Authorization": API_KEY,
        "accept": "application/json"
    }
    
    params = {
        "origin_airport": ORIGIN,
        "destination_airport": DESTINATION,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "sources": "qatar",
    }

    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        return

    # Data is returned in a 'data' array of Availability objects
    data = response.json().get('data', [])
    found_seats = []

    for item in data:
        # Availability objects use {Cabin}Available (bool) and {Cabin}MileageCost (str)
        is_available = item.get(f"{CABIN_CODE}Available", False)
        cost = item.get(f"{CABIN_CODE}MileageCost", "N/A")
        
        if is_available:
            found_seats.append({
                "date": item.get("Date"),
                "cost": cost,
                "source": item.get("Source")
            })

    if found_seats:
        msg = f"✈️ Found {len(found_seats)} Qatar Business (J) seats from {ORIGIN} to {DESTINATION}!"
        for s in found_seats[:10]: # List up to 10 results
            msg += f"\n- {s['date']}: {s['cost']} Avios"
        send_notification(msg)
    else:
        print(f"No {CABIN_CODE} availability found for this check.")

if __name__ == "__main__":
    check_flights()
