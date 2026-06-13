# Kuki Kids Bot — Railway Deployment Guide
## Runs 24/7 in the cloud. Your PC can be off. You do nothing.

---

## Total setup time: ~20 minutes (one time only)

---

## PART 1 — Prepare files on your PC (5 min)

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Get your client_secrets.json from Google
1. Go to https://console.cloud.google.com
2. Create a project (or use existing)
3. **APIs & Services → Enable APIs → YouTube Data API v3** → Enable
4. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop App** → Create
6. Click **Download JSON** → rename file to `client_secrets.json`
7. Put `client_secrets.json` in this folder

### 3. Run auth setup (opens browser once)
```bash
python auth_setup.py
```
- A browser opens → log into your Google/YouTube account → click Allow
- The script prints a long `YOUTUBE_TOKEN_B64` value — **copy it**

---

## PART 2 — Deploy to Railway (10 min)

### 4. Create Railway account
Go to https://railway.app → Sign up with GitHub (free)

### 5. Create new project
- Click **New Project → Deploy from GitHub repo**
- Upload this folder as a GitHub repo (or use Railway CLI)

**Easiest way — Railway CLI:**
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

### 6. Add environment variables
In Railway dashboard → your project → **Variables** → add ALL of these:

| Variable | Value | Where to get it |
|---|---|---|
| `HIGGSFIELD_API_KEY` | your key | app.higgsfield.ai/settings/api |
| `YOUTUBE_API_KEY` | your key | Google Cloud Console → API Key |
| `YOUTUBE_TOKEN_B64` | the long string from Step 3 | auth_setup.py output |
| `YOUR_CHANNEL_ID` | your channel ID | youtube.com/channel/XXXXX |
| `COMPETITOR_CHANNELS` | `UCMEVZK5J38upc4XiRO3sqWQ` | NuNu TV (default) |
| `EMAIL_SENDER` | your Gmail | - |
| `EMAIL_PASSWORD` | Gmail App Password | myaccount.google.com → Security → App Passwords |
| `EMAIL_RECIPIENT` | where to receive reports | - |
| `SERPAPI_KEY` | optional | serpapi.com (free tier) |
| `OUTPUT_DIR` | `/tmp/videos` | exactly as written |

### 7. Deploy
Railway auto-deploys when you push. Or click **Deploy** in the dashboard.

---

## PART 3 — Done ✅

From now on:
- Bot runs every day at 08:00 UTC automatically
- Your PC can be off
- You receive an email daily with what was uploaded
- Video is already live on YouTube by the time you read the email

---

## Timezone note
08:00 UTC = 10:00 Israel time (summer) / 11:00 Israel time (winter).
To change the time, edit `RUN_AT` in `main.py` and redeploy.

---

## Cost
Railway free tier: **$5 free credits/month** — more than enough for this bot.
If you exceed free tier: ~$1-2/month.

---

## Troubleshooting
- **Bot not running?** Check Railway logs: dashboard → your project → Deployments → View Logs
- **YouTube auth expired?** Re-run `auth_setup.py` locally and update `YOUTUBE_TOKEN_B64` in Railway Variables
- **Video generation failing?** Check your Higgsfield credits at app.higgsfield.ai
