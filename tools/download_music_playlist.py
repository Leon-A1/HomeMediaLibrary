import os
import subprocess
from flask import jsonify
import yt_dlp
import queue

# Add this global variable at the top of the file
progress_queue = queue.Queue()


def clean_music_downloads(folder="Downloads"):
    if not folder or folder == "Downloads":
        downloads_directory = "C:/Users/leona/Desktop/Code 2025/HomeMediaLibrary/Music/Downloads"
    else:
        downloads_directory = f"C:/Users/leona/Desktop/Code 2025/HomeMediaLibrary/Music/{folder}"
    # Iterate through files in the directory
    for filename in os.listdir(downloads_directory):

        if filename.startswith("NA -"):

            new_filename = filename[4:]  # Remove "NA -" (4 characters)
            old_path = os.path.join(downloads_directory, filename)
            new_path = os.path.join(downloads_directory, new_filename)

            # Rename the file
            os.rename(old_path, new_path)
            print(f'Renamed: "{filename}" → "{new_filename}"')


    print("Renaming complete.")



def download_from_youtube(url, format_type, download_id, folder='Downloads'):
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
            output_folder = os.path.join(base_path, "Music", folder)
            output_template = f"{output_folder}/%(artist)s - %(title)s (%(upload_date>%Y)s).%(ext)s"
            ydl_opts = {
                'format': 'bestaudio/best',
                'progress_hooks': [progress_hook],
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }],
                'embed-metadata': True,
                'add-metadata': True,
                'parse-metadata': '%(artist)s:%(uploader)s',
                'metadata-from-title': '(?P<artist>.+?) - (?P<title>.+)'
            }
        else:  # video
            output_folder = os.path.join(base_path, "Photos&Videos/Downloads")
            output_template = f"{output_folder}/%(title)s (%(upload_date>%Y)s).%(ext)s"
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
                'progress_hooks': [progress_hook],
                'outtmpl': output_template,
                'merge_output_format': 'mp4'
            }

        # Create output folder if it doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        progress_queue.put({
            'id': download_id,
            'progress': 100,
            'complete': True,
            'success': True
        })
        clean_music_downloads(folder)
        return {"success": True}

    except Exception as e:
        progress_queue.put({
            'id': download_id,
            'progress': 100,
            'complete': True,
            'success': False,
            'error': str(e)
        })
        clean_music_downloads(folder)
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    clean_music_downloads("Hebrew")
