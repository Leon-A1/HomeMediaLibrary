import os
import subprocess

# Define the playlist URL and output folder
playlist_url = "https://www.youtube.com/watch?v=oPo86ureETg"
output_folder = "Music/Downloads"

# Create the output folder if it doesn't exist
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Enhanced yt-dlp command with metadata handling
command = [
    "yt-dlp",
    "--extract-audio",
    "--audio-format", "mp3",
    "--embed-metadata",          # Embed metadata in file
    "--add-metadata",           # Add metadata to file
    "--parse-metadata",        # Parse metadata
    "%(artist)s:%(uploader)s", # Use uploader as artist if artist not available
    "--output", f"{output_folder}/%(artist)s - %(title)s (%(upload_date>%Y)s).%(ext)s",
    "--metadata-from-title", "(?P<artist>.+?) - (?P<title>.+)",  # Extract artist/title from video title
    "--yes-playlist",
    "--format", 'best',
    playlist_url
]

try:
    subprocess.run(command, check=True)
    print(f"All songs from the playlist have been downloaded to the '{output_folder}' folder.")
except subprocess.CalledProcessError as e:
    print(f"An error occurred: {e}")