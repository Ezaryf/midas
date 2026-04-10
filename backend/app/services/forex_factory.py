import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

# Singleton instance for caching across calls
_forex_factory_instance = None

def get_forex_factory():
    global _forex_factory_instance
    if _forex_factory_instance is None:
        _forex_factory_instance = ForexFactoryService()
    return _forex_factory_instance

class ForexFactoryService:
    def __init__(self):
        self.url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        self._cache = None
        self._cache_time = 0
        self._cache_ttl = int(os.getenv("FOREX_FACTORY_CACHE_TTL_SECONDS", "900"))
        self._timeout = float(os.getenv("FOREX_FACTORY_TIMEOUT_SECONDS", "3"))
        self._backoff_until = 0.0

    def get_weekly_events(self):
        """Fetches the weekly economic calendar events."""
        now = time.time()

        if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        if now < self._backoff_until:
            return self._cache if self._cache is not None else []

        try:
            response = requests.get(self.url, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
            
            usd_events = [event for event in data if event.get("country") == "USD"]
            
            # Update cache
            self._cache = usd_events
            self._cache_time = now
            
            return usd_events
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch ForexFactory calendar: {e}")
            self._backoff_until = now + min(self._cache_ttl, 300)
            return self._cache if self._cache is not None else []

if __name__ == "__main__":
    service = ForexFactoryService()
    print(service.get_weekly_events())
