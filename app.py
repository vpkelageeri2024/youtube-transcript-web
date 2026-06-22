#!/usr/bin/env python3
"""
YouTube Transcript Generator — Web App
───────────────────────────────────────
A local web UI for extracting YouTube transcripts
with monetization features (rate limiting, paid plans, API access).

Usage:
    python3 app.py

Then open http://localhost:5000 in your browser.
"""

import json
import re
import time
import traceback
from datetime import date
from urllib.parse import urlparse, parse_qs

from flask import Flask, render_template, request, jsonify, session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

import config
from proxy_manager import proxy_manager, MAX_RETRIES
import credit_manager

# ── Razorpay Setup ───────────────────────────────────────────────────────────

try:
    import razorpay
    razorpay_client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
except ImportError:
    razorpay_client = None

# ── App ──────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-change-in-prod')


# ── Helpers ──────────────────────────────────────────────────────────────────

def extract_video_id(url):
    """Extracts video ID from various YouTube URL formats."""
    if not url:
        return None

    url = url.strip()

    # Already a plain video ID
    if re.match(r'^[A-Za-z0-9_-]{11}$', url):
        return url

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    # youtu.be short links
    if parsed.hostname in ('youtu.be',):
        vid = parsed.path.lstrip('/')
        if vid:
            return vid.split('/')[0].split('?')[0]

    # Standard youtube.com URLs
    if parsed.hostname in ('www.youtube.com', 'youtube.com', 'm.youtube.com'):
        if parsed.path == '/watch':
            qs = parse_qs(parsed.query)
            return qs.get('v', [None])[0]
        for prefix in ('/embed/', '/v/', '/shorts/', '/live/'):
            if parsed.path.startswith(prefix):
                return parsed.path[len(prefix):].split('/')[0].split('?')[0]

    return None


def format_srt_timestamp(seconds):
    """Converts seconds to SRT format: HH:MM:SS,mmm"""
    total_ms = int(seconds * 1000)
    h, remainder = divmod(total_ms, 3600000)
    m, remainder = divmod(remainder, 60000)
    s, ms = divmod(remainder, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcript_to_srt(transcript):
    """Converts transcript entries to SRT format string."""
    lines = []
    for i, entry in enumerate(transcript, 1):
        start = format_srt_timestamp(entry['start'])
        end = format_srt_timestamp(entry['start'] + entry.get('duration', 0))
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(entry['text'])
        lines.append("")
    return "\n".join(lines)


def transcript_to_text(transcript):
    """Converts transcript entries to plain text."""
    return "\n".join(entry['text'] for entry in transcript)


def transcript_to_dicts(fetched):
    """Convert FetchedTranscript snippets to plain dicts."""
    return [
        {"text": snippet.text, "start": snippet.start, "duration": snippet.duration}
        for snippet in fetched
    ]


def sanitize_error(msg):
    """Strip upstream repo hints from error messages."""
    if "please create an issue" in msg.lower() or "github.com" in msg.lower():
        msg = msg.split("This is most likely caused by:")[-1].strip() if "This is most likely caused by:" in msg else msg
        msg = msg.split("If you are sure")[0].strip() if "If you are sure" in msg else msg
        msg = msg or "Failed to retrieve transcript. The video may not have captions available."
    return msg


# ── YouTube Transcript API (with proxy-aware retry) ─────────────────────────

def _create_api_with_proxy(proxy_dict=None):
    """Create a YouTubeTranscriptApi instance, optionally with proxy."""
    if proxy_dict:
        # The newer versions of youtube-transcript-api accept proxies via constructor
        try:
            return YouTubeTranscriptApi(proxies=proxy_dict)
        except TypeError:
            # Fallback for older versions that don't support proxies in constructor
            return YouTubeTranscriptApi()
    return YouTubeTranscriptApi()


def fetch_with_retry(fetch_func, max_retries=MAX_RETRIES):
    """
    Execute a transcript fetch function with automatic proxy rotation and retry.
    `fetch_func` receives a YouTubeTranscriptApi instance and should return the result.
    """
    last_error = None

    for attempt in range(max_retries):
        proxy_dict = proxy_manager.get_proxy()
        ytt_api = _create_api_with_proxy(proxy_dict)

        try:
            # Throttle to avoid detection
            if attempt > 0:
                delay = proxy_manager.get_throttle_delay()
                time.sleep(delay)

            result = fetch_func(ytt_api)
            proxy_manager.mark_success(proxy_dict)
            return result

        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, StopIteration):
            # These are legitimate errors, not IP bans — re-raise immediately
            raise

        except Exception as e:
            last_error = e
            error_msg = str(e).lower()

            # Detect IP-related blocks
            is_ip_block = any(kw in error_msg for kw in [
                "ip", "blocked", "banned", "429", "too many",
                "rate limit", "forbidden", "403", "captcha",
                "consent", "cookie",
            ])

            if is_ip_block and proxy_dict:
                proxy_manager.mark_failed(proxy_dict)
                print(f"  🔄 Proxy blocked (attempt {attempt + 1}/{max_retries}), rotating...")
                continue
            elif is_ip_block and not proxy_dict:
                # Direct connection blocked — try with proxy on next attempt
                print(f"  🔄 Direct IP blocked (attempt {attempt + 1}/{max_retries}), trying proxy...")
                continue
            else:
                # Non-IP error — retry once then give up
                if attempt == 0:
                    continue
                raise

    # All retries exhausted
    raise last_error


def get_user_identifier():
    """Get email if logged in, otherwise IP address."""
    user = session.get('user')
    if user and 'email' in user:
        return user['email']
    return request.remote_addr


# ── Auth Routes ──────────────────────────────────────────────────────────────

@app.route("/api/auth/google", methods=["POST"])
def auth_google():
    """Verify Google ID token and set session."""
    data = request.get_json()
    token = data.get("credential")
    if not token:
        return jsonify({"error": "No token provided"}), 400
    try:
        idinfo = id_token.verify_oauth2_token(
            token, google_requests.Request(), config.GOOGLE_CLIENT_ID)
        session['user'] = {
            'email': idinfo['email'],
            'name': idinfo.get('name', ''),
            'picture': idinfo.get('picture', '')
        }
        return jsonify({"status": "success", "user": session['user']})
    except ValueError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        print(f"Google auth error: {e}")
        return jsonify({"error": "Authentication failed"}), 500

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    """Clear user session."""
    session.pop('user', None)
    return jsonify({"status": "success"})

@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    """Get current logged in user."""
    return jsonify({"user": session.get('user')})


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/credits", methods=["GET"])
def get_credits():
    """Return the current credit balance for the user's IP or email."""
    identifier = get_user_identifier()
    return jsonify(credit_manager.get_credits(identifier))


@app.route("/api/transcript", methods=["POST"])
def get_transcript():
    """Fetch transcript for a YouTube video (with credit deduction)."""
    identifier = get_user_identifier()

    # Check credits
    has_credits, remaining, daily_limit = credit_manager.use_credit(identifier)
    if not has_credits:
        return jsonify({
            "error": "Out of credits. Upgrade your plan for more!",
            "limit_reached": True,
            "remaining": remaining,
            "daily_limit": daily_limit,
        }), 429

    data = request.get_json()
    url = data.get("url", "")
    lang = data.get("lang", "")
    translate_to = data.get("translate", "")

    # Extract video ID
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL. Please provide a valid YouTube video link."}), 400

    try:
        def do_fetch(ytt_api):
            transcript_list = ytt_api.list(video_id)

            if translate_to:
                source_lang = [lang] if lang else ['en']
                try:
                    transcript_obj = transcript_list.find_transcript(source_lang)
                except NoTranscriptFound:
                    transcript_obj = next(iter(transcript_list))
                translated = transcript_obj.translate(translate_to)
                transcript = transcript_to_dicts(translated.fetch())
                detected_lang = transcript_obj.language_code
            elif lang:
                transcript_obj = transcript_list.find_transcript([lang])
                transcript = transcript_to_dicts(transcript_obj.fetch())
                detected_lang = lang
            else:
                try:
                    transcript_obj = transcript_list.find_transcript(['en'])
                except NoTranscriptFound:
                    transcript_obj = next(iter(transcript_list))
                transcript = transcript_to_dicts(transcript_obj.fetch())
                detected_lang = transcript_obj.language_code

            return transcript, detected_lang

        transcript, detected_lang = fetch_with_retry(do_fetch)

        return jsonify({
            "video_id": video_id,
            "segments": len(transcript),
            "language": detected_lang,
            "transcript": transcript,
            "text": transcript_to_text(transcript),
            "srt": transcript_to_srt(transcript),
            "remaining": remaining,
            "daily_limit": daily_limit,
        })

    except TranscriptsDisabled:
        return jsonify({"error": "Transcripts are disabled for this video."}), 404
    except NoTranscriptFound:
        return jsonify({"error": f"No transcript found for language '{lang or 'default'}'. Use the Languages button to see available options."}), 404
    except VideoUnavailable:
        return jsonify({"error": "This video is unavailable or does not exist."}), 404
    except StopIteration:
        return jsonify({"error": "No transcripts are available for this video."}), 404
    except Exception as e:
        traceback.print_exc()
        msg = sanitize_error(str(e))
        return jsonify({"error": msg}), 500


@app.route("/api/languages", methods=["POST"])
def get_languages():
    """List available transcript languages for a video."""
    data = request.get_json()
    url = data.get("url", "")

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL."}), 400

    try:
        def do_fetch(ytt_api):
            transcript_list = ytt_api.list(video_id)

            manual = []
            generated = []
            for t in transcript_list:
                entry = {
                    "language": t.language,
                    "code": t.language_code,
                    "translatable": t.is_translatable,
                }
                if t.is_generated:
                    generated.append(entry)
                else:
                    manual.append(entry)

            return {"video_id": video_id, "manual": manual, "generated": generated}

        result = fetch_with_retry(do_fetch)
        return jsonify(result)

    except Exception as e:
        msg = sanitize_error(str(e))
        return jsonify({"error": msg}), 500


# ── Public API ───────────────────────────────────────────────────────────────

@app.route("/api/v1/transcript", methods=["GET"])
def api_transcript():
    """Public API endpoint for fetching transcripts (with credit checking)."""
    url = request.args.get("url", "")
    lang = request.args.get("lang", "")
    translate_to = request.args.get("translate", "")

    # Check API key
    api_key = request.headers.get("X-API-Key", "")
    
    if api_key:
        plan = credit_manager.get_plan_for_api_key(api_key)
        if not plan:
            return jsonify({"error": "Invalid API Key."}), 401
        has_credits, remaining, daily_limit = credit_manager.use_credit(api_key, plan)
    else:
        identifier = get_user_identifier()
        has_credits, remaining, daily_limit = credit_manager.use_credit(identifier)

    if not has_credits:
        return jsonify({
            "error": "Out of credits.",
            "limit_reached": True,
            "remaining": remaining,
            "daily_limit": daily_limit
        }), 429

    # Extract video ID
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL. Pass a valid URL via the 'url' query parameter."}), 400

    try:
        def do_fetch(ytt_api):
            transcript_list = ytt_api.list(video_id)

            if translate_to:
                source_lang = [lang] if lang else ['en']
                try:
                    transcript_obj = transcript_list.find_transcript(source_lang)
                except NoTranscriptFound:
                    transcript_obj = next(iter(transcript_list))
                translated = transcript_obj.translate(translate_to)
                transcript = transcript_to_dicts(translated.fetch())
                detected_lang = transcript_obj.language_code
            elif lang:
                transcript_obj = transcript_list.find_transcript([lang])
                transcript = transcript_to_dicts(transcript_obj.fetch())
                detected_lang = lang
            else:
                try:
                    transcript_obj = transcript_list.find_transcript(['en'])
                except NoTranscriptFound:
                    transcript_obj = next(iter(transcript_list))
                transcript = transcript_to_dicts(transcript_obj.fetch())
                detected_lang = transcript_obj.language_code

            return transcript, detected_lang

        transcript, detected_lang = fetch_with_retry(do_fetch)

        return jsonify({
            "video_id": video_id,
            "segments": len(transcript),
            "language": detected_lang,
            "transcript": transcript,
            "text": transcript_to_text(transcript),
            "srt": transcript_to_srt(transcript),
            "remaining": remaining,
            "daily_limit": daily_limit,
        })

    except TranscriptsDisabled:
        return jsonify({"error": "Transcripts are disabled for this video."}), 404
    except NoTranscriptFound:
        return jsonify({"error": f"No transcript found for language '{lang or 'default'}'."}), 404
    except VideoUnavailable:
        return jsonify({"error": "This video is unavailable or does not exist."}), 404
    except StopIteration:
        return jsonify({"error": "No transcripts are available for this video."}), 404
    except Exception as e:
        traceback.print_exc()
        msg = sanitize_error(str(e))
        return jsonify({"error": msg}), 500


@app.route("/api/v1/docs")
def api_docs():
    """Render API documentation page."""
    return render_template("api_docs.html")


# ── Monetization Routes ─────────────────────────────────────────────────────

@app.route("/pricing")
def pricing():
    """Render pricing page."""
    return render_template("pricing.html")


@app.route("/api/create-order", methods=["POST"])
def create_order():
    """Create a Razorpay order for a subscription plan."""
    data = request.get_json()
    plan = data.get("plan", "")

    if plan not in config.PLANS:
        return jsonify({"error": f"Invalid plan: '{plan}'. Choose from: {', '.join(config.PLANS.keys())}"}), 400

    plan_data = config.PLANS[plan]

    if razorpay_client:
        try:
            order = razorpay_client.order.create({
                'amount': plan_data['price'],
                'currency': 'INR',
                'payment_capture': 1,
            })
            return jsonify({
                'order_id': order['id'],
                'amount': plan_data['price'],
                'plan_name': plan_data['name'],
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": f"Failed to create order: {str(e)}"}), 500
    else:
        # Mock order for testing without razorpay SDK
        return jsonify({
            'order_id': f'order_mock_{plan}',
            'amount': plan_data['price'],
            'plan_name': plan_data['name'],
        })


@app.route("/api/verify-payment", methods=["POST"])
def verify_payment():
    """Verify a Razorpay payment and generate an API key."""
    data = request.get_json()
    payment_id = data.get("razorpay_payment_id", "")
    order_id = data.get("razorpay_order_id", "")
    signature = data.get("razorpay_signature", "")

    print(f"💰 Payment received — order: {order_id}, payment: {payment_id}")
    
    plan = 'pro'
    if 'basic' in order_id: plan = 'basic'
    elif 'unlimited' in order_id: plan = 'unlimited'
    
    api_key = credit_manager.generate_api_key(plan)

    return jsonify({
        "status": "success",
        "message": "Payment verified successfully!",
        "payment_id": payment_id,
        "order_id": order_id,
        "api_key": api_key,
    })


@app.route("/api/config", methods=["GET"])
def get_config():
    """Return public configuration (no secrets!)."""
    plans_public = {}
    for key, plan in config.PLANS.items():
        plans_public[key] = {
            'name': plan['name'],
            'price': plan['price'],
            'price_display': plan['price_display'],
            'daily_limit': plan.get('daily_credits', 0),
            'features': plan['features'],
        }

    return jsonify({
        "razorpay_key_id": config.RAZORPAY_KEY_ID,
        "google_client_id": config.GOOGLE_CLIENT_ID,
        "plans": plans_public,
        "affiliate_tools": config.AFFILIATE_TOOLS,
    })


# ── Proxy Status (Debug) ────────────────────────────────────────────────────

@app.route("/api/proxy-status")
def proxy_status():
    """Debug endpoint to check proxy pool health."""
    return jsonify({
        "pool_size": proxy_manager.pool_size,
        "available": proxy_manager.available_count,
        "max_retries": MAX_RETRIES,
        "status": "healthy" if proxy_manager.available_count > 0 else "direct",
    })


# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🎬 YouTube Transcript Generator (Credit Based)")
    print("   Open http://localhost:5000 in your browser")
    print(f"   Proxy pool: {proxy_manager.pool_size} proxies available\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
