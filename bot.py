"""
Kuki Kids Bot v2 — Fully Automatic
====================================
1. Researches trending children's content online
2. Analyzes YOUR channel (views, comments, best/worst performers)
3. Compares against competitor channels
4. Picks the best topic automatically
5. Generates video via Higgsfield
6. Uploads directly to YouTube
7. Emails you a report — you do NOTHING except read the email

Setup: see README.md
"""

import os, time, json, random, smtplib, requests, logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# YouTube OAuth
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.http
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("KukiBot")

# ── Config ─────────────────────────────────────────────────────────────────────
HIGGSFIELD_API_KEY  = os.getenv("HIGGSFIELD_API_KEY")
YOUR_CHANNEL_ID     = os.getenv("YOUR_CHANNEL_ID")
COMPETITOR_CHANNELS = os.getenv("COMPETITOR_CHANNELS", "UCMEVZK5J38upc4XiRO3sqWQ").split(",")  # NuNu TV default
EMAIL_SENDER        = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD      = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENT     = os.getenv("EMAIL_RECIPIENT")
OUTPUT_DIR          = os.getenv("OUTPUT_DIR", "./videos")
TOKEN_FILE          = "youtube_token.json"
CLIENT_SECRETS_FILE = "client_secrets.json"
SERPAPI_KEY         = os.getenv("SERPAPI_KEY")  # For web research (free tier available)

os.makedirs(OUTPUT_DIR, exist_ok=True)

HIGGSFIELD_BASE = "https://api.higgsfield.ai"
HF_HEADERS = {"Authorization": f"Bearer {HIGGSFIELD_API_KEY}", "Content-Type": "application/json"}

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — WEB RESEARCH: What's trending in children's content?
# ══════════════════════════════════════════════════════════════════════════════
def research_trending_topics():
    """Search the web for trending children's YouTube content topics."""
    log.info("🌐 Researching trending children's content...")
    trending_keywords = []

    # Option A: SerpAPI (most reliable, free tier = 100 searches/month)
    if SERPAPI_KEY:
        queries = [
            "trending kids youtube shorts 2025",
            "most popular nursery rhymes youtube 2025",
            "children educational songs viral youtube",
        ]
        for query in queries:
            try:
                resp = requests.get("https://serpapi.com/search", params={
                    "q": query,
                    "api_key": SERPAPI_KEY,
                    "num": 5,
                    "tbm": "vid",
                }, timeout=15)
                results = resp.json().get("video_results", [])
                for r in results:
                    title = r.get("title", "").lower()
                    trending_keywords.extend(title.split())
            except Exception as e:
                log.warning(f"SerpAPI error: {e}")

    # Option B: YouTube search API (always available if YouTube API key exists)
    try:
        yt = _get_youtube_service_readonly()
        search_terms = ["kids songs 2025", "nursery rhymes shorts", "toddler educational songs"]
        for term in search_terms:
            resp = yt.search().list(
                q=term, part="snippet", type="video",
                videoDuration="short", order="viewCount",
                maxResults=10, relevanceLanguage="en"
            ).execute()
            for item in resp.get("items", []):
                title = item["snippet"]["title"].lower()
                trending_keywords.extend(title.split())
    except Exception as e:
        log.warning(f"YouTube trending search error: {e}")

    # Count keyword frequencies
    freq = {}
    stop_words = {"and","the","a","to","in","of","for","with","more","nursery","rhymes","kids","song","songs","video","youtube"}
    for kw in trending_keywords:
        kw = kw.strip(".,!?|+&")
        if len(kw) > 3 and kw not in stop_words:
            freq[kw] = freq.get(kw, 0) + 1

    top_trending = sorted(freq, key=freq.get, reverse=True)[:20]
    log.info(f"🔥 Top trending keywords: {top_trending[:10]}")
    return top_trending


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — CHANNEL ANALYSIS: What works on YOUR channel?
# ══════════════════════════════════════════════════════════════════════════════
def analyze_my_channel(yt_service):
    """Deep analysis of your channel: views, comments, best/worst videos."""
    log.info("📊 Analyzing your channel...")
    results = {
        "top_videos": [],
        "worst_videos": [],
        "top_keywords": [],
        "comment_insights": [],
        "avg_views": 0,
    }

    if not YOUR_CHANNEL_ID:
        log.warning("No channel ID configured — skipping channel analysis.")
        return results

    try:
        # Get all recent videos
        search_resp = yt_service.search().list(
            channelId=YOUR_CHANNEL_ID,
            part="snippet,id",
            order="date",
            maxResults=50,
            type="video"
        ).execute()

        video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
        if not video_ids:
            return results

        # Get stats for all videos
        stats_resp = yt_service.videos().list(
            id=",".join(video_ids),
            part="snippet,statistics"
        ).execute()

        videos = []
        for item in stats_resp.get("items", []):
            stats = item.get("statistics", {})
            videos.append({
                "id": item["id"],
                "title": item["snippet"]["title"],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "published": item["snippet"]["publishedAt"],
            })

        # Sort by views
        videos.sort(key=lambda x: x["views"], reverse=True)
        results["top_videos"]   = videos[:5]
        results["worst_videos"] = videos[-5:]
        results["avg_views"]    = sum(v["views"] for v in videos) // max(len(videos), 1)

        # Extract keywords from top performing titles
        top_titles = " ".join(v["title"].lower() for v in videos[:5])
        results["top_keywords"] = [w for w in top_titles.split() if len(w) > 3]

        # Analyze comments on top 3 videos
        for video in videos[:3]:
            try:
                comments_resp = yt_service.commentThreads().list(
                    videoId=video["id"],
                    part="snippet",
                    maxResults=20,
                    order="relevance"
                ).execute()
                for c in comments_resp.get("items", []):
                    text = c["snippet"]["topLevelComment"]["snippet"]["textDisplay"].lower()
                    results["comment_insights"].append(text)
            except Exception:
                pass  # Comments may be disabled

        log.info(f"✅ Channel analyzed: {len(videos)} videos, avg views: {results['avg_views']}")

    except Exception as e:
        log.error(f"Channel analysis error: {e}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — COMPETITOR ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
def analyze_competitors(yt_service):
    """Analyze competitor channels to find what's working for them."""
    log.info("🔍 Analyzing competitor channels...")
    competitor_data = []

    for channel_id in COMPETITOR_CHANNELS:
        try:
            search_resp = yt_service.search().list(
                channelId=channel_id.strip(),
                part="snippet,id",
                order="viewCount",
                maxResults=10,
                type="video"
            ).execute()

            for item in search_resp.get("items", []):
                competitor_data.append({
                    "channel": channel_id,
                    "title": item["snippet"]["title"].lower(),
                    "video_id": item["id"]["videoId"],
                })
        except Exception as e:
            log.warning(f"Competitor {channel_id} error: {e}")

    competitor_keywords = []
    for v in competitor_data:
        competitor_keywords.extend(v["title"].split())

    log.info(f"✅ Competitor data: {len(competitor_data)} videos analyzed")
    return competitor_data, competitor_keywords


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — SMART TOPIC PICKER
# ══════════════════════════════════════════════════════════════════════════════
TOPIC_POOL = [
    {"title": "The Clean Up Song",      "hebrew": "שיר הסדר",          "tags": ["clean","tidy","room","organize"]},
    {"title": "Colors All Around",       "hebrew": "צבעים בכל מקום",    "tags": ["red","blue","yellow","colors","colour"]},
    {"title": "Count With Me 1 to 10",   "hebrew": "ספור איתי",         "tags": ["numbers","count","math","one","two","three"]},
    {"title": "Good Morning Song",       "hebrew": "בוקר טוב",          "tags": ["morning","routine","wake","breakfast"]},
    {"title": "Vegetables Are Yummy",    "hebrew": "ירקות זה טעים",     "tags": ["vegetables","healthy","eating","food"]},
    {"title": "Head Shoulders Knees",    "hebrew": "ראש כתפיים ברכיים", "tags": ["body","parts","exercise","head","shoulders"]},
    {"title": "Old MacDonald Farm",      "hebrew": "חוות הדוד מקדונלד", "tags": ["farm","animals","cow","chicken","sheep","pig"]},
    {"title": "Brush Your Teeth Song",   "hebrew": "צחצוח שיניים",      "tags": ["teeth","hygiene","health","brush","morning"]},
    {"title": "Be Kind Share Today",     "hebrew": "שיתוף ונחמדות",     "tags": ["sharing","kind","friends","gentle","care"]},
    {"title": "ABC Alphabet Song",       "hebrew": "שיר האלפבית",       "tags": ["abc","alphabet","letters","learn","phonics"]},
    {"title": "Five Little Monkeys",     "hebrew": "חמישה קופים",       "tags": ["monkeys","counting","jumping","five","bed"]},
    {"title": "Twinkle Little Star",     "hebrew": "כוכב קטן",          "tags": ["star","night","sky","lullaby","sleep","twinkle"]},
    {"title": "Wheels on the Bus",       "hebrew": "גלגלי האוטובוס",    "tags": ["bus","wheels","transport","round","round"]},
    {"title": "Happy Sad Feelings",      "hebrew": "רגשות",             "tags": ["happy","sad","angry","feelings","emotions"]},
    {"title": "Rain Rain Go Away",       "hebrew": "גשם לך לך",         "tags": ["rain","weather","outside","sun","clouds"]},
    {"title": "Happy Birthday To You",   "hebrew": "יום הולדת שמח",     "tags": ["birthday","cake","celebrate","party","candles"]},
    {"title": "My Family Song",          "hebrew": "שיר המשפחה",        "tags": ["family","mom","dad","baby","sister","brother"]},
    {"title": "Baa Baa Black Sheep",     "hebrew": "כבשה שחורה",        "tags": ["sheep","wool","farm","black","white"]},
    {"title": "Bath Time Fun",           "hebrew": "כיף באמבטיה",       "tags": ["bath","bubbles","clean","water","splash"]},
    {"title": "Let Us Play Outside",     "hebrew": "לשחק בחוץ",         "tags": ["play","slide","swing","friends","outside","park"]},
    {"title": "Johny Johny Yes Papa",    "hebrew": "ג'וני ג'וני",        "tags": ["johny","papa","sugar","eating","no","yes"]},
    {"title": "If Youre Happy Clap",     "hebrew": "אם אתה שמח",        "tags": ["happy","clap","stomp","shout","hooray"]},
    {"title": "Incy Wincy Spider",       "hebrew": "עכביש קטן",         "tags": ["spider","rain","sun","web","climb","itsy"]},
    {"title": "Row Your Boat Song",      "hebrew": "חתור את הסירה",      "tags": ["boat","row","stream","dream","life","merrily"]},
    {"title": "The Dinosaur Song",       "hebrew": "שיר הדינוזאורים",   "tags": ["dinosaur","roar","big","stomp","dino","rex"]},
]

def pick_best_topic(trending_kw, my_channel_data, competitor_kw, already_uploaded):
    """Score each topic based on research + channel data and pick the best one."""
    log.info("🧠 Picking best topic...")

    already_titles = {t.lower() for t in already_uploaded}
    all_signals = trending_kw + my_channel_data.get("top_keywords", []) + competitor_kw

    scores = {}
    for topic in TOPIC_POOL:
        # Skip if already uploaded recently
        if topic["title"].lower() in already_titles:
            continue

        score = 0
        for tag in topic["tags"]:
            score += all_signals.count(tag) * 2  # weight by frequency

        # Bonus if it's in top_keywords of your own channel (proven to work)
        for kw in my_channel_data.get("top_keywords", []):
            if kw in topic["tags"]:
                score += 5

        # Bonus if trending online
        for kw in trending_kw:
            if kw in topic["tags"]:
                score += 3

        scores[topic["title"]] = score

    if not scores:
        log.warning("All topics already uploaded — resetting pool.")
        scores = {t["title"]: random.randint(1, 5) for t in TOPIC_POOL}

    best_title = max(scores, key=scores.get)
    best_topic = next(t for t in TOPIC_POOL if t["title"] == best_title)
    log.info(f"✅ Best topic: {best_topic['title']} (score={scores[best_title]})")
    return best_topic, scores


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — GENERATE VIDEO via Higgsfield
# ══════════════════════════════════════════════════════════════════════════════
def generate_video(topic):
    """Generate a 9:16 animated Short via Higgsfield and return the local file path."""
    log.info(f"🎬 Generating video for: {topic['title']}")

    # 5a. Generate character image
    image_prompt = (
        f"Cute cartoon baby character Kuki performing '{topic['title']}', "
        f"big round eyes, chubby cheeks, colorful outfit, bright smile, "
        f"2D flat animation style, vibrant background matching the song theme, "
        f"children's YouTube Short 9:16, warm and friendly, no text, "
        f"theme keywords: {', '.join(topic['tags'][:3])}"
    )
    img_resp = requests.post(f"{HIGGSFIELD_BASE}/v1/generate/image", headers=HF_HEADERS, json={
        "model": "nano_banana_2",
        "prompt": image_prompt,
        "aspect_ratio": "9:16",
        "count": 1,
    }, timeout=60)
    img_resp.raise_for_status()
    image_job_id = img_resp.json().get("id") or img_resp.json().get("job_id")
    log.info(f"Image job: {image_job_id}")

    image_url = _poll_job(image_job_id, "image")

    # 5b. Generate video from image
    video_prompt = (
        f"Animated children's Short: cute cartoon baby Kuki singing '{topic['title']}' "
        f"({topic['hebrew']}), colorful 2D animation, bouncy joyful movement, "
        f"bright cheerful colors, educational kids content, no text overlays, "
        f"theme: {', '.join(topic['tags'][:3])}"
    )
    vid_resp = requests.post(f"{HIGGSFIELD_BASE}/v1/generate/video", headers=HF_HEADERS, json={
        "model": "seedance_2_0",
        "prompt": video_prompt,
        "aspect_ratio": "9:16",
        "resolution": "1080p",
        "medias": [{"value": image_job_id, "role": "start_image"}],
    }, timeout=60)
    vid_resp.raise_for_status()
    video_job_id = vid_resp.json().get("id") or vid_resp.json().get("job_id")
    log.info(f"Video job: {video_job_id}")

    video_url = _poll_job(video_job_id, "video")

    # 5c. Download
    date_str   = datetime.now().strftime("%Y%m%d_%H%M")
    safe_title = topic["title"].replace(" ", "_").lower()
    filename   = f"{OUTPUT_DIR}/{date_str}_{safe_title}.mp4"
    dl = requests.get(video_url, stream=True, timeout=120)
    with open(filename, "wb") as f:
        for chunk in dl.iter_content(8192):
            f.write(chunk)

    log.info(f"✅ Video saved: {filename}")
    return filename


def _poll_job(job_id, job_type, max_wait=600):
    """Poll Higgsfield until job completes."""
    endpoint = f"{HIGGSFIELD_BASE}/v1/generate/{job_type}/status/{job_id}"
    start = time.time()
    while time.time() - start < max_wait:
        resp = requests.get(endpoint, headers=HF_HEADERS, timeout=15).json()
        status = resp.get("status", "")
        log.info(f"  [{job_type}] {job_id}: {status}")
        if status == "completed":
            return (resp.get("result_url") or resp.get("url")
                    or (resp.get("results") or [{}])[0].get("url"))
        if status == "failed":
            raise RuntimeError(f"Job failed: {resp}")
        time.sleep(15)
    raise TimeoutError(f"Job {job_id} timed out")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — UPLOAD TO YOUTUBE
# ══════════════════════════════════════════════════════════════════════════════
def upload_to_youtube(yt_service, filename, topic, scores):
    """Upload the video directly to YouTube as a Short."""
    log.info(f"⬆️  Uploading to YouTube...")

    title = f"{topic['title']} + More Kids Songs | Kuki Kids 🎵 #Shorts"
    description = (
        f"🎵 {topic['title']} ({topic['hebrew']}) — a fun educational song for kids!\n\n"
        f"Join Kuki on a musical learning adventure! Perfect for toddlers and preschoolers.\n\n"
        f"#KukiKids #KidsSongs #NurseryRhymes #Shorts #ChildrenSongs #ToddlerSongs "
        f"#{topic['tags'][0].capitalize()} #KidsYouTube #EducationalKids #BabySongs"
    )
    tags = ["kids songs", "nursery rhymes", "kuki kids", "shorts", "toddler songs",
            "educational kids", "children songs", "baby songs"] + topic["tags"]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs (best for kids content)
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": True,
        }
    }

    media = googleapiclient.http.MediaFileUpload(
        filename, chunksize=-1, resumable=True, mimetype="video/mp4"
    )
    request = yt_service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info(f"  Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    log.info(f"✅ Uploaded: {video_url}")
    return video_id, video_url


# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — EMAIL REPORT
# ══════════════════════════════════════════════════════════════════════════════
def send_report(topic, video_url, my_channel_data, scores, trending_kw):
    """Send a full daily report email."""
    log.info("📧 Sending email report...")

    top_5 = sorted(scores, key=scores.get, reverse=True)[:5]
    top_videos_str = "\n".join(
        f"  • {v['title']} — {v['views']:,} views"
        for v in my_channel_data.get("top_videos", [])
    )
    worst_videos_str = "\n".join(
        f"  • {v['title']} — {v['views']:,} views"
        for v in my_channel_data.get("worst_videos", [])
    )

    body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 KUKI KIDS BOT — Daily Report
{datetime.now().strftime('%A, %B %d %Y — %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ VIDEO UPLOADED AUTOMATICALLY
   Title:  {topic['title']} + More Kids Songs | Kuki Kids 🎵
   Link:   {video_url}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 YOUR CHANNEL STATS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Average views per video: {my_channel_data.get('avg_views', 0):,}

🏆 TOP PERFORMING VIDEOS:
{top_videos_str or '  No data yet'}

📉 LOWEST PERFORMING VIDEOS:
{worst_videos_str or '  No data yet'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 TODAY'S TOPIC SCORES (why we picked this)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{chr(10).join(f'  {i+1}. {t} — score {scores.get(t, 0)}' for i, t in enumerate(top_5))}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 TRENDING KEYWORDS ONLINE TODAY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{', '.join(trending_kw[:15])}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You don't need to do anything. The video is live. 🚀

— Kuki Kids Bot 🤖
"""

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg["Subject"] = f"✅ Kuki Kids — Video Live: {topic['title']} | {datetime.now().strftime('%b %d')}"
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())

    log.info(f"✅ Report sent to {EMAIL_RECIPIENT}")


# ══════════════════════════════════════════════════════════════════════════════
# YOUTUBE AUTH
# ══════════════════════════════════════════════════════════════════════════════
def _get_youtube_service():
    import base64
    creds = None
    token_b64 = os.getenv("YOUTUBE_TOKEN_B64")
    log.info(f"Token present: {bool(token_b64)}, length: {len(token_b64) if token_b64 else 0}")
    if token_b64:
        try:
            token_b64_clean = "".join(token_b64.split())
            token_json = base64.b64decode(token_b64_clean).decode()
            token_data = json.loads(token_json)
            log.info(f"Token keys: {list(token_data.keys())}")
            creds = Credentials.from_authorized_user_info(token_data, YOUTUBE_SCOPES)
            log.info(f"Creds valid: {creds.valid}, expired: {creds.expired}")
        except Exception as e:
            log.error(f"Token error: {e}")
            creds = None
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, YOUTUBE_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        log.info("Refreshing expired token...")
        creds.refresh(Request())
    if not creds or not creds.valid:
        raise RuntimeError("No valid YouTube credentials found.")
    return build("youtube", "v3", credentials=creds)


def _get_youtube_service_readonly():
    """Read-only YouTube service for research (no auth needed with API key)."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if api_key:
        return build("youtube", "v3", developerKey=api_key)
    return _get_youtube_service()


# ══════════════════════════════════════════════════════════════════════════════
# UPLOAD HISTORY (to avoid repeating topics)
# ══════════════════════════════════════════════════════════════════════════════
HISTORY_FILE = "upload_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def save_history(history, topic, video_url):
    history.append({
        "date": datetime.now().isoformat(),
        "title": topic["title"],
        "url": video_url,
    })
    # Keep last 60 days
    cutoff = datetime.now() - timedelta(days=60)
    history = [h for h in history if datetime.fromisoformat(h["date"]) > cutoff]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    return history


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def run():
    log.info("\n" + "="*55)
    log.info(f"  KUKI KIDS BOT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("="*55)

    # Auth
    yt = _get_youtube_service()

    # Load history
    history        = load_history()
    already_posted = [h["title"] for h in history]

    # 1. Research
    trending_kw    = research_trending_topics()

    # 2. Analyze my channel
    my_data        = analyze_my_channel(yt)

    # 3. Analyze competitors
    _, comp_kw     = analyze_competitors(yt)

    # 4. Pick topic
    topic, scores  = pick_best_topic(trending_kw, my_data, comp_kw, already_posted)

    # 5. Generate video
    filename       = generate_video(topic)

    # 6. Upload
    video_id, video_url = upload_to_youtube(yt, filename, topic, scores)

    # 7. Save history
    history        = save_history(history, topic, video_url)

    # 8. Email report
    send_report(topic, video_url, my_data, scores, trending_kw)

    log.info(f"\n🎉 ALL DONE — Video live at: {video_url}\n")


if __name__ == "__main__":
    run()
