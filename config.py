import os
from dotenv import load_dotenv

load_dotenv()

# Rate Limiting (credits based)
FREE_DAILY_CREDITS = 5

# Razorpay credentials
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

# Google OAuth
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')

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
