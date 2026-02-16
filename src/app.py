from fastapi import FastAPI, Query, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from main import generate_playlist
import json
import logging
from typing import Annotated
from urllib.parse import urlparse

# New imports for Spotify OAuth (Authorization Code flow)
import os
import base64
import secrets
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory store for OAuth state tokens (use Redis in production)
# State tokens expire after 10 minutes
oauth_state_store: dict[str, float] = {}
STATE_EXPIRY_SECONDS = 600  # 10 minutes

# Allowed hosts for the scrape endpoint (SSRF protection)
ALLOWED_SCRAPE_HOSTS = ["open.spotify.com", "i.scdn.co"]

app = FastAPI(
    title="LLM Spotify Playlist Generator",
    description="Generate Spotify playlists using LLMs",
)

# Environment variable validation
REQUIRED_ENV_VARS = [
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "OPENAI_API_KEY",
]

missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    logger.warning(f"Missing required environment variables: {', '.join(missing_vars)}")

frontend_url = os.getenv("FRONTEND_URL")
logger.info(f"Frontend URL configured: {frontend_url}")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # nginx or dockerized frontend
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",  # Vite dev server
        frontend_url,  # Railway frontend
        f"{frontend_url}/*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")  # Legacy


class PlaylistRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=1000)
    user_track_list: str
    access_token: str | None = None


@app.post("/generate_playlist")
def create_playlist(request: PlaylistRequest):
    """Generate a Spotify playlist using a prompt and a list of tracks."""
    try:
        trackList = json.loads(request.user_track_list)
        description, tracks, playlist_id = generate_playlist(
            request.user_prompt, trackList, request.access_token
        )

        response = {"description": description, "tracks": tracks}

        if playlist_id:
            response["playlist_id"] = playlist_id

        return response

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in user_track_list: {e}")
        raise HTTPException(status_code=400, detail="Invalid track list format")
    except Exception as e:
        logger.error(f"Error generating playlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate playlist")


def is_allowed_url(url: str) -> bool:
    """Validate URL against allowlist"""
    try:
        parsed = urlparse(url)
        return parsed.hostname in ALLOWED_SCRAPE_HOSTS and parsed.scheme in [
            "http",
            "https",
        ]
    except Exception:
        return False


@app.get("/scrape", response_class=HTMLResponse)
def scrape_previews(url: Annotated[str, Header()]):
    """Scrape preview URLs from allowed Spotify domains only."""
    if not is_allowed_url(url):
        logger.warning(f"Blocked scrape attempt for disallowed URL: {url}")
        raise HTTPException(
            status_code=400, detail="URL not allowed. Only Spotify URLs are permitted."
        )

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        logger.error(f"Error scraping URL {url}: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch URL")


# Spotify OAuth (Auth Code)

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://localhost:8000/auth/callback"
)

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

SPOTIFY_SCOPES = "user-top-read playlist-modify-private playlist-modify-public"


def basic_auth_header(client_id: str, client_secret: str) -> str:
    creds = f"{client_id}:{client_secret}".encode("utf-8")
    return base64.b64encode(creds).decode("utf-8")


def cleanup_expired_states():
    """Remove expired OAuth state tokens."""
    import time

    current_time = time.time()
    expired = [
        s
        for s, t in oauth_state_store.items()
        if current_time - t > STATE_EXPIRY_SECONDS
    ]
    for s in expired:
        del oauth_state_store[s]


def store_state(state: str):
    """Store OAuth state token with timestamp."""
    import time

    cleanup_expired_states()
    oauth_state_store[state] = time.time()


def validate_and_consume_state(state: str | None) -> bool:
    """Validate OAuth state token and remove it (single use)."""
    import time

    if not state or state not in oauth_state_store:
        return False

    timestamp = oauth_state_store.pop(state)
    return (time.time() - timestamp) <= STATE_EXPIRY_SECONDS


@app.get("/auth/login")
def auth_login(
    redirect: bool = Query(
        default=False, description="If true, respond with a 302 redirect to Spotify"
    )
):
    """
    Generate Spotify authorization URL (Authorization Code flow).
    - If redirect=false: returns JSON { auth_url, state } so the frontend can window.location to it
    - If redirect=true: responds with 302 Redirect to Spotify auth page
    """
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_REDIRECT_URI:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Spotify OAuth is not configured. Check environment variables."
            },
        )

    state = secrets.token_urlsafe(16)
    store_state(state)  # Store state for validation on callback

    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "state": state,
    }
    auth_url = f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"

    if redirect:
        return RedirectResponse(url=auth_url, status_code=302)
    return {"auth_url": auth_url, "state": state}


class AuthCallbackResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    scope: str | None = None


@app.get("/auth/callback")
def auth_callback(code: str, state: str | None = None, error: str | None = None):
    """
    Spotify redirects here with ?code= and ?state=. Exchange code for tokens.
    Redirects to frontend with tokens in URL.
    """
    frontend_error_url = (
        f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/auth/error"
    )

    # Handle OAuth errors from Spotify
    if error:
        logger.warning(f"OAuth error from Spotify: {error}")
        return RedirectResponse(
            url=f"{frontend_error_url}?error={error}", status_code=302
        )

    # Validate state token
    if not validate_and_consume_state(state):
        logger.warning(f"Invalid or expired OAuth state token")
        return RedirectResponse(
            url=f"{frontend_error_url}?error=invalid_state", status_code=302
        )

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET or not SPOTIFY_REDIRECT_URI:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Spotify OAuth is not configured. Check environment variables."
            },
        )

    headers = {
        "Authorization": f"Basic {basic_auth_header(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }
    resp = requests.post(SPOTIFY_TOKEN_URL, data=data, headers=headers, timeout=15)
    logger.info(f"Token exchange response status: {resp.status_code}")

    if resp.status_code != 200:
        # Redirect to frontend with error
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/auth/error?error=oauth_failed", status_code=302
        )

    token_json = resp.json()

    # Redirect to frontend with tokens in URL fragment
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    params = {
        "access_token": token_json["access_token"],
        "token_type": token_json["token_type"],
        "expires_in": str(token_json["expires_in"]),
        "refresh_token": token_json.get("refresh_token", ""),
        "scope": token_json.get("scope", ""),
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items() if v)
    return RedirectResponse(url=f"{frontend_url}/#{query_string}", status_code=302)


class RefreshRequest(BaseModel):
    refresh_token: str


@app.post("/auth/refresh", response_model=AuthCallbackResponse)
def auth_refresh(request: RefreshRequest):
    """
    Refresh access token using refresh_token.
    Returns new access_token (and possibly a new refresh_token).
    """
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Spotify OAuth is not configured. Check environment variables."
            },
        )

    headers = {
        "Authorization": f"Basic {basic_auth_header(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": request.refresh_token,
    }
    resp = requests.post(SPOTIFY_TOKEN_URL, data=data, headers=headers, timeout=15)
    if resp.status_code != 200:
        return JSONResponse(status_code=resp.status_code, content={"detail": resp.text})
    return resp.json()


@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("static/index.html") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
