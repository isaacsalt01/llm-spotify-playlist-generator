import json
from spotify_client import SpotifyClient
from llm_client import LLMClient


def generate_playlist(user_input, user_track_list=None, access_token=None):
    spotify = SpotifyClient()
    llm = LLMClient()

    # Generate description
    description = llm.generate_playlist_description(user_input, user_track_list)

    # Find correct ouput index for description
    # Start with high value to act as a case where no elemenets reach the if statement
    index_desc = 100
    for i, element in enumerate(description.output):
        if element.content is not None:
            print(element)
            index_desc = i
            break
    if index_desc == 100:
        description = "No output from model"
    else:
        description = description.output[index_desc].content[0].text
        print(f"Playlist Description: {description}")

    # Suggest tracks using LLM
    suggestions = llm.suggest_tracks(description, user_track_list)

    # Find correct output index for tracks
    index_tracks = 100
    for i, element in enumerate(suggestions.output):
        if element.content is not None:
            index_tracks = i
            break

    if index_tracks == 100:
        tracks = "No output from model"
        track_uris = []
    else:
        tracks_json = suggestions.output[index_tracks].content[0].text
        tracks = json.loads(tracks_json)
        print(tracks)

        # Search for track URIs
        track_uris = []
        filtered_tracks = []
        for track in tracks:
            uri = spotify.get_track_uri(track["name"], track["artist"])
            if uri:
                track_uris.append(uri)
                track["uri"] = uri  # Add URI to track object
                filtered_tracks.append(track)
        tracks = filtered_tracks

    playlist_id = None
    if access_token and track_uris:
        description_text = (
            description
            if isinstance(description, str)
            else description.output[index_desc].content[0].text
        )
        playlist_id = spotify.create_playlist(
            access_token, user_input, description_text, track_uris
        )

    return description, tracks, playlist_id


if __name__ == "__main__":
    user_i = input("Enter playlist theme: ")
    generate_playlist(user_i)
