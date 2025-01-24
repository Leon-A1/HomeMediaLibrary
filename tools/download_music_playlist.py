import os
import subprocess
from flask import jsonify
import yt_dlp
import queue

# Add this global variable at the top of the file
progress_queue = queue.Queue()

def download_from_youtube(url, format_type, download_id):
    try:
        # Define base paths
        base_path = "C:/Users/leona/Desktop/Code 2025/HomeMediaLibrary"
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                # Calculate progress percentage
                total_bytes = d.get('total_bytes')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                if total_bytes:
                    progress = (downloaded_bytes / total_bytes) * 100
                    progress_queue.put({
                        'id': download_id,
                        'progress': round(progress, 1),
                        'status': 'Downloading...'
                    })
            elif d['status'] == 'finished':
                progress_queue.put({
                    'id': download_id,
                    'progress': 100,
                    'status': 'Processing...'
                })

        # Set output folder based on format type
        if format_type == "audio":
            output_folder = os.path.join(base_path, "Music/Downloads")
            command = [
                "yt-dlp",
                "--extract-audio",
                "--audio-format", "mp3",
                "--embed-metadata",
                "--add-metadata",
                "--parse-metadata", "%(artist)s:%(uploader)s",
                "--output", f"{output_folder}/%(artist)s - %(title)s (%(upload_date>%Y)s).%(ext)s",
                "--metadata-from-title", "(?P<artist>.+?) - (?P<title>.+)",
                "--progress-hooks", [progress_hook],
                url
            ]
        else:  # video
            output_folder = os.path.join(base_path, "Photos&Videos/Downloads")
            command = [
                "yt-dlp",
                "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
                "--merge-output-format", "mp4",
                "--output", f"{output_folder}/%(title)s (%(upload_date>%Y)s).%(ext)s",
                "--progress-hooks", [progress_hook],
                url
            ]

        # Create output folder if it doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # Execute yt-dlp with progress hooks
        ydl_opts = {
            'format': 'bestaudio/best' if format_type == "audio" else 'bestvideo+bestaudio/best',
            'progress_hooks': [progress_hook],
            'outtmpl': command[-2],  # Use the output template from command
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }] if format_type == "audio" else []
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        progress_queue.put({
            'id': download_id,
            'progress': 100,
            'complete': True,
            'success': True
        })
        return {"success": True}

    except Exception as e:
        progress_queue.put({
            'id': download_id,
            'progress': 100,
            'complete': True,
            'success': False,
            'error': str(e)
        })
        return {"success": False, "error": str(e)}