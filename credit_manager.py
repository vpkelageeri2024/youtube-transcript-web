"""
Credit Manager — In-memory credit-based usage system.
──────────────────────────────────────────────────────
Tracks credits per IP address (free users) and per API key (paid users).
Designed for Vercel serverless: all state is in-memory (resets on cold start).
"""

import secrets
import threading
from datetime import date


# ── Plan Definitions ─────────────────────────────────────────────────────────

PLAN_CREDITS = {
    'free':      5,       # 5 credits/day
    'basic':     50,      # 50 credits/day
    'pro':       500,     # 500 credits/day
    'unlimited': -1,      # Unlimited (-1 means no cap)
}


# ── In-Memory Storage ────────────────────────────────────────────────────────

# Usage store: {identifier: {credits: int, plan: str, daily_limit: int, date: str}}
_usage_store = {}

# API key store: {api_key: {plan: str, created: str}}
_api_key_store = {}

# User plans store: {identifier: plan_name}
_user_plans = {}

_lock = threading.Lock()


# ── Internal Helpers ─────────────────────────────────────────────────────────

def _today():
    """Return today's date as ISO string."""
    return date.today().isoformat()


def set_user_plan(identifier, plan):
    """Set an active plan for a user identifier."""
    with _lock:
        _user_plans[identifier] = plan
        
        # Immediately update their current credits if they exist for today
        today = _today()
        entry = _usage_store.get(identifier)
        if entry and entry['date'] == today and entry['plan'] != plan:
            daily_limit = PLAN_CREDITS.get(plan, PLAN_CREDITS['free'])
            entry['plan'] = plan
            entry['daily_limit'] = daily_limit
            entry['credits'] = daily_limit


def _get_or_create_entry(identifier, plan=None):
    """
    Get the usage entry for an identifier, creating or resetting it if needed.
    Daily credits reset when the date changes.
    """
    today = _today()

    with _lock:
        active_plan = plan or _user_plans.get(identifier, 'free')
        daily_limit = PLAN_CREDITS.get(active_plan, PLAN_CREDITS['free'])

        entry = _usage_store.get(identifier)

        if entry is None or entry['date'] != today:
            # New user or new day — reset credits
            _usage_store[identifier] = {
                'credits': daily_limit,
                'plan': active_plan,
                'daily_limit': daily_limit,
                'date': today,
            }
            return _usage_store[identifier]

        # Existing entry for today — update plan if it changed
        if entry['plan'] != active_plan:
            entry['plan'] = active_plan
            entry['daily_limit'] = daily_limit
            entry['credits'] = daily_limit

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
    entry = _get_or_create_entry(identifier, plan)

    with _lock:
        # Unlimited plan — never deduct
        if entry['daily_limit'] == -1:
            return (True, -1, -1)

        if entry['credits'] <= 0:
            return (False, 0, entry['daily_limit'])

        entry['credits'] -= 1
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
        _api_key_store[api_key] = {
            'plan': plan,
            'created': today,
        }

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
        return {
            'active_users': len(_usage_store),
            'api_keys_issued': len(_api_key_store),
        }
