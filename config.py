import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    try:
        with open('.env') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, val = line.strip().split('=', 1)
                    os.environ[key] = val
    except Exception:
        pass

# Rate Limiting (credits based)
FREE_DAILY_CREDITS = 5

# Razorpay credentials
_rzp_id = os.environ.get('RAZORPAY_KEY_ID', '')
_rzp_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
RAZORPAY_KEY_ID = _rzp_id.strip(' \'"') if _rzp_id else None
RAZORPAY_KEY_SECRET = _rzp_secret.strip(' \'"') if _rzp_secret else None

# Google OAuth
_google_id = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_ID = _google_id.strip(' \'"') if _google_id else None

# Redis Config
REDIS_URL = os.environ.get('KV_URL') or os.environ.get('UPSTASH_REDIS_URL') or os.environ.get('REDIS_URL')

# Pricing Plans (amounts in paise, 100 paise = Rs.1)
PLANS = {
    'basic': {
        'name': 'Basic',
        'price': 9900,
        'price_display': 'Rs.99/month',
        'daily_credits': 50,
        'features': ['50 credits/day', 'All languages', 'SRT & JSON export', 'Email support'],
    },
    'pro': {
        'name': 'Pro',
        'price': 29900,
        'price_display': 'Rs.299/month',
        'daily_credits': 500,
        'features': ['500 credits/day', 'All languages', 'All export formats', 'API access', 'Priority support'],
    },
    'unlimited': {
        'name': 'Unlimited',
        'price': 59900,
        'price_display': 'Rs.599/month',
        'daily_credits': -1,
        'features': ['Unlimited credits', 'All languages', 'All export formats', 'Full API access', 'Bulk processing', 'Priority support'],
    },
}

API_KEYS = {}


AFFILIATE_TOOLS = [
    {'name': 'InVideo', 'description': 'Create stunning videos with AI', 'url': 'https://invideo.io', 'icon': '🎥'},
    {'name': 'Kapwing', 'description': 'Online video editor & subtitle tool', 'url': 'https://kapwing.com', 'icon': '✂️'},
    {'name': 'Jasper AI', 'description': 'AI writing assistant for content', 'url': 'https://jasper.ai', 'icon': '🤖'},
    {'name': 'Semrush', 'description': 'SEO toolkit for better rankings', 'url': 'https://semrush.com', 'icon': '📊'},
]
