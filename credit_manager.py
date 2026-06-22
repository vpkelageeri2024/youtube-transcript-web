"""
Credit Manager — In-memory & Redis credit-based usage system.
──────────────────────────────────────────────────────
Tracks credits per IP address (free users) and per API key (paid users).
Can use Redis for persistence if REDIS_URL is configured, else falls back to in-memory.
"""

import secrets
import threading
from datetime import date
import json
import config

try:
    from upstash_redis import Redis as UpstashRedis
except ImportError:
    UpstashRedis = None

try:
    import redis
except ImportError:
    redis = None

redis_client = None

if getattr(config, 'UPSTASH_REST_URL', None) and getattr(config, 'UPSTASH_REST_TOKEN', None) and UpstashRedis:
    try:
        redis_client = UpstashRedis(url=config.UPSTASH_REST_URL, token=config.UPSTASH_REST_TOKEN)
        redis_client.get("test_connection")
    except Exception as e:
        print(f"Failed to connect to Upstash Redis: {e}")
        redis_client = None
elif getattr(config, 'REDIS_URL', None) and redis:
    try:
        redis_client = redis.from_url(config.REDIS_URL)
        redis_client.ping()
    except Exception as e:
        print(f"Failed to connect to standard Redis: {e}")
        redis_client = None


# ── Plan Definitions ─────────────────────────────────────────────────────────

PLAN_CREDITS = {
    'free':      5,       # 5 credits/day
    'basic':     50,      # 50 credits/day
    'pro':       500,     # 500 credits/day
    'unlimited': -1,      # Unlimited (-1 means no cap)
}


# ── In-Memory Storage Fallbacks ──────────────────────────────────────────────

# Usage store: {identifier: {credits: int, plan: str, daily_limit: int, date: str}}
_usage_store_mem = {}

# API key store: {api_key: {plan: str, created: str}}
_api_key_store_mem = {}

# User plans store: {identifier: plan_name}
_user_plans_mem = {}

# User history store: {email: [{'video_id': str, 'title': str, 'date': str}]}
_user_history_mem = {}

_lock = threading.Lock()


# ── Internal Helpers ─────────────────────────────────────────────────────────

def _load_dict(key, fallback):
    if redis_client:
        try:
            val = redis_client.get(key)
            if val:
                return json.loads(val)
            return {}
        except Exception:
            pass
    return fallback

def _save_dict(key, data, fallback):
    if redis_client:
        try:
            redis_client.set(key, json.dumps(data))
        except Exception:
            pass
    if data is not fallback:
        fallback.clear()
        fallback.update(data)

def _today():
    """Return today's date as ISO string."""
    return date.today().isoformat()


def set_user_plan(identifier, plan):
    """Set an active plan for a user identifier."""
    with _lock:
        _user_plans = _load_dict('user_plans', _user_plans_mem)
        _user_plans[identifier] = plan
        _save_dict('user_plans', _user_plans, _user_plans_mem)
        
        # Immediately update their current credits if they exist for today
        today = _today()
        _usage_store = _load_dict('usage_store', _usage_store_mem)
        entry = _usage_store.get(identifier)
        if entry and entry['date'] == today and entry['plan'] != plan:
            daily_limit = PLAN_CREDITS.get(plan, PLAN_CREDITS['free'])
            entry['plan'] = plan
            entry['daily_limit'] = daily_limit
            entry['credits'] = daily_limit
            _save_dict('usage_store', _usage_store, _usage_store_mem)


def _get_or_create_entry(identifier, plan=None):
    """
    Get the usage entry for an identifier, creating or resetting it if needed.
    Daily credits reset when the date changes.
    """
    today = _today()

    with _lock:
        _user_plans = _load_dict('user_plans', _user_plans_mem)
        active_plan = plan or _user_plans.get(identifier, 'free')
        daily_limit = PLAN_CREDITS.get(active_plan, PLAN_CREDITS['free'])

        _usage_store = _load_dict('usage_store', _usage_store_mem)
        entry = _usage_store.get(identifier)

        if entry is None or entry['date'] != today:
            # New user or new day — reset credits
            _usage_store[identifier] = {
                'credits': daily_limit,
                'plan': active_plan,
                'daily_limit': daily_limit,
                'date': today,
            }
            _save_dict('usage_store', _usage_store, _usage_store_mem)
            return _usage_store[identifier]

        # Existing entry for today — update plan if it changed
        if entry['plan'] != active_plan:
            entry['plan'] = active_plan
            entry['daily_limit'] = daily_limit
            entry['credits'] = daily_limit
            _save_dict('usage_store', _usage_store, _usage_store_mem)

        return entry


# ── Public API ───────────────────────────────────────────────────────────────

def get_credits(identifier, plan=None):
    """
    Get remaining credits for an identifier (IP address or API key).

    Returns:
        dict: {credits: int, plan: str, daily_limit: int}
    """
    entry = _get_or_create_entry(identifier, plan)
    return {
        'credits': entry['credits'],
        'plan': entry['plan'],
        'daily_limit': entry['daily_limit'],
    }


def use_credit(identifier, plan=None):
    """
    Deduct 1 credit from an identifier.

    Returns:
        tuple: (success: bool, remaining: int, daily_limit: int)
    """
    # ensure it's created or reset for today
    _get_or_create_entry(identifier, plan)

    with _lock:
        _usage_store = _load_dict('usage_store', _usage_store_mem)
        entry = _usage_store.get(identifier)
        if not entry:
            # edge case, should not happen due to _get_or_create_entry above
            return (False, 0, PLAN_CREDITS.get(plan or 'free', 5))

        # Unlimited plan — never deduct
        if entry['daily_limit'] == -1:
            return (True, -1, -1)

        if entry['credits'] <= 0:
            return (False, 0, entry['daily_limit'])

        entry['credits'] -= 1
        _save_dict('usage_store', _usage_store, _usage_store_mem)
        return (True, entry['credits'], entry['daily_limit'])


def generate_api_key(plan):
    """
    Generate a unique API key for a paid user.

    Args:
        plan: One of 'basic', 'pro', 'unlimited'

    Returns:
        str: The generated API key (ytg_<32-char-hex>)
    """
    api_key = f"ytg_{secrets.token_hex(16)}"
    today = _today()

    with _lock:
        _api_key_store = _load_dict('api_key_store', _api_key_store_mem)
        _api_key_store[api_key] = {
            'plan': plan,
            'created': today,
        }
        _save_dict('api_key_store', _api_key_store, _api_key_store_mem)

    return api_key


def validate_api_key(key):
    """
    Check if an API key is valid.

    Returns:
        dict or None: {plan: str, created: str} if valid, None if invalid
    """
    if not key or not key.startswith('ytg_'):
        return None

    with _lock:
        _api_key_store = _load_dict('api_key_store', _api_key_store_mem)
        return _api_key_store.get(key)


def get_plan_for_api_key(key):
    """
    Get the plan name associated with an API key.

    Returns:
        str or None: Plan name ('basic', 'pro', 'unlimited') or None
    """
    info = validate_api_key(key)
    return info['plan'] if info else None


def get_stats():
    """
    Return summary stats for debugging.

    Returns:
        dict: {active_users: int, api_keys_issued: int}
    """
    with _lock:
        _usage_store = _load_dict('usage_store', _usage_store_mem)
        _api_key_store = _load_dict('api_key_store', _api_key_store_mem)
        return {
            'active_users': len(_usage_store),
            'api_keys_issued': len(_api_key_store),
        }

def save_history(email, video_id, title):
    """
    Save a video to the user's history.
    """
    with _lock:
        history = _load_dict('user_history', _user_history_mem)
        if email not in history:
            history[email] = []
        # prepend to keep most recent first
        history[email].insert(0, {'video_id': video_id, 'title': title, 'date': _today()})
        _save_dict('user_history', history, _user_history_mem)

def get_history(email):
    """
    Retrieve history for a user email.
    """
    with _lock:
        history = _load_dict('user_history', _user_history_mem)
        return history.get(email, [])
