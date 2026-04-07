import logging
import requests

logger = logging.getLogger(__name__)

class ForexFactoryService:
    def __init__(self):
        self.url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json" # Forex Factory JSON proxy

    def get_weekly_events(self):
        """Fetches the weekly economic calendar events."""
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            data = response.json()
            
            # Filter for USD only in MVP
            usd_events = [event for event in data if event.get("country") == "USD"]
            return usd_events
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch ForexFactory calendar: {e}")
            return []

if __name__ == "__main__":
    service = ForexFactoryService()
    print(service.get_weekly_events())
