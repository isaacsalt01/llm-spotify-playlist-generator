from fastapi import FastAPI, Query, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError, ValidationException, FastAPIError
from pydantic import BaseModel
from main import generate_playlist
import json
from typing import Annotated, Union


# New imports for Spotify OAuth (Authorization Code flow)
import os
import base64
import secrets
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv

import fastapi.exceptions

print(fastapi.exceptions)

load_dotenv()

app = FastAPI(
    title="LLM Spotify Playlist Generator",
    description="Generate Spotify playlists using LLMs",
)

frontend_url = os.getenv("FRONTEND_URL")
print(frontend_url)

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
    user_prompt: str
    user_track_list: str
    access_token: str = None


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

    except Exception as e:
        print(f"Error generating playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scrape", response_class=HTMLResponse)
def scrape_previews(url: Annotated[str, Header()]):
    """Scrape previews URLs"""
    print(url)
    resp = requests.get(url)
    return resp.text


# =========================
# Spotify OAuth (Auth Code)
# =========================

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://localhost:8000/auth/callback"
)

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

SPOTIFY_SCOPES = "user-top-read playlist-modify-private playlist-modify-public"


def _basic_auth_header(client_id: str, client_secret: str) -> str:
    creds = f"{client_id}:{client_secret}".encode("utf-8")
    return base64.b64encode(creds).decode("utf-8")


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
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "state": state,
        # "show_dialog": "true",  # uncomment to force re-consent during development
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
def auth_callback(code: str, state: str | None = None):
    """
    Spotify redirects here with ?code= and optional ?state=. Exchange code for tokens.
    Redirects to frontend with tokens in URL
    """
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET or not SPOTIFY_REDIRECT_URI:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Spotify OAuth is not configured. Check environment variables."
            },
        )

    headers = {
        "Authorization": f"Basic {_basic_auth_header(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }
    resp = requests.post(SPOTIFY_TOKEN_URL, data=data, headers=headers, timeout=15)
    print(resp.status_code, resp.text)

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
        "Authorization": f"Basic {_basic_auth_header(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)}",
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
