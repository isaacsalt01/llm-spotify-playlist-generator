# LLM Spotify Playlist Generator

A web application that generates personalized Spotify playlists using Large Language Models (LLMs) based on natural language descriptions provided by users.

<a href="https://frontend-production-b573.up.railway.app/" target="_blank">
  <img src="https://img.shields.io/badge/Live%20Demo-Railway-red?style=flat-square&logo=netlify&logoSize=auto" alt="Live Demo Badge"  class="border-none">
</a>

## Overview

The application allows users to describe their desired playlist in plain English (e.g., "upbeat workout music" or "chill vibes for studying"). It leverages OpenAI's GPT models to interpret the input, generate a playlist description, and suggest relevant tracks by querying the Spotify Web API. The results are presented through a modern React-based web interface with Spotify OAuth integration.

### How It Works

1. **User Authentication**: Users log in via Spotify OAuth to access their Spotify account.
2. **Input Description**: Enter a natural language description of the desired playlist.
3. **Track List UI**: Users top tracks are displayed and user can add seed tracks to the playlist
4. **LLM Processing**: The input is processed by an LLM to generate a detailed playlist theme and track suggestions.
5. **Playlist Creation**: The generated playlist is displayed with options to save to Spotify.

## Architecture

### Frontend

- **Framework**: React 19 with TypeScript
- **Styling**: Bootstrap 5.3, React Bootstrap, SASS
- **State Management**: Zustand
- **Routing**: React Router DOM
- **API Communication**: Axios for backend calls
- **Components**: Modular components in `frontend/src/components`
- **API Helpers**: Helper functions in `frontend/src/api`

### Backend

- **Framework**: Python FastAPI with Pydantic for request validation
- **Endpoints**:
  - `/generate_playlist`: Main endpoint for playlist generation (calls `generate_playlist` in `src/main.py`)
  - `/scrape`: Middleware for scraping Spotify preview URLs
  - `/auth/*`: OAuth endpoints for Spotify authentication
- **LLM Integration**: `src/llm_client.py` Handles OpenAI API interactions
- **Spotify Client**: `src/spotify_client.py` Manages Spotify API calls

## Setup

### Prerequisites

- Python 3.8+
- Node.js 16+
- Docker and Docker Compose (optional, for containerized deployment)
- Spotify Developer Account (for app credentials)
- OpenAI API Key

### Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/your-username/llm-spotify-playlist-generator.git
   cd llm-spotify-playlist-generator
   ```

2. **Backend Setup**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Frontend Setup**:

   ```bash
   cd frontend
   npm install
   cd ..
   ```

4. **Environment Variables**:
   Create a `.env` file in the root directory with:
   ```
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   OPENAI_API_KEY=your_openai_api_key
   FRONTEND_URL=http://localhost:5173
   ```
   Create a `.env` in the frontend directory with:
   ```
   VITE_API_URL=http://localhost:8000
   ```

### Running the Application

#### Using Docker

You will need to add references to the .env files in your docker files.

```bash
docker-compose up --build
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000

#### Manual Setup

1. **Start Backend**:

   ```bash
   python src/app.py
   ```

   Backend runs on http://localhost:8000

2. **Start Frontend** (in a new terminal):
   ```bash
   cd frontend
   npm run dev
   ```
   Frontend runs on http://localhost:5173

## Usage

1. Open the frontend at http://localhost:5173
2. Click "Login with Spotify" to authenticate
3. Enter a playlist description (e.g., "energetic pop songs for a road trip")
4. Click "Generate Playlist"
5. Review the suggested tracks and playlist description
6. Click "Open in spotify" to see your playlist in your Spotify account

### API Usage

You can also interact with the backend API directly:

```bash
curl -X POST "http://localhost:8000/generate_playlist" \
     -H "Content-Type: application/json" \
     -d '{"user_input": "chill study music"}'
```
