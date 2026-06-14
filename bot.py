"""
Kuki Kids Bot v2 — Fully Automatic
====================================
1. Researches trending children's content online
2. Analyzes YOUR channel (views, comments, best/worst performers)
3. Compares against competitor channels
4. Picks the best topic automatically
5. Generates video via Higgsfield
6. Uploads directly to YouTube
7. Emails you a report
"""

import os, time, json, random, smtplib, requests, logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
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
COMPETITOR_CHANNELS = os.getenv("COMPETITOR_CHANNELS", "UCMEVZK5J38upc4XiRO3sqWQ").split(",")
EMAIL_SENDER        = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD      = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENT     = os.getenv("EMAIL_RECIPIENT")
OUTPUT_DIR          = os.getenv("OUTPUT_DIR", "/tmp/videos")
TOKEN_FILE          = "youtube_token.json"
SERPAPI_KEY         = os.getenv("SERPAPI_KEY", "")

os.makedirs(OUTPUT_DIR, exist_ok=True)

HIGGSFIELD_BASE = "https://api.higgsfield.ai"
HF_HEADERS = {
    "Authorization": f"Bearer {HIGGSFIELD_API_KEY}",
    "Content-Type": "application/json"
}

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# ── Topic Pool ─────────────────────────────────────────────────────────────────
TOPIC_POOL = [
    {"title": "The Clean Up Song",      "hebrew": "שיר הסדר",          "tags": ["clean","tidy","room","organize"]},
    {"title": "Colors All Around",       "hebrew": "צבעים בכל מקום",    "tags": ["red","blue","yellow","colors"]},
    {"title": "Count With Me 1 to 10",   "hebrew": "ספור איתי",         "tags": ["numbers","count","math","one","two"]},
    {"title": "Good Morning Song",       "hebrew": "בוקר טוב",          "tags": ["morning","routine","wake","breakfast"]},
    {"title": "Vegetables Are Yummy",    "hebrew": "ירקות זה טעים",     "tags": ["vegetables","healthy","eating","food"]},
    {"title": "Head Shoulders Knees",    "hebrew": "ראש כתפיים ברכיים", "tags": ["body","parts","exercise","head"]},
    {"title": "Old MacDonald Farm",      "hebrew": "חוות הדוד מקדונלד", "tags": ["farm","animals","cow","chicken","sheep"]},
    {"title": "Brush Your Teeth Song",   "hebrew": "צחצוח שיניים",      "tags": ["teeth","hygiene","health","brush"]},
    {"title": "Be Kind Share Today",     "hebrew": "שיתוף ונחמדות",     "tags": ["sharing","kind","friends","gentle"]},
    {"title": "ABC Alphabet Song",       "hebrew": "שיר האלפבית",       "tags": ["abc","alphabet","letters","learn"]},
    {"title": "Five Little Monkeys",     "hebrew": "חמישה קופים",       "tags": ["monkeys","counting","jumping","five"]},
    {"title": "Twinkle Little Star",     "hebrew": "כוכב קטן",          "tags": ["star","night","sky","lullaby","sleep"]},
    {"title": "Wheels on the Bus",       "hebrew": "גלגלי האוטובוס",    "tags": ["bus","wheels","transport","round"]},
    {"title": "Happy Sad Feelings",      "hebrew": "רגשות",             "tags": ["happy","sad","angry","feelings"]},
    {"title": "Rain Rain Go Away",       "hebrew": "גשם לך לך",         "tags": ["rain","weather","outside","sun"]},
    {"title": "Happy Birthday To You",   "hebrew": "יום הולדת שמח",     "tags": ["birthday","cake","celebrate","party"]},
    {"title": "My Family Song",          "hebrew": "שיר המשפחה",        "tags": ["family","mom","dad","baby","sister"]},
    {"title": "Baa Baa Black Sheep",     "hebrew": "כבשה שחורה",        "tags": ["sheep","wool","farm","black"]},
    {"title": "Bath Time Fun",           "hebrew": "כיף באמבטיה",       "tags": ["bath","bubbles","clean","water"]},
    {"title": "Let Us Play Outside",     "hebrew": "לשחק בחוץ",         "tags": ["play","slide","swing","friends","park"]},
    {"title": "Johny Johny Yes Papa",    "hebrew": "ג'וני ג'וני",        "tags": ["johny","papa","sugar","eating"]},
    {"title": "If Youre Happy Clap",     "hebrew": "אם אתה שמח",        "tags": ["happy","clap","stomp","shout"]},
    {"title": "Incy Wincy Spider",       "hebrew": "עכביש קטן",         "tags": ["spider","rain","sun","web","climb"]},
    {"title": "Row Your Boat Song",      "hebrew": "חתור את הסירה",      "tags": ["boat","row","stream","dream","life"]},
    {"title": "The Dinosaur Song",       "hebrew": "שיר הדינוזאורים",   "tags": ["dinosaur","roar","big","stomp","dino"]},
]

# ── Step 1: Web Research ───────────────────────────────────────────────────────
def research_trending_topics():
    log.info("🌐 Researching trending children's content...")
    trending_keywords = []
    try:
        yt = _get_youtube_service_readonly()
        for term in ["kids songs 2025", "nursery rhymes shorts", "toddler educational songs"]:
            resp = yt.search().list(
                q=term, part="snippet", type="video",
                videoDuration="short", order="viewCount",
                maxResults=10, relevanceLanguage="en"
            ).execute()
            for item in resp.get("items", []):
                title = item["snippet"]["title"].lower()
                trending_keywords.extend(title.split())
    except Exception as e:
        log.warning(f"Trending research error: {e}")

    stop_words = {"and","the","a","to","in","of","for","with","more","nursery","rhymes","kids","song","songs","video","youtube"}
    freq = {}
    for kw in trending_keywords:
        kw = kw.strip(".,!?|+&")
        if len(kw) > 3 and kw not in stop_words:
            freq[kw] = freq.get(kw, 0) + 1

    top = sorted(freq, key=freq.get, reverse=True)[:20]
    log.info(f"🔥 Trending: {top[:10]}")
    return top

# ── Step 2: Analyze My Channel ─────────────────────────────────────────────────
def analyze_my_channel(yt):
    log.info("📊 Analyzing your channel...")
    results = {"top_videos": [], "worst_videos": [], "top_keywords": [], "avg_views": 0}
    if not YOUR_CHANNEL_ID:
        return results
    try:
        search_resp = yt.search().list(
            channelId=YOUR_CHANNEL_ID, part="snippet,id",
            order="date", maxResults=50, type="video"
        ).execute()
        video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
        if not video_ids:
            return results
        stats_resp = yt.videos().list(id=",".join(video_ids), part="snippet,statistics").execute()
        videos = []
        for item in stats_resp.get("items", []):
            s = item.get("statistics", {})
            videos.append({
                "id": item["id"],
                "title": item["snippet"]["title"],
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
            })
        videos.sort(key=lambda x: x["views"], reverse=True)
        results["top_videos"]   = videos[:5]
        results["worst_videos"] = videos[-5:]
        results["avg_views"]    = sum(v["views"] for v in videos) // max(len(videos), 1)
        results["top_keywords"] = " ".join(v["title"].lower() for v in videos[:5]).split()
        log.info(f"✅ Channel: {len(videos)} videos, avg views: {results['avg_views']}")
    except Exception as e:
        log.error(f"Channel analysis error: {e}")
    return results

# ── Step 3: Analyze Competitors ────────────────────────────────────────────────
def analyze_competitors(yt):
    log.info("🔍 Analyzing competitors...")
    keywords = []
    for ch in COMPETITOR_CHANNELS:
        try:
            resp = yt.search().list(
                channelId=ch.strip(), part="snippet,id",
                order="viewCount", maxResults=10, type="video"
            ).execute()
            for item in resp.get("items", []):
                keywords.extend(item["snippet"]["title"].lower().split())
        except Exception as e:
            log.warning(f"Competitor {ch} error: {e}")
    log.info(f"✅ Competitor keywords: {len(keywords)}")
    return keywords

# ── Step 4: Pick Best Topic ────────────────────────────────────────────────────
def pick_best_topic(trending_kw, my_data, comp_kw, already_posted):
    log.info("🧠 Picking best topic...")
    all_signals = trending_kw + my_data.get("top_keywords", []) + comp_kw
    scores = {}
    for topic in TOPIC_POOL:
        if topic["title"] in already_posted:
            continue
        score = sum(all_signals.count(tag) for tag in topic["tags"])
        scores[topic["title"]] = score

    if not scores:
        scores = {t["title"]: random.randint(1, 5) for t in TOPIC_POOL}

    best = max(scores, key=scores.get)
    topic = next(t for t in TOPIC_POOL if t["title"] == best)
    log.info(f"✅ Topic: {topic['title']} (score={scores[best]})")
    return topic, scores

# ── Step 5: Generate Video via Higgsfield ──────────────────────────────────────
def generate_video(topic):
    log.info(f"🎬 Generating: {topic['title']}")

    # Generate image
    img_payload = {
        "model": "nano_banana_2",
        "prompt": (
            f"Cute cartoon baby character Kuki performing '{topic['title']}', "
            f"big round eyes, chubby cheeks, colorful outfit, bright smile, "
            f"2D flat animation style, vibrant background, children's YouTube, "
            f"warm and friendly, no text, theme: {', '.join(topic['tags'][:3])}"
        ),
        "aspect_ratio": "9:16",
        "count": 1,
    }
    img_resp = requests.post(
        f"{HIGGSFIELD_BASE}/v1/image/generate",
        headers=HF_HEADERS, json=img_payload, timeout=60
    )
    log.info(f"Image API response: {img_resp.status_code} {img_resp.text[:200]}")
    img_resp.raise_for_status()
    image_job_id = img_resp.json().get("id") or img_resp.json().get("job_id")
    log.info(f"Image job: {image_job_id}")
    _poll_job(image_job_id, "image")

    # Generate video
    vid_payload = {
        "model": "seedance_2_0",
        "prompt": (
            f"Animated children's Short: cartoon baby Kuki singing '{topic['title']}' "
            f"({topic['hebrew']}), colorful 2D animation, bouncy movement, bright colors, "
            f"educational kids content, no text"
        ),
        "aspect_ratio": "9:16",
        "resolution": "720p",
        "medias": [{"value": image_job_id, "role": "start_image"}],
    }
    vid_resp = requests.post(
        f"{HIGGSFIELD_BASE}/v1/video/generate",
        headers=HF_HEADERS, json=vid_payload, timeout=60
    )
    log.info(f"Video API response: {vid_resp.status_code} {vid_resp.text[:200]}")
    vid_resp.raise_for_status()
    video_job_id = vid_resp.json().get("id") or vid_resp.json().get("job_id")
    log.info(f"Video job: {video_job_id}")
    video_url = _poll_job(video_job_id, "video")

    # Download
    filename = f"{OUTPUT_DIR}/{datetime.now().strftime('%Y%m%d_%H%M')}_{topic['title'].replace(' ','_').lower()}.mp4"
    r = requests.get(video_url, stream=True, timeout=120)
    with open(filename, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    log.info(f"✅ Saved: {filename}")
    return filename

def _poll_job(job_id, job_type, max_wait=600):
    endpoint = f"{HIGGSFIELD_BASE}/v1/{job_type}/status/{job_id}"
    start = time.time()
    while time.time() - start < max_wait:
        r = requests.get(endpoint, headers=HF_HEADERS, timeout=15).json()
        status = r.get("status", "")
        log.info(f"  [{job_type}] {status}")
        if status == "completed":
            return (r.get("result_url") or r.get("url") or
                    (r.get("results") or [{}])[0].get("url"))
        if status == "failed":
            raise RuntimeError(f"Job failed: {r}")
        time.sleep(15)
    raise TimeoutError(f"Job timed out after {max_wait}s")

# ── Step 6: Upload to YouTube ──────────────────────────────────────────────────
def upload_to_youtube(yt, filename, topic, scores):
    log.info("⬆️ Uploading to YouTube...")
    title = f"{topic['title']} + More Kids Songs | Kuki Kids 🎵 #Shorts"
    description = (
        f"🎵 {topic['title']} ({topic['hebrew']}) — fun educational song for kids!\n\n"
        f"#KukiKids #KidsSongs #NurseryRhymes #Shorts #ChildrenSongs #ToddlerSongs"
    )
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["kids songs","nursery rhymes","kuki kids","shorts"] + topic["tags"],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": True,
        }
    }
    media = googleapiclient.http.MediaFileUpload(filename, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info(f"  Upload: {int(status.progress()*100)}%")
    video_id = response["id"]
    url = f"https://www.youtube.com/shorts/{video_id}"
    log.info(f"✅ Live: {url}")
    return video_id, url

# ── Step 7: Email Report ───────────────────────────────────────────────────────
def send_report(topic, video_url, my_data, scores, trending_kw):
    log.info("📧 Sending report...")
    top_5 = sorted(scores, key=scores.get, reverse=True)[:5]
    top_str = "\n".join(f"  {i+1}. {t} — score {scores[t]}" for i,t in enumerate(top_5))
    top_vids = "\n".join(f"  • {v['title']} — {v['views']:,} views" for v in my_data.get("top_videos",[]))
    body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 KUKI KIDS BOT — Daily Report
{datetime.now().strftime('%A, %B %d %Y — %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ VIDEO UPLOADED
   Title: {topic['title']} | Kuki Kids
   Link:  {video_url}

📊 YOUR CHANNEL
   Avg views: {my_data.get('avg_views',0):,}
   
🏆 TOP VIDEOS:
{top_vids or '  No data yet'}

🔥 TOPIC SCORES TODAY:
{top_str}

🌐 TRENDING: {', '.join(trending_kw[:10])}

— Kuki Kids Bot 🤖
"""
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT
    msg["Subject"] = f"✅ Kuki Kids — Video Live: {topic['title']} | {datetime.now().strftime('%b %d')}"
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
    log.info(f"✅ Report sent to {EMAIL_RECIPIENT}")

# ── YouTube Auth ───────────────────────────────────────────────────────────────
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
        log.info("Refreshing token...")
        creds.refresh(Request())
    if not creds or not creds.valid:
        raise RuntimeError("No valid YouTube credentials found.")
    return build("youtube", "v3", credentials=creds)

def _get_youtube_service_readonly():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if api_key:
        return build("youtube", "v3", developerKey=api_key)
    return _get_youtube_service()

# ── History ────────────────────────────────────────────────────────────────────
HISTORY_FILE = "/tmp/upload_history.json"

def load_history():
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except:
        return []

def save_history(history, topic, url):
    history.append({"date": datetime.now().isoformat(), "title": topic["title"], "url": url})
    cutoff = datetime.now() - timedelta(days=60)
    history = [h for h in history if datetime.fromisoformat(h["date"]) > cutoff]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    return history

# ── Main ───────────────────────────────────────────────────────────────────────
def run():
    log.info("\n" + "="*55)
    log.info(f"  KUKI KIDS BOT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("="*55)

    yt            = _get_youtube_service()
    history       = load_history()
    already       = [h["title"] for h in history]
    trending_kw   = research_trending_topics()
    my_data       = analyze_my_channel(yt)
    comp_kw       = analyze_competitors(yt)
    topic, scores = pick_best_topic(trending_kw, my_data, comp_kw, already)
    filename      = generate_video(topic)
    _, video_url  = upload_to_youtube(yt, filename, topic, scores)
    history       = save_history(history, topic, video_url)
    send_report(topic, video_url, my_data, scores, trending_kw)

    log.info(f"\n🎉 DONE — {video_url}\n")

if __name__ == "__main__":
    run()
