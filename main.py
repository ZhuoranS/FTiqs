import requests
import os

# --- Configuration ---
ORIGIN = "SFO"
DESTINATION = "DOH"
START_DATE = "2026-12-05"
END_DATE = "2026-12-30"
CABIN_CODE = "J" # J = Business

# Define what you consider a 'Saver' price for this route.
# For Qatar Business US-DOH, Saver is usually 70,000.
SAVER_THRESHOLD = 125000

API_KEY = os.getenv("SEATS_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

def send_notification(message):
    print(message)
    if DISCORD_WEBHOOK:
        # Use an embed-style look for Discord
        payload = {"content": message}
        requests.post(DISCORD_WEBHOOK, json=payload)

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

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
    except Exception as e:
        print(f"Error: {e}")
        return

    data = response.json().get('data', [])
    
    saver_results = []
    flexi_results = []

    for item in data:
        if item.get(f"{CABIN_CODE}Available"):
            cost_str = item.get(f"{CABIN_CODE}MileageCost", "0")
            cost = int(cost_str)
            
            flight_info = {
                "date": item.get("Date"),
                "cost": f"{cost:,}",
                "direct": "Yes" if item.get("Direct") else "No"
            }

            if cost < SAVER_THRESHOLD:
                saver_results.append(flight_info)
            else:
                flexi_results.append(flight_info)

    # Construct Message
    if not saver_results and not flexi_results:
        print("No seats found.")
        return

    msg = f"🔎 **Qatar Airways Availability: {ORIGIN} ✈️ {DESTINATION}**\n"
    
    if saver_results:
        msg += "\n🔥 **SAVER SEATS FOUND (CLASSIC tier)!** 🔥\n"
        for s in saver_results:
            msg += f"✅ {s['date']} - {s['cost']} Avios (Direct: {s['direct']})\n"
    
    if flexi_results:
        msg += "\n⚠️ *Flexi Seats (Double Price):*\n"
        # Only show the next 3 Flexi seats to keep the message clean
        for s in flexi_results[:3]:
            msg += f"• {s['date']} - {s['cost']} Avios\n"

    # Only send notification if a Saver is found, 
    # OR if you want an update regardless, remove this 'if'
    if saver_results:
        send_notification(msg)
    else:
        print("Found only Flexi seats. No notification sent.")

if __name__ == "__main__":
    check_flights()
