import axios from "axios";

/**
 * Client for FastAPI-backed Spotify OAuth (Authorization Code flow).
 * Backend endpoints implemented in Python FastAPI:
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
console.log(API_BASE_URL);

export type AuthLoginResponse = {
  auth_url: string;
  state: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string;
  scope?: string;
};

/**
 * Directly redirect the browser to the backend which will 302 to Spotify.
 */
export function redirectToLogin(): void {
  window.location.href = `${API_BASE_URL}/auth/login?redirect=true`;
}

/**
 * Refresh access token using a refresh token via backend.
 */
export async function refreshAccessToken(
  refresh_token: string
): Promise<TokenResponse> {
  const res = await axios.post<TokenResponse>(`${API_BASE_URL}/auth/refresh`, {
    refresh_token,
  });
  return res.data;
}
