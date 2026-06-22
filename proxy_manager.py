"""
Proxy Manager — Free rotating proxy pool for YouTube requests.
───────────────────────────────────────────────────────────────
Fetches free proxy lists, validates them against YouTube,
rotates on every request, and auto-retries on failure.

No paid proxy service required.
"""

import os
import random
import time
import threading
import requests
from datetime import datetime, timedelta

# ── Configuration ────────────────────────────────────────────────────────────

# Free proxy list APIs (return proxies in various formats)
PROXY_LIST_URLS = [
    # ProxyScrape — HTTPS proxies
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all&ssl=yes&anonymity=all",
    # Proxifly GitHub — JSON list
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    # TheSpeedX — HTTPS proxy list
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    # ShiftyTR — fresh proxies
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
    # monosans — verified proxies
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
]

# How many proxies to keep in the pool
MAX_POOL_SIZE = 80

# Refresh proxy list every N minutes
REFRESH_INTERVAL_MINUTES = 15

# Timeout for proxy validation (seconds)
VALIDATION_TIMEOUT = 8

# Max retries per transcript request with different proxies
MAX_RETRIES = 5

# Delay range between requests (seconds) to avoid detection
MIN_DELAY = 0.5
MAX_DELAY = 2.0


class ProxyManager:
    """Manages a rotating pool of free proxies for YouTube transcript requests."""

    def __init__(self):
        self._pool = []             # List of validated proxy URLs
        self._failed = set()        # Proxies that failed recently
        self._lock = threading.Lock()
        self._last_refresh = None
        self._refreshing = False

        # Custom proxy from environment (optional — for users with their own proxy)
        self._custom_proxy = os.environ.get("PROXY_URL", "").strip()

        # Start background refresh
        self._start_background_refresh()

    def _start_background_refresh(self):
        """Start a daemon thread that periodically refreshes the proxy pool."""
        def refresh_loop():
            while True:
                try:
                    self._refresh_pool()
                except Exception as e:
                    print(f"⚠️  Proxy refresh error: {e}")
                time.sleep(REFRESH_INTERVAL_MINUTES * 60)

        t = threading.Thread(target=refresh_loop, daemon=True)
        t.start()

    def _fetch_raw_proxies(self):
        """Fetch proxy lists from multiple free sources."""
        raw_proxies = set()

        for url in PROXY_LIST_URLS:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    lines = resp.text.strip().split("\n")
                    for line in lines:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        # Format: ip:port
                        if ":" in line and not line.startswith("http"):
                            raw_proxies.add(f"http://{line}")
                        elif line.startswith("http"):
                            raw_proxies.add(line)
            except Exception as e:
                print(f"  ⚠️  Failed to fetch from {url[:50]}...: {e}")
                continue

        print(f"  📋 Fetched {len(raw_proxies)} raw proxies from {len(PROXY_LIST_URLS)} sources")
        return list(raw_proxies)

    def _validate_proxy(self, proxy_url):
        """Check if a proxy can reach YouTube (lightweight check)."""
        proxies = {"http": proxy_url, "https": proxy_url}
        try:
            # Use a lightweight YouTube endpoint to validate
            resp = requests.get(
                "https://www.youtube.com/robots.txt",
                proxies=proxies,
                timeout=VALIDATION_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _refresh_pool(self):
        """Fetch and validate a fresh batch of proxies."""
        if self._refreshing:
            return
        self._refreshing = True

        print("🔄 Refreshing proxy pool...")
        raw = self._fetch_raw_proxies()
        random.shuffle(raw)

        # Validate proxies in parallel (test a subset for speed)
        candidates = raw[:200]  # Test up to 200 proxies
        validated = []

        def validate(proxy):
            if self._validate_proxy(proxy):
                validated.append(proxy)

        threads = []
        for proxy in candidates:
            if len(validated) >= MAX_POOL_SIZE:
                break
            t = threading.Thread(target=validate, args=(proxy,))
            t.start()
            threads.append(t)
            # Limit concurrent validation threads
            if len(threads) >= 30:
                for th in threads:
                    th.join(timeout=VALIDATION_TIMEOUT + 2)
                threads = []

        # Wait for remaining threads
        for th in threads:
            th.join(timeout=VALIDATION_TIMEOUT + 2)

        with self._lock:
            if validated:
                self._pool = validated[:MAX_POOL_SIZE]
                self._failed.clear()
                self._last_refresh = datetime.now()
                print(f"✅ Proxy pool refreshed: {len(self._pool)} working proxies")
            else:
                print("⚠️  No valid proxies found — will use direct connection")

        self._refreshing = False

    def get_proxy(self):
        """Get a random proxy from the pool, or None to use direct connection."""
        # If user has a custom proxy, always prefer it
        if self._custom_proxy:
            return {"http": self._custom_proxy, "https": self._custom_proxy}

        with self._lock:
            available = [p for p in self._pool if p not in self._failed]

        if not available:
            # Try a refresh if pool is empty
            if not self._pool:
                self._refresh_pool()
                with self._lock:
                    available = [p for p in self._pool if p not in self._failed]

            if not available:
                return None  # Fall back to direct connection

        proxy_url = random.choice(available)
        return {"http": proxy_url, "https": proxy_url}

    def mark_failed(self, proxy_dict):
        """Mark a proxy as failed so it's skipped in future rotations."""
        if not proxy_dict:
            return
        proxy_url = proxy_dict.get("http", "")
        if proxy_url and not self._custom_proxy:
            with self._lock:
                self._failed.add(proxy_url)

    def mark_success(self, proxy_dict):
        """Mark a proxy as working (remove from failed set if present)."""
        if not proxy_dict:
            return
        proxy_url = proxy_dict.get("http", "")
        with self._lock:
            self._failed.discard(proxy_url)

    @property
    def pool_size(self):
        with self._lock:
            return len(self._pool)

    @property
    def available_count(self):
        with self._lock:
            return len([p for p in self._pool if p not in self._failed])

    def get_throttle_delay(self):
        """Return a random delay to throttle requests and avoid detection."""
        return random.uniform(MIN_DELAY, MAX_DELAY)


# ── Singleton instance ───────────────────────────────────────────────────────

proxy_manager = ProxyManager()
