import os

# Rate Limiting
FREE_DAILY_LIMIT = 3

# Razorpay - Replace with actual keys from https://dashboard.razorpay.com/app/keys
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', 'rzp_test_T4MIOkYDvidlt9')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', 'aJou7xPs5KusH5stlwzyFNN3')

# Pricing Plans (amounts in paise, 100 paise = Rs.1)
PLANS = {
    'basic': {
        'name': 'Basic',
        'price': 9900,
        'price_display': 'Rs.99/month',
        'daily_limit': 50,
        'features': ['50 transcripts/day', 'All languages', 'SRT & JSON export', 'Email support'],
    },
    'pro': {
        'name': 'Pro',
        'price': 29900,
        'price_display': 'Rs.299/month',
        'daily_limit': 500,
        'features': ['500 transcripts/day', 'All languages', 'All export formats', 'API access', 'Priority support'],
    },
    'unlimited': {
        'name': 'Unlimited',
        'price': 59900,
        'price_display': 'Rs.599/month',
        'daily_limit': -1,
        'features': ['Unlimited transcripts', 'All languages', 'All export formats', 'Full API access', 'Bulk processing', 'Priority support'],
    },
}

API_KEYS = {}


AFFILIATE_TOOLS = [
    {'name': 'InVideo', 'description': 'Create stunning videos with AI', 'url': 'https://invideo.io', 'icon': '🎥'},
    {'name': 'Kapwing', 'description': 'Online video editor & subtitle tool', 'url': 'https://kapwing.com', 'icon': '✂️'},
    {'name': 'Jasper AI', 'description': 'AI writing assistant for content', 'url': 'https://jasper.ai', 'icon': '🤖'},
    {'name': 'Semrush', 'description': 'SEO toolkit for better rankings', 'url': 'https://semrush.com', 'icon': '📊'},
]
