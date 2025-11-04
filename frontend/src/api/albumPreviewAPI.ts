import * as cheerio from "cheerio";
import SpotifyWebApi from "spotify-web-api-node";
import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function getSpotifyLinks(url: string): Promise<string[]> {
  /* 
      NOT MY CODE
      FROM REPO - https://github.com/AliAkhtari78/SpotifyScraper  
    */
  const scraper = `${API_BASE_URL}/scrape` || "http://localhost:8000/scrape";
  try {
    const response = await axios.get(scraper, {
      headers: {
        url,
      },
    });
    const html = response.data;
    const $ = cheerio.load(html);
    const scdnLinks = new Set();

    $("*").each((_i, element) => {
      if ("attribs" in element) {
        const attrs = element.attribs;
        Object.values(attrs).forEach((value) => {
          if (typeof value === "string" && value.includes("p.scdn.co")) {
            scdnLinks.add(value);
          }
        });
      }
    });

    return Array.from(scdnLinks) as string[];
  } catch (error) {
    throw new Error(
      `Failed to fetch preview URLs: ${(error as Error).message}`
    );
  }
}

export async function searchAndGetLinks(
  songName: string,
  limit: number = 5,
  accessToken: string
) {
  /* 
	NOT MY CODE
	FROM REPO - https://github.com/AliAkhtari78/SpotifyScraper  
*/
  try {
    if (!songName) {
      throw new Error("Song name is required");
    }

    const spotifyApi = new SpotifyWebApi();
    spotifyApi.setAccessToken(accessToken!);

    const searchResults = await spotifyApi.searchTracks(songName);

    if (
      !searchResults.body.tracks ||
      searchResults.body.tracks.items.length === 0
    ) {
      return {
        success: false,
        error: "No songs found",
        results: [],
      };
    }

    const tracks = searchResults.body.tracks.items.slice(0, limit);
    const results = await Promise.all(
      tracks.map(async (track) => {
        const spotifyUrl = track.external_urls.spotify;
        const previewUrls = await getSpotifyLinks(spotifyUrl);
        return {
          name: `${track.name} - ${track.artists
            .map((artist) => artist.name)
            .join(", ")}`,
          spotifyUrl: spotifyUrl,
          previewUrls: previewUrls,
        };
      })
    );

    return {
      success: true,
      results: results,
    };
  } catch (error) {
    return {
      success: false,
      error: (error as Error).message,
      results: [],
    };
  }
}
