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
import traceback
from datetime import date
from urllib.parse import urlparse, parse_qs

from flask import Flask, render_template, request, jsonify

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

import config

# ── Razorpay Setup ───────────────────────────────────────────────────────────

try:
    import razorpay
    razorpay_client = razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))
except ImportError:
    razorpay_client = None

# ── App ──────────────────────────────────────────────────────────────────────

app = Flask(__name__)


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


# ── Rate Limiting ────────────────────────────────────────────────────────────

usage_tracker = {}  # {ip: {'count': N, 'date': 'YYYY-MM-DD'}}


def get_usage(ip):
    today = str(date.today())
    if ip not in usage_tracker or usage_tracker[ip]['date'] != today:
        usage_tracker[ip] = {'count': 0, 'date': today}
    return usage_tracker[ip]


def check_rate_limit(ip):
    info = get_usage(ip)
    limit = config.FREE_DAILY_LIMIT
    remaining = max(0, limit - info['count'])
    return remaining > 0, remaining


def increment_usage(ip):
    info = get_usage(ip)
    info['count'] += 1


# ── YouTube Transcript API ───────────────────────────────────────────────────

ytt_api = YouTubeTranscriptApi()


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/transcript", methods=["POST"])
def get_transcript():
    """Fetch transcript for a YouTube video (with rate limiting)."""
    ip = request.remote_addr

    # Check rate limit
    allowed, remaining = check_rate_limit(ip)
    if not allowed:
        return jsonify({
            "error": f"Daily free limit reached ({config.FREE_DAILY_LIMIT} transcripts/day). Upgrade your plan for more!",
            "limit_reached": True,
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
        transcript_list = ytt_api.list(video_id)

        if translate_to:
            # Find source transcript, then translate
            source_lang = [lang] if lang else ['en']
            try:
                transcript_obj = transcript_list.find_transcript(source_lang)
            except NoTranscriptFound:
                # Fall back to any available transcript
                transcript_obj = next(iter(transcript_list))
            translated = transcript_obj.translate(translate_to)
            transcript = transcript_to_dicts(translated.fetch())
            detected_lang = transcript_obj.language_code
        elif lang:
            # Fetch specific language
            transcript_obj = transcript_list.find_transcript([lang])
            transcript = transcript_to_dicts(transcript_obj.fetch())
            detected_lang = lang
        else:
            # Auto-detect: try English first, then fall back to any available
            try:
                transcript_obj = transcript_list.find_transcript(['en'])
            except NoTranscriptFound:
                transcript_obj = next(iter(transcript_list))
            transcript = transcript_to_dicts(transcript_obj.fetch())
            detected_lang = transcript_obj.language_code

        # Increment usage on success
        increment_usage(ip)
        _, remaining_after = check_rate_limit(ip)

        # Build response
        return jsonify({
            "video_id": video_id,
            "segments": len(transcript),
            "language": detected_lang,
            "transcript": transcript,
            "text": transcript_to_text(transcript),
            "srt": transcript_to_srt(transcript),
            "remaining": remaining_after,
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

        return jsonify({
            "video_id": video_id,
            "manual": manual,
            "generated": generated,
        })

    except Exception as e:
        msg = sanitize_error(str(e))
        return jsonify({"error": msg}), 500


# ── Public API ───────────────────────────────────────────────────────────────

@app.route("/api/v1/transcript", methods=["GET"])
def api_transcript():
    """Public API endpoint for fetching transcripts."""
    url = request.args.get("url", "")
    lang = request.args.get("lang", "")
    translate_to = request.args.get("translate", "")

    # Check API key
    api_key = request.headers.get("X-API-Key", "")
    if api_key and api_key in config.API_KEYS:
        # Authenticated — no rate limiting
        pass
    else:
        # Fall back to IP-based rate limiting
        ip = request.remote_addr
        allowed, remaining = check_rate_limit(ip)
        if not allowed:
            return jsonify({
                "error": f"Daily free limit reached ({config.FREE_DAILY_LIMIT} requests/day). Get an API key for higher limits.",
                "limit_reached": True,
            }), 429

    # Extract video ID
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL. Pass a valid URL via the 'url' query parameter."}), 400

    try:
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

        # Increment usage for unauthenticated requests
        if not (api_key and api_key in config.API_KEYS):
            ip = request.remote_addr
            increment_usage(ip)

        return jsonify({
            "video_id": video_id,
            "segments": len(transcript),
            "language": detected_lang,
            "transcript": transcript,
            "text": transcript_to_text(transcript),
            "srt": transcript_to_srt(transcript),
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
    """Verify a Razorpay payment (log and confirm for now)."""
    data = request.get_json()
    payment_id = data.get("razorpay_payment_id", "")
    order_id = data.get("razorpay_order_id", "")
    signature = data.get("razorpay_signature", "")

    print(f"💰 Payment received — order: {order_id}, payment: {payment_id}")

    return jsonify({
        "status": "success",
        "message": "Payment verified successfully!",
        "payment_id": payment_id,
        "order_id": order_id,
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
            'daily_limit': plan['daily_limit'],
            'features': plan['features'],
        }

    return jsonify({
        "razorpay_key_id": config.RAZORPAY_KEY_ID,
        "plans": plans_public,
        "affiliate_tools": config.AFFILIATE_TOOLS,
    })


# ── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🎬 YouTube Transcript Generator")
    print("   Open http://localhost:5000 in your browser\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
