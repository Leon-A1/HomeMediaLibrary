import os
import subprocess

# Define the playlist URL and output folder
playlist_url = "https://music.youtube.com/playlist?list=PLpDHBn_bSGr7WnHt4SNf9NkWHmDlfMG6U&si=nwxL-5mcQI7pjHyF"
output_folder = "Music"

# Create the output folder if it doesn't exist
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# yt-dlp command for downloading the playlist as MP3
command = [
    "yt-dlp",
    "--extract-audio",           # Extract audio only
    "--audio-format", "mp3",     # Save audio in MP3 format
    "--output", f"{output_folder}/%(title)s.%(ext)s",  # Output file naming
    "--yes-playlist",            # Download the whole playlist
    playlist_url
]


try:
    # Run the yt-dlp command
    subprocess.run(command, check=True)
    print(f"All songs from the playlist have been downloaded to the '{output_folder}' folder.")
except subprocess.CalledProcessError as e:
    print(f"An error occurred: {e}")
