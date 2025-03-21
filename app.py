import os
from flask import Flask, render_template, send_from_directory, abort, jsonify, request, session, redirect, url_for, Response
import ebooklib
from ebooklib import epub
from PIL import Image
import base64
import json
from datetime import datetime
from PIL.ExifTags import TAGS
import time
import subprocess
import queue
import threading
import yt_dlp
from bs4 import BeautifulSoup
import html
import random
import re
import urllib
from mutagen.id3 import ID3
from faster_whisper import WhisperModel
import tempfile
import shutil
from OpenSSL import crypto
import ssl
from urllib.parse import unquote

current_directory = os.path.dirname(os.path.realpath(__file__)).replace("\\","/")

app = Flask(__name__,template_folder= current_directory+"/templates")

files_dir = current_directory + "/Files"
NOTEBOOK_DIR = files_dir + "/Notebook"
MUSIC_DIR = files_dir + "/Music"
MEDIA_DIR = files_dir + "/Photos&Videos"
BOOK_DIR = files_dir + "/Books"  
LOCKED_DIR = files_dir + "/Locked"
SHUFFLED_DIR = files_dir + "/shuffled"

# Configuration
ALLOWED_EXTENSIONS = {'epub'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
ALLOWED_PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}
FINISHED_BOOKS_FILE = files_dir + "/finished_books.json"
MAIN_PASSWORD = ""  # Password for most sections
PRIVATE_PASSWORD = ""  # Use the existing PASSWORD for locked and notebook sections


# Add these global variables at the top of the file
download_progress = {}
progress_queue = queue.Queue()

# Add this near the top with other configuration variables
BOOKMARKS_FILE = files_dir + "/bookmarks.json"
TASKS_FILE = files_dir + "/tasks.json"

def load_finished_books():
    if os.path.exists(FINISHED_BOOKS_FILE):
        with open(FINISHED_BOOKS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_finished_books(finished_books):
    with open(FINISHED_BOOKS_FILE, 'w') as f:
        json.dump(finished_books, f, indent=4)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS




def load_shuffle_history(folder_name):
    json_path = os.path.join(SHUFFLED_DIR, f"{folder_name}.json")
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            return json.load(f)
    return []

def save_shuffle_history(folder_name, played_songs):
    os.makedirs(SHUFFLED_DIR, exist_ok=True)
    json_path = os.path.join(SHUFFLED_DIR, f"{folder_name}.json")
    with open(json_path, 'w') as f:
        json.dump(played_songs, f, indent=4)

def get_paginated_files(directory, allowed_extensions, page, per_page=5):
    files = [f for f in os.listdir(directory) 
             if f.lower().endswith(tuple(allowed_extensions))]
    files.sort()
    start = (page - 1) * per_page
    end = start + per_page
    return files[start:end], len(files)


def scan_video_contents(directory, path=''):
    """Get folders and files from the specified directory and path (for videos)"""
    full_path = os.path.join(directory, path)
    items = []
    folders = []

    try:
        # First scan for all items
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            relative_path = os.path.join(path, item).replace('\\', '/')
            
            if os.path.isdir(item_path):
                # Check if the folder contains any videos (including in subfolders)
                has_videos = False
                for root, _, files in os.walk(item_path):
                    if any(f.lower().endswith(tuple(ALLOWED_VIDEO_EXTENSIONS)) for f in files):
                        has_videos = True
                        break
                
                if has_videos:
                    folders.append({
                        'name': item,
                        'path': relative_path + '/'
                    })
            elif item.lower().endswith(tuple(ALLOWED_VIDEO_EXTENSIONS)):
                items.append(item)
    except Exception as e:
        print(f"Error reading directory: {e}")
        return [], []

    return folders, items

def get_photo_date(file_path):
    """Get the original creation date from image metadata"""
    try:
        with Image.open(file_path) as img:
            exif = img._getexif()
            if exif:
                # Convert EXIF tags to a readable dictionary
                exif_data = {TAGS.get(tag_id, tag_id): value
                           for tag_id, value in exif.items()}
                
                # Look for CreateDate or DateTimeOriginal
                if 'CreateDate' in exif_data:
                    date_str = exif_data['CreateDate']
                    return time.mktime(time.strptime(date_str, "%Y:%m:%d %H:%M:%S"))
                elif 'DateTimeOriginal' in exif_data:
                    date_str = exif_data['DateTimeOriginal']
                    return time.mktime(time.strptime(date_str, "%Y:%m:%d %H:%M:%S"))
    except:
        pass
    
    # If no EXIF data, try to get file creation time (Windows)
    try:
        stats = os.stat(file_path)
        # On Windows, st_ctime is the creation time
        return stats.st_ctime
    except:
        return time.time()

def scan_photo_contents(directory, path=''):
    """Get folders and files from the specified directory and path (for photos)"""
    full_path = os.path.join(directory, path)
    items = []
    folders = []

    try:
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            relative_path = os.path.join(path, item).replace('\\', '/')
            
            if os.path.isdir(item_path):
                folders.append({
                    'name': item,
                    'path': relative_path + '/'
                })
            elif item.lower().endswith(tuple(ALLOWED_PHOTO_EXTENSIONS)):
                # Get the media created date
                date = get_photo_date(item_path)
                items.append({
                    'name': item,
                    'date': date
                })
    except Exception as e:
        print(f"Error reading directory: {e}")
        return [], []

    # Sort items by date before returning
    items.sort(key=lambda x: x['date'], reverse=True)
    return folders, items



def has_music():
    # Check root music directory and Downloads folder
    downloads_path = MUSIC_DIR + '/Downloads'
    has_downloads = os.path.exists(downloads_path) and any(
        f.lower().endswith(('.mp3', '.wav', '.flac', '.aac')) 
        for f in os.listdir(downloads_path)
    )
    
    # Check other folders
    has_other_music = any(
        f.lower().endswith(('.mp3', '.wav', '.flac', '.aac')) 
        for root, _, files in os.walk(MUSIC_DIR) 
        for f in files
    )
    
    return has_downloads or has_other_music

def has_photos():
    return any(
        f.lower().endswith(tuple(ALLOWED_PHOTO_EXTENSIONS)) 
        for root, _, files in os.walk(MEDIA_DIR) 
        for f in files
    )

def has_videos():
    return any(
        f.lower().endswith(tuple(ALLOWED_VIDEO_EXTENSIONS)) 
        for root, _, files in os.walk(MEDIA_DIR) 
        for f in files
    )


def check_auth(section):
    """Check if user is authenticated for a specific section"""
    if section in ["locked", "notebook"]:
        # Skip auth if private password is empty
        if not PRIVATE_PASSWORD:
            return True
        return session.get('authenticated_private', False)
    else:
        # Skip auth if main password is empty
        if not MAIN_PASSWORD:
            return True
        return session.get('authenticated_main', False)

def check_auth_any():
    """Check if user is authenticated for any section"""
    # If both passwords are empty, user is effectively authenticated for everything
    if not MAIN_PASSWORD and not PRIVATE_PASSWORD:
        return True
    return session.get('authenticated_main', False) or session.get('authenticated_private', False)
    
def has_protected_content():
    """Check if there is any password protection enabled"""
    return bool(MAIN_PASSWORD.strip() or PRIVATE_PASSWORD.strip())

@app.route('/')
def index():
    quotes_path = os.path.join('Files', 'inspirational_quotes.json')
    try:
        with open(quotes_path, 'r', encoding='utf-8') as f:
            quotes = json.load(f)

        quote = random.choice(quotes) if quotes else None
    except (FileNotFoundError, json.JSONDecodeError):
        quote = None
    
    return render_template('index.html', 
                          quote=quote,
                          has_music=has_music(),
                          has_books=has_books(),
                          has_photos=has_photos(),
                          has_videos=has_videos(),
                          has_protected=True)  # Always show as protected now

@app.route('/music')
def music():
    if not check_auth('music'):
        return redirect(url_for('section_login', section='music'))
    
    # Get folders and their file counts
    folders = ['Downloads']  # Downloads as first folder option
    folder_counts = {}
    
    # Count files in Downloads folder
    downloads_folder_path = os.path.join(MUSIC_DIR, 'Downloads')
    root_files = [f for f in os.listdir(downloads_folder_path) 
                  if os.path.isfile(os.path.join(downloads_folder_path, f)) 
                  and f.lower().endswith(('.mp3', '.wav', '.flac', '.aac'))]
    folder_counts['Downloads'] = len(root_files)
    
    # Get other folders from Music directory
    for item in os.listdir(MUSIC_DIR):
        if item == "Downloads":
            continue
        if os.path.isdir(os.path.join(MUSIC_DIR, item)):
            folders.append(item)
            folder_path = os.path.join(MUSIC_DIR, item)
            files = [f for f in os.listdir(folder_path) 
                    if os.path.isfile(os.path.join(folder_path, f)) 
                    and f.lower().endswith(('.mp3', '.wav', '.flac', '.aac'))]
            folder_counts[item] = len(files)
    
    # Get music files from Downloads folder for initial display
    music_files = root_files
    
    return render_template('music.html', 
                         music_files=music_files,
                         folders=folders,
                         folder_counts=folder_counts)

@app.route('/search_music')
def search_music():
    query = request.args.get('q', '').lower()
    folder = request.args.get('folder', 'Downloads')
    
    # Determine the folder path
    folder_path = os.path.join(MUSIC_DIR, folder)
    
    if not os.path.exists(folder_path):
        return jsonify([])
    
    # Get all music files in the folder
    music_files = [f for f in os.listdir(folder_path) 
                  if f.lower().endswith(('.mp3', '.wav', '.flac', '.aac'))]
    
    # Filter files based on search query
    filtered_files = []
    for file in music_files:
        # Check filename
        if query in file.lower():
            filtered_files.append(file)
            continue
            
        # Check file metadata if it's an MP3
        if file.lower().endswith('.mp3'):
            try:
                file_path = os.path.join(folder_path, file)
                audio = ID3(file_path)
                if audio:
                    # Check title
                    if audio.get('TIT2') and query in audio['TIT2'].text[0].lower():
                        filtered_files.append(file)
                        continue
                    # Check artist
                    if audio.get('TPE1') and query in audio['TPE1'].text[0].lower():
                        filtered_files.append(file)
                        continue
                    # Check album
                    if audio.get('TALB') and query in audio['TALB'].text[0].lower():
                        filtered_files.append(file)
                        continue
            except Exception:
                pass  # Skip if metadata can't be read
    
    return jsonify(filtered_files)

@app.route('/folder/<path:folder_name>')
def get_folder_contents(folder_name):
    folder_path = os.path.join(MUSIC_DIR, folder_name)
    music_files = []
    if os.path.exists(folder_path):
        for file in os.listdir(folder_path):
            if file.lower().endswith(('.mp3', '.wav', '.flac', '.aac')):
                music_files.append(file)
    return jsonify(music_files)

@app.route('/music/<path:filename>')
def stream_music(filename):
    if not check_auth('music'):
        abort(403)
    # Split the path into folder and filename
    parts = os.path.split(filename)
    if len(parts) > 1:
        folder, file = parts
        return send_from_directory(os.path.join(MUSIC_DIR, folder), file)
    return send_from_directory(MUSIC_DIR, filename)

@app.route('/photos')
def photos():
    if not check_auth('photos'):
        return redirect(url_for('section_login', section='photos'))
    return render_template('photos.html', **get_back_context())

@app.route('/api/photos')
def get_photos():
    if not check_auth('photos'):
        abort(403)
    page = int(request.args.get('page', 1))
    path = request.args.get('path', '')
    per_page = 5

    # Get folders and files using the photo-specific function
    folders, photos = scan_photo_contents(MEDIA_DIR, path)
    
    # Sort folders alphabetically
    folders.sort(key=lambda x: x['name'].lower())
    
    # Sort photos by date, newest first
    photos.sort(key=lambda x: x['date'], reverse=True)
    
    # Extract just the filenames for pagination
    photo_files = [photo['name'] for photo in photos]

    # Paginate photos
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_photos = photo_files[start_idx:end_idx]

    has_more = end_idx < len(photos)

    return jsonify({
        'folders': folders if page == 1 else [],  # Only send folders on first page
        'items': paginated_photos,
        'hasMore': has_more,
        'total': len(photos)
    })

@app.route('/videos')
def videos():
    if not check_auth('videos'):
        return redirect(url_for('section_login', section='videos'))
    return render_template('videos.html')

def get_video_date(file_path):
    """
    Returns the creation date (as a UNIX timestamp) of the video by checking its metadata via ffprobe.
    Falls back to the file modification time if the metadata is missing or an error occurs.
    """
    try:
        command = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format_tags=creation_time",
            file_path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data = json.loads(result.stdout)
        creation_time = data.get("format", {}).get("tags", {}).get("creation_time")
        if creation_time:
            # Example format: "2020-08-05T14:12:31.000000Z"
            dt = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
            return dt.timestamp()
    except Exception as e:
        print(f"Error reading video metadata for {file_path}: {e}")
    return os.path.getmtime(file_path)

@app.route('/api/videos')
def get_videos():
    if not check_auth('videos'):
        abort(403)
    page = int(request.args.get('page', 1))
    path = request.args.get('path', '')
    per_page = 5

    # Get folders and video files using the video-specific function
    folders, videos = scan_video_contents(MEDIA_DIR, path)
    
    # Sort folders alphabetically
    folders.sort(key=lambda x: x['name'].lower())
    
    # Sort videos by metadata "creation_time" (newest first). Falls back to file modified time.
    videos.sort(key=lambda video: get_video_date(os.path.join(MEDIA_DIR, path, video)), reverse=True)

    # Paginate videos
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_videos = videos[start_idx:end_idx]
    has_more = end_idx < len(videos)

    return jsonify({
        'folders': folders if page == 1 else [],  # Only send folders on first page
        'items': paginated_videos,
        'hasMore': has_more,
        'total': len(videos)
    })

@app.route('/media/<path:filename>')
def serve_media(filename):
    if not check_auth('photos'):  # Using photos auth for media
        abort(403)
    parts = filename.split('/')
    directory = os.path.join(MEDIA_DIR, *parts[:-1])
    return send_from_directory(directory, parts[-1])

@app.route('/locked')
def locked():
    if not check_auth('locked'):
        return redirect(url_for('section_login', section='locked'))
    return render_template('locked.html')

@app.route('/api/locked')
def get_locked():
    if not check_auth('locked'):
        abort(403)
    page = int(request.args.get('page', 1))
    per_page = 5
    media_type = request.args.get('type', 'all')

    all_items = []
    if media_type == 'photos':
        # Get only photo files and their dates
        photo_files = [f for f in os.listdir(LOCKED_DIR)
                       if f.lower().endswith(tuple(ALLOWED_PHOTO_EXTENSIONS))]
        for f in photo_files:
            file_path = os.path.join(LOCKED_DIR, f)
            file_date = get_photo_date(file_path)
            all_items.append({'filename': f, 'date': file_date, 'type': 'photo'})
    elif media_type == 'videos':
        # Get only video files and their dates
        video_files = [f for f in os.listdir(LOCKED_DIR)
                       if f.lower().endswith(tuple(ALLOWED_VIDEO_EXTENSIONS))]
        for f in video_files:
            file_path = os.path.join(LOCKED_DIR, f)
            file_date = get_video_date(file_path)
            all_items.append({'filename': f, 'date': file_date, 'type': 'video'})
    else:
        # Get both photos and videos
        allowed_extensions = ALLOWED_PHOTO_EXTENSIONS.union(ALLOWED_VIDEO_EXTENSIONS)
        files = [f for f in os.listdir(LOCKED_DIR)
                 if f.lower().endswith(tuple(allowed_extensions))]
        for f in files:
            file_path = os.path.join(LOCKED_DIR, f)
            if f.lower().endswith(tuple(ALLOWED_PHOTO_EXTENSIONS)):
                file_date = get_photo_date(file_path)
                file_type = 'photo'
            else:
                file_date = get_video_date(file_path)
                file_type = 'video'
            all_items.append({'filename': f, 'date': file_date, 'type': file_type})

    # Sort all items by date in descending order (newest first)
    all_items.sort(key=lambda x: x['date'], reverse=True)

    total = len(all_items)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_items = all_items[start_idx:end_idx]
    
    # Return only the filenames; the client uses the filename to build the media path
    items = [item['filename'] for item in paginated_items]
    has_more = end_idx < total

    return jsonify({
        'items': items,
        'hasMore': has_more,
        'total': total
    })

@app.route('/login/<section>', methods=['GET', 'POST'])
def section_login(section):
    # Determine which password to use based on section
    if section in ["locked", "notebook"]:
        auth_type = "private"
        password = PRIVATE_PASSWORD
    else:
        auth_type = "main"
        password = MAIN_PASSWORD
        
    if request.method == 'POST':
        if request.form.get('password') == password:
            session[f'authenticated_{auth_type}'] = True
            # Determine where to redirect based on section
            redirect_map = {
                "books": "/books",
                "music": "/music",
                "photos": "/photos",
                "videos": "/videos",
                "notebook": "/notebook",
                "calendar": "/calendar",
                "youtube": "/youtube-downloader",
                "locked": "/locked"
            }
            return jsonify({'success': True, 'redirect': redirect_map.get(section, '/')})
        return jsonify({'success': False, 'message': 'Invalid password'})
    
    return render_template('login.html', section=section)

@app.route('/logout/<auth_type>')
def section_logout(auth_type):
    if auth_type in ["main", "private"]:
        session.pop(f'authenticated_{auth_type}', None)
    return redirect(url_for('index'))

@app.route('/add_shuffled_song', methods=['POST'])
def add_shuffled_song():
    data = request.json
    folder_name = data.get('folder', 'Downloads')
    song = data.get('song')
    
    if not song:
        return jsonify({'success': False, 'message': 'No song provided'})

    # Get the folder path and count total songs
    folder_path = os.path.join(MUSIC_DIR, folder_name)
    total_songs = len([f for f in os.listdir(folder_path) 
                      if os.path.isfile(os.path.join(folder_path, f)) 
                      and f.lower().endswith(('.mp3', '.wav', '.flac', '.aac'))])

    # Load existing history
    played_songs = load_shuffle_history(folder_name)
    
    # Check if song is already in list
    if song in played_songs:
        return jsonify({
            'success': False,
            'message': 'Song already played',
            'played_songs': played_songs,
            'should_skip': True
        })

    # Add new song to list
    played_songs.append(song)
    
    # Reset if we've played all songs
    if len(played_songs) >= total_songs:
        played_songs = [song]
    
    # Save updated history
    save_shuffle_history(folder_name, played_songs)
    
    return jsonify({
        'success': True, 
        'played_songs': played_songs,
        'should_skip': False,
        'should_reset': len(played_songs) >= total_songs
    })

app.secret_key = 'your-secret-key-here'  # Change this to a secure random key in production



def load_notebook_pages():
    pages = []
    if os.path.exists(NOTEBOOK_DIR):
        for filename in os.listdir(NOTEBOOK_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(NOTEBOOK_DIR, filename) 
                try:
                    with open(filepath, 'r') as f:
                        page_data = json.load(f)
                        pages.append(page_data)
                except Exception as e:
                    print(f"Error loading notebook page {filename}: {e}")
    
    # Sort pages by updatedAt in descending order (newest first)
    pages.sort(key=lambda x: x.get('updatedAt', ''), reverse=True)
    return pages




@app.route('/notebook')
def notebook():
    if not check_auth('notebook'):
        return redirect(url_for('section_login', section='notebook'))
    pages = load_notebook_pages()
    return render_template('notebook.html', 
                         pages=pages, 
                         **get_back_context(show_back=True))

@app.route('/notebook/create', methods=['POST'])
def create_page():
    now = datetime.now()
    base_date_str = now.strftime("%Y-%m-%d")

    existing_files = []
    for filename in os.listdir(NOTEBOOK_DIR):
        if filename.startswith(base_date_str) and filename.endswith('.json'):
            existing_files.append(filename)

    suffixes = []
    for filename in existing_files:
        name_part = filename[:-5]  # Remove .json
        if name_part == base_date_str:
            suffixes.append(1)
        else:
            remaining = name_part[len(base_date_str):]
            if remaining.startswith('-') and remaining[1:].isdigit():
                suffix = int(remaining[1:])
                suffixes.append(suffix)

    max_suffix = max(suffixes) if suffixes else 0
    new_suffix = max_suffix + 1 if max_suffix > 0 else 1

    if new_suffix == 1:
        new_filename = f"{base_date_str}.json"
    else:
        new_filename = f"{base_date_str}-{new_suffix}.json"

    new_name = new_filename[:-5]  # Remove .json extension

    new_page = {
        "name": new_name,
        "content": "",
        "createdAt": now.isoformat(),
        "updatedAt": now.isoformat()
    }

    filepath = os.path.join(NOTEBOOK_DIR, new_filename)
    with open(filepath, 'w') as f:
        json.dump(new_page, f, indent=4)

    return jsonify({"success": True, "page": new_page})

@app.route('/notebook/<name>')
def get_page(name):
    pages = load_notebook_pages()
    page = next((p for p in pages if p['name'] == name), None)
    if page is None:
        abort(404)
    return render_template('notebook_page.html', 
                         page=page, 
                         **get_back_context(back_url='/notebook'))

@app.route('/notebook/<name>', methods=['POST'])
def update_page(name):
    content = request.json.get('content')
    filename = f"{name}.json"
    filepath = os.path.join(NOTEBOOK_DIR, filename)

    if not os.path.exists(filepath):
        abort(404)

    with open(filepath, 'r') as f:
        page = json.load(f)

    page['content'] = content
    page['updatedAt'] = datetime.now().isoformat()

    with open(filepath, 'w') as f:
        json.dump(page, f, indent=4)

    return jsonify({"success": True, "page": page})

@app.route('/notebook/<name>/rename', methods=['POST'])
def rename_page(name):
    data = request.json
    new_name = data.get('newName')
    
    if not new_name:
        return jsonify({"success": False, "message": "New name cannot be empty"})
    
    # Check if the new name already exists
    new_filename = f"{new_name}.json"
    new_filepath = os.path.join(NOTEBOOK_DIR, new_filename)
    if os.path.exists(new_filepath):
        return jsonify({"success": False, "message": "A page with this name already exists"})
    
    # Get the old file
    old_filename = f"{name}.json"
    old_filepath = os.path.join(NOTEBOOK_DIR, old_filename)
    
    if not os.path.exists(old_filepath):
        return jsonify({"success": False, "message": "Page not found"})
    
    # Load the page data
    with open(old_filepath, 'r') as f:
        page = json.load(f)
    
    # Update the name and updatedAt
    page['name'] = new_name
    page['updatedAt'] = datetime.now().isoformat()
    
    # Save to the new file
    with open(new_filepath, 'w') as f:
        json.dump(page, f, indent=4)
    
    # Delete the old file
    os.remove(old_filepath)
    
    return jsonify({"success": True, "page": page})

@app.route('/notebook/<name>/delete', methods=['POST'])
def delete_page(name):
    try:
        # Decode the URL-encoded name
        decoded_name = unquote(name)
        print(f"Attempting to delete page: '{decoded_name}'")
        
        # Find the file to delete
        filename = f"{decoded_name}.json"
        filepath = os.path.join(NOTEBOOK_DIR, filename)
        
        if not os.path.exists(filepath):
            print(f"Page file not found: '{filepath}'")
            return jsonify({'success': False, 'message': 'Page file not found'})
        
        # Delete the file
        os.remove(filepath)
        print(f"Deleted page file: '{filepath}'")
        
        return jsonify({'success': True})
    except Exception as e:
        import traceback
        print(f"Error deleting page: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

def download_from_youtube(url, format_type, download_id, folder):
    try:
        # Define base paths
        base_path = current_directory
        files_dir = os.path.join(base_path, "files")
        
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
                        'status': 'Downloading...',
                        'folder': folder
                    })
            elif d['status'] == 'finished':
                progress_queue.put({
                    'id': download_id,
                    'progress': 100,
                    'status': 'Processing...',
                    'folder': folder
                })

        # Set output folder based on format type
        if format_type == "audio":
            downloads_folder = folder if folder else "Downloads"
            output_folder = os.path.join(files_dir, f"Music/{downloads_folder}")

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
            output_folder = os.path.join(files_dir, "Photos&Videos/Downloads")
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
            'success': True,
            'folder': folder
        })
        return {"success": True}

    except Exception as e:
        progress_queue.put({
            'id': download_id,
            'progress': 100,
            'complete': True,
            'success': False,
            'error': str(e),
            'folder': folder
        })
        return {"success": False, "error": str(e)}

@app.route('/youtube-downloader')
def youtube_downloader():
    if not check_auth('youtube'):
        return redirect(url_for('section_login', section='youtube'))
    return render_template('youtube_downloader.html', **get_back_context())

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    format_type = data.get('format')
    folder = data.get('folder', 'Downloads')
    
    if not url:
        return jsonify({"success": False, "error": "No URL provided"})
    
    result = download_from_youtube(url, format_type, f"{url}_{format_type}", folder)
    return jsonify(result)

@app.route('/download-progress')
def download_progress_stream():
    url = request.args.get('url')
    format_type = request.args.get('format')
    folder = request.args.get('folder', 'Downloads')  # Default to Downloads
    download_id = f"{url}_{format_type}"
    
    def generate():
        thread = threading.Thread(
            target=download_from_youtube,
            args=(url, format_type, download_id, folder),  # Add folder parameter
            daemon=True
        )
        thread.start()
        
        while True:
            try:
                # Get progress updates from the queue
                progress_data = progress_queue.get(timeout=1)
                if progress_data['id'] == download_id:
                    yield f"data: {json.dumps(progress_data)}\n\n"
                    if progress_data.get('complete', False):
                        break
            except queue.Empty:
                # Send keepalive
                yield f"data: {json.dumps({'status': 'Processing...'})}\n\n"
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )

@app.route('/api/music-folders')
def get_music_folders():
    folders = ['Downloads']  # Start with Downloads as default
    for item in os.listdir(MUSIC_DIR):
        if os.path.isdir(os.path.join(MUSIC_DIR, item)) and item != 'Downloads':
            folders.append(item)
    return jsonify(folders)





########################################################
#### Books ############################################
########################################################

@app.route('/read/<path:filename>')
def read_book(filename):
    if not check_auth('books'):
        return redirect(url_for('section_login', section='books'))
    if not allowed_file(filename):
        abort(404)
    return render_template('reader.html', 
                         filename=filename, 
                         title=os.path.splitext(filename)[0],
                         **get_back_context(back_url='/books'))

@app.route('/book-content/<path:filename>')
def get_book_content(filename):
    if not check_auth('books'):
        abort(403)
    if not allowed_file(filename):
        abort(404)
    
    book_path = os.path.join(BOOK_DIR, filename)
    book = epub.read_epub(book_path)
    
    # Prepare a map of images
    image_map = {}
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            try:
                image_data = base64.b64encode(item.get_content()).decode('utf-8')
                
                # Get file extension from the name or default to jpeg
                name = item.get_name()
                ext = name.split('.')[-1].lower() if '.' in name else 'jpeg'
                
                # Set the appropriate MIME type
                mime_type = f"image/{ext}"
                if ext == 'svg':
                    mime_type = "image/svg+xml"
                elif ext in ['jpg', 'jpeg']:
                    mime_type = "image/jpeg"
                
                data_url = f"data:{mime_type};base64,{image_data}"
                
                # Map the image using multiple possible key formats to improve link resolution
                image_map[name] = data_url  # Full path
                image_map[os.path.basename(name)] = data_url  # Just the filename
                
                # Also map without extension
                base_without_ext = os.path.splitext(os.path.basename(name))[0]
                image_map[base_without_ext] = data_url
                
                # Additional mapping for URL-encoded paths
                image_map[urllib.parse.unquote(name)] = data_url
                image_map[urllib.parse.quote(name)] = data_url
                
                # Handle relative paths
                image_map[name.lstrip('./')] = data_url
                
            except Exception as e:
                print(f"Error processing image {item.get_name()}: {e}")
    
    all_content = []
    episodes = []
    
    # First pass: Extract all document content
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            try:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                
                # Remove style and link elements
                for tag in soup.find_all(['style', 'link']):
                    tag.decompose()
                
                # Fix image links
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if src:
                        img_matched = False
                        
                        # Try different variations of the src to find a match
                        potential_matches = [
                            src,
                            os.path.basename(src),
                            os.path.splitext(os.path.basename(src))[0],
                            urllib.parse.unquote(src),
                            urllib.parse.quote(src),
                            src.lstrip('./')
                        ]
                        
                        for potential_src in potential_matches:
                            if potential_src in image_map:
                                img['src'] = image_map[potential_src]
                                img_matched = True
                                break
                        
                        if not img_matched:
                            # If no match found, set a placeholder or remove
                            img['src'] = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAAB3RJTUUH4QgFDDYAFzD+TgAAABl0RVh0Q29tbWVudABDcmVhdGVkIHdpdGggR0lNUFeBDhcAAABISURBVHja7c0xAQAACAMgtH+KLzrABTZ4ABIkQIAASIAAAZAAARIgAZAAARIgARIgAQIkQAIEQAIESIAESIAE6G9PwQGAAQBfgwvLTzLiAgAAAABJRU5ErkJggg=='
                
                # Get html content
                content = str(soup.body) if soup.body else str(soup)
                unescaped_content = html.unescape(content)
                
                # Add to all content collection for further processing
                all_content.append(unescaped_content)
                
            except Exception as e:
                print(f"Error processing document {item.get_name()}: {e}")
    
    # Second pass: Split content into pages of appropriate length
    standardized_pages = []
    current_episodes = []
    
    for doc_content in all_content:
        # Remove HTML tags for character counting but preserve for actual content
        text_only = BeautifulSoup(doc_content, 'html.parser').get_text()
        max_length = 1000
        if len(text_only) <= max_length:
            # If content is already within range, keep as is
            standardized_pages.append(doc_content)
            current_episodes.append([doc_content])
        else:
            # Need to split this content
            doc_soup = BeautifulSoup(doc_content, 'html.parser')
            elements = list(doc_soup.body.children) if doc_soup.body else list(doc_soup.children)
            
            pages = []
            current_page = ''
            current_page_text_length = 0
            
            for elem in elements:
                elem_str = str(elem)
                elem_text = elem.get_text() if hasattr(elem, 'get_text') else str(elem)
                
                # If adding this element would exceed our limit, start a new page
                if current_page_text_length + len(elem_text) > max_length and current_page_text_length > 800:
                    pages.append(current_page)
                    current_page = elem_str
                    current_page_text_length = len(elem_text)
                else:
                    current_page += elem_str
                    current_page_text_length += len(elem_text)
            
            # Add the last page if it has content
            if current_page:
                pages.append(current_page)
            
            # Handle edge case where a single element is larger than our limit
            final_pages = []
            for page in pages:
                page_text = BeautifulSoup(page, 'html.parser').get_text()
                if len(page_text) > max_length:
                    # Further split this page by sentences or paragraphs
                    chunks = split_large_element(page)
                    final_pages.extend(chunks)
                else:
                    final_pages.append(page)
            
            standardized_pages.extend(final_pages)
            current_episodes.append(final_pages)
    
    cover_data = extract_cover(book_path)
    return jsonify({
        'pages': standardized_pages, 
        'cover': cover_data, 
        'episodes': current_episodes
    })

def split_large_element(html_content):
    """Split a large HTML element into smaller chunks of 800-1000 characters."""
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text()
    
    # If it's not that much over, just return it
    if len(text) < 1200:
        return [html_content]
    
    # Try to find natural breaking points (paragraphs, sentences)
    paragraphs = re.split(r'(<p>|<div>|<br\s*\/?>)', html_content, flags=re.IGNORECASE)
    
    chunks = []
    current_chunk = ''
    current_text_length = 0
    
    for p in paragraphs:
        p_text = BeautifulSoup(p, 'html.parser').get_text()
        
        if current_text_length + len(p_text) > 1000 and current_text_length > 800:
            chunks.append(current_chunk)
            current_chunk = p
            current_text_length = len(p_text)
        else:
            current_chunk += p
            current_text_length += len(p_text)
    
    # Add the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    # If we still have chunks that are too large, split by sentences
    final_chunks = []
    for chunk in chunks:
        chunk_text = BeautifulSoup(chunk, 'html.parser').get_text()
        
        if len(chunk_text) > 1000:
            # Split by sentences, trying to keep HTML intact
            sentence_chunks = split_by_sentences(chunk)
            final_chunks.extend(sentence_chunks)
        else:
            final_chunks.append(chunk)
    
    return final_chunks

def split_by_sentences(html_content):
    """Split HTML content by sentences, attempting to keep HTML structure."""
    # This is a simplified approach - for production, you'd need more sophisticated parsing
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text()
    
    # Split text into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = ''
    current_text = ''
    
    for sentence in sentences:
        if len(current_text + sentence) > 1000 and len(current_text) > 800:
            chunks.append(current_chunk)
            # Find this sentence in the HTML and start a new chunk
            sentence_pos = html_content.find(sentence, len(current_chunk))
            if sentence_pos != -1:
                current_chunk = html_content[sentence_pos:]
                current_text = sentence
            else:
                # Fallback if we can't find the exact position
                current_chunk = f"<p>{sentence}</p>"
                current_text = sentence
        else:
            if not current_chunk:
                sentence_pos = html_content.find(sentence)
                if sentence_pos != -1:
                    current_chunk = html_content[:sentence_pos + len(sentence)]
                else:
                    current_chunk = f"<p>{sentence}</p>"
            current_text += sentence
    
    # Add the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks

def load_bookmarks():
    if os.path.exists(BOOKMARKS_FILE):
        with open(BOOKMARKS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_bookmarks(bookmarks):
    with open(BOOKMARKS_FILE, 'w') as f:
        json.dump(bookmarks, f, indent=4)

@app.route('/bookmark', methods=['POST'])
def add_bookmark():
    data = request.json
    book = data.get('book')
    page = data.get('page')
    word = data.get('word')
    occurrence = data.get('occurrence')  # New field: which occurrence in the page

    if not book or page is None or not word or occurrence is None:
        return jsonify({'success': False, 'message': 'Invalid data'}), 400

    bookmarks = load_bookmarks()
    if book not in bookmarks:
        bookmarks[book] = []
    bookmarks[book].append({
        'page': page,
        'word': word,
        'occurrence': occurrence,
        'timestamp': datetime.now().isoformat()
    })
    save_bookmarks(bookmarks)
    return jsonify({'success': True, 'bookmark': {'page': page, 'word': word, 'occurrence': occurrence}})

@app.route('/api/bookmarks')
def api_bookmarks():
    if not check_auth('books'):
        abort(403)
    book = request.args.get('book')
    page = request.args.get('page')
    bookmarks = load_bookmarks()
    if book in bookmarks:
        if page:
            bookmarks_for_page = [bm for bm in bookmarks[book] if str(bm.get('page')) == str(page)]
            return jsonify(bookmarks_for_page)
        else:
            # Return all bookmarks for the specified book
            return jsonify(bookmarks[book])
    return jsonify([])

@app.route('/api/bookmarks/last')
def get_last_bookmark():
    book_id = request.args.get('book')
    bookmarks = load_bookmarks()
    if book_id in bookmarks and bookmarks[book_id]:
        try:
            # Find the highest page number that has a bookmark.
            last_page = max(bm['page'] for bm in bookmarks[book_id])
            return jsonify({"page": last_page})
        except Exception as e:
            print("Error computing last bookmark:", e)
            return jsonify({"page": 0})
    return jsonify({"page": 0})

@app.route('/bookmark/delete', methods=['POST'])
def delete_bookmark():
    data = request.json
    book = data.get('book')
    page = data.get('page')
    word = data.get('word')
    occurrence = data.get('occurrence')
    if not book or page is None or not word or occurrence is None:
        return jsonify({'success': False, 'message': 'Invalid data'}), 400

    bookmarks = load_bookmarks()
    if book in bookmarks:
        original_len = len(bookmarks[book])
        bookmarks[book] = [bm for bm in bookmarks[book]
                           if not (bm['page'] == page and bm['word'] == word and bm['occurrence'] == occurrence)]
        if len(bookmarks[book]) < original_len:
            save_bookmarks(bookmarks)
            return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Bookmark not found'}), 404



def extract_cover(epub_path):
    try:
        book = epub.read_epub(epub_path)
        # Try to find the cover image
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_COVER or \
               item.get_type() == ebooklib.ITEM_IMAGE:
                # Convert image data to base64 for displaying in HTML
                image_data = base64.b64encode(item.get_content()).decode('utf-8')
                return f"data:image/jpeg;base64,{image_data}"
        return None
    except Exception as e:
        print(f"Error processing EPUB: {e} - File: {epub_path}")
        return None
    
def has_books():
    return any(f.endswith('.epub') for f in os.listdir(BOOK_DIR))
@app.route('/books')
def books():
    if not check_auth('books'):
        return redirect(url_for('section_login', section='books'))
    books = []
    finished_books = load_finished_books()
    
    for filename in os.listdir(BOOK_DIR):
        if allowed_file(filename):
            book_path = os.path.join(BOOK_DIR, filename)
            cover_data = extract_cover(book_path)
            title = filename[:-5]  # remove .epub
            books.append({
                "title": title,
                "cover": cover_data,
                "filename": filename,
                "finished": title in finished_books,
                "finished_date": finished_books.get(title, None)
            })
    
    # Sort books: unfinished first, then finished
    books.sort(key=lambda x: (x['finished'], x['title'].lower()))
    
    return render_template('books.html', 
                         books=books,
                         **get_back_context(show_back=True))

@app.route('/toggle_finished/<path:book_title>', methods=['POST'])
def toggle_finished(book_title):
    finished_books = load_finished_books()
    
    if book_title in finished_books:
        del finished_books[book_title]
        is_finished = False
        finished_date = None
    else:
        finished_books[book_title] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_finished = True
        finished_date = finished_books[book_title]
    
    save_finished_books(finished_books)
    
    return jsonify({
        "success": True,
        "is_finished": is_finished,
        "finished_date": finished_date
    })

@app.route('/books/<path:filename>')
def serve_book(filename):
    if not check_auth('books'):
        abort(403)
    if not allowed_file(filename):
        abort(404)
    return send_from_directory(BOOK_DIR, filename)





#### Manifest ####

@app.route('/manifest.json')
def manifest():
    # Get the "book" query parameter from the URL. For example:
    # /manifest.json?book=MyBook.epub
    book_filename = request.args.get('book')
    if book_filename and allowed_file(book_filename):
        book_path = os.path.join(BOOK_DIR, book_filename)
        cover_data = extract_cover(book_path)
        # If cover_data is empty, fall back to a default
        if not cover_data:
            cover_data = url_for('static', filename='default-icon.png', _external=True)
    else:
        cover_data = url_for('static', filename='default-icon.png', _external=True)

    manifest_data = {
        "name": "Book Reader",
        "short_name": "Reader",
        "start_url": url_for('read_book', filename=book_filename, _external=True) if book_filename else url_for('index', _external=True),
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#000000",
        "icons": [
            {
                "src": cover_data,
                "sizes": "512x512",
                "type": "image/png"  # Adjust if your cover is JPEG ("image/jpeg")
            }
        ]
    }
    response = jsonify(manifest_data)
    # Prevent caching so that updated icons show immediately.
    response.headers['Cache-Control'] = 'no-cache'
    return response

@app.route('/delete_song', methods=['POST'])
def delete_song():
    data = request.get_json()
    song = data.get('song')
    if not song:
        return jsonify({'success': False, 'message': 'No song provided'})
    # Determine full file path using the song path (e.g., "Downloads/song.mp3" or "Folder/song.mp3")
    parts = song.split('/', 1)
    if len(parts) == 2:
        folder, filename = parts
        full_path = os.path.join(MUSIC_DIR, folder, filename)
    else:
        full_path = os.path.join(MUSIC_DIR, song)
    full_path = os.path.abspath(full_path)
    # Verify the file is inside MUSIC_DIR
    if not full_path.startswith(os.path.abspath(MUSIC_DIR)):
        return jsonify({'success': False, 'message': 'Invalid path'}), 400
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    else:
        return jsonify({'success': False, 'message': 'Song not found'}), 404

@app.route('/uploader')
def uploader():
    return render_template('uploader.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'})
    
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return jsonify({'success': False, 'message': 'No files selected'})
    
    folder = request.form.get('folder', '')
    file_type = request.form.get('type', 'media')
    
    # Determine the target directory based on file type
    if file_type == 'book':
        target_dir = BOOK_DIR
        allowed_extensions = ALLOWED_EXTENSIONS
    else:  # media type
        if folder:
            target_dir = os.path.join(MEDIA_DIR, folder)
        else:
            target_dir = MEDIA_DIR
        allowed_extensions = ALLOWED_PHOTO_EXTENSIONS.union(ALLOWED_VIDEO_EXTENSIONS)
    
    # Create directory if it doesn't exist
    os.makedirs(target_dir, exist_ok=True)
    
    results = []
    for file in files:
        # Determine file extension and check if it's allowed
        extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if extension not in allowed_extensions:
            results.append({
                'filename': file.filename,
                'success': False,
                'message': f'File type not allowed. Allowed types: {", ".join(allowed_extensions)}'
            })
            continue
        
        try:
            # Save the file
            file_path = os.path.join(target_dir, file.filename)
            file.save(file_path)
            results.append({
                'filename': file.filename,
                'success': True,
                'message': f'Uploaded successfully as {file_type}'
            })
        except Exception as e:
            results.append({
                'filename': file.filename,
                'success': False,
                'message': f'Error: {str(e)}'
            })
    
    # Determine overall success
    all_success = all(result['success'] for result in results)
    
    return jsonify({
        'success': all_success,
        'results': results,
        'message': f'Uploaded {sum(1 for r in results if r["success"])} of {len(results)} files successfully'
    })

@app.route('/api/folders')
def get_media_folders():
    folders = []
    
    # Get all folders in the media directory
    for root, dirs, _ in os.walk(MEDIA_DIR):
        for dir_name in dirs:
            # Get the relative path from MEDIA_DIR
            rel_path = os.path.relpath(os.path.join(root, dir_name), MEDIA_DIR)
            folders.append(rel_path)
    
    return jsonify(folders)

@app.route('/reset_shuffle', methods=['POST'])
def reset_shuffle():
    data = request.get_json()
    folder_name = data.get('folder', 'Downloads')
    
    try:
        # Build the path to the shuffle history file
        json_path = os.path.join(SHUFFLED_DIR, f"{folder_name}.json")
        # json_path = os.path.join(SHUFFLED_DIR, f"Heb.json")
        
        # Check if the file exists
        if os.path.exists(json_path):
            # Delete the file
            os.remove(json_path)
            return jsonify({
                'success': True,
                'message': f'Shuffle history for {folder_name} has been reset'
            })
        else:
            # File doesn't exist, but that's okay - it's already "reset"
            return jsonify({
                'success': True,
                'message': f'No shuffle history found for {folder_name}'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error resetting shuffle history: {str(e)}'
        }), 500

def get_back_context(show_back=True, back_url='/'):
    """Helper function to provide consistent back button context"""
    return {
        'show_back': show_back,
        'back_url': back_url
    }

@app.route('/notebook/search')
def search_notebook():
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify([])
    
    pages = load_notebook_pages()
    matching_pages = []
    
    for page in pages:
        # Search in both name and content
        if (query in page['name'].lower() or 
            query in page.get('content', '').lower()):
            matching_pages.append(page)
    
    return jsonify(matching_pages)

def check_ffmpeg():
    """Check if ffmpeg is available in the system PATH"""
    return shutil.which('ffmpeg') is not None

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    print("Received transcription request")
    if not check_ffmpeg():
        print("FFmpeg not found in system PATH")
        return jsonify({
            'success': False,
            'message': 'FFmpeg is not installed. Please install FFmpeg to use the dictation feature.'
        })

    if 'audio' not in request.files:
        print("No audio file in request")
        return jsonify({'success': False, 'message': 'No audio file provided'})
    
    audio_file = request.files['audio']
    if audio_file.filename == '':
        print("Empty filename")
        return jsonify({'success': False, 'message': 'No selected file'})
    
    # Read the file content to check if it's empty
    file_content = audio_file.read()
    if not file_content:
        print("Empty audio file")
        return jsonify({'success': False, 'message': 'The audio file is empty. Please try recording again.'})
    
    # Reset file pointer for later use
    audio_file.seek(0)
    
    # Get audio file size
    file_size = len(file_content)
    print(f"Received audio file: {audio_file.filename}, size: {file_size} bytes")
    
    # Skip small files that are likely just background noise
    if file_size < 10000:  # Less than 10KB
        print("Audio file too small, likely just background noise")
        return jsonify({
            'success': True,
            'text': '',  # Return empty text
            'message': 'No speech detected'
        })
    
    input_file = None
    output_file = None
    
    try:
        # Create temporary files for input and output
        input_file = tempfile.NamedTemporaryFile(delete=False, suffix='.webm')
        output_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        
        # Close the files so they can be used by ffmpeg
        input_file.close()
        output_file.close()
        
        print(f"Created temporary files: {input_file.name}, {output_file.name}")
        
        # Save the uploaded audio
        audio_file.save(input_file.name)
        
        # Verify the file was saved and has content
        if not os.path.exists(input_file.name) or os.path.getsize(input_file.name) == 0:
            print("Error: Saved file is empty or does not exist")
            return jsonify({'success': False, 'message': 'Error saving audio file. Please try again.'})
            
        print("Saved uploaded audio file")
        
        # Convert WebM to WAV using ffmpeg
        try:
            print("Running FFmpeg conversion...")
            # Add -y flag to overwrite output file if it exists
            result = subprocess.run([
                'ffmpeg', '-y', '-i', input_file.name,
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                output_file.name
            ], check=True, capture_output=True, text=True)
            print("FFmpeg conversion successful")
            
            # Verify the output file exists and has content
            if not os.path.exists(output_file.name) or os.path.getsize(output_file.name) == 0:
                print("Error: FFmpeg output file is empty or does not exist")
                return jsonify({'success': False, 'message': 'Error converting audio. Please try again.'})
            
            # Check audio level to ensure there's actual speech (optional)
            try:
                # Check audio amplitude with ffmpeg
                level_check = subprocess.run([
                    'ffmpeg', '-i', output_file.name, 
                    '-af', 'volumedetect', 
                    '-f', 'null', 
                    'NUL'  # Use /dev/null on Unix systems
                ], capture_output=True, text=True)
                
                # Look for mean volume in the output
                mean_volume_match = re.search(r'mean_volume: ([-\d.]+) dB', level_check.stderr)
                if mean_volume_match:
                    mean_volume = float(mean_volume_match.group(1))
                    print(f"Mean audio volume: {mean_volume} dB")
                    
                    # If volume is very low, likely no speech
                    if mean_volume < -40:  # Typical threshold for silence
                        print("Audio contains no speech (volume too low)")
                        return jsonify({
                            'success': True,
                            'text': '',
                            'message': 'No speech detected'
                        })
                
            except Exception as e:
                print(f"Warning: Could not check audio level: {e}")
                # Continue anyway since this is just an optional check
                
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error: {e.stderr}")
            return jsonify({
                'success': False,
                'message': f'Error converting audio: {e.stderr}'
            })
        
        # Initialize the Whisper model
        print("Initializing Whisper model...")
        model = WhisperModel("base", device="cpu", compute_type="int8")
        print("Whisper model initialized")
        
        # Transcribe the audio
        print("Starting transcription...")
        segments, info = model.transcribe(output_file.name, beam_size=5)
        
        # Get the transcribed text
        text = " ".join([segment.text for segment in segments])
        print(f"Transcription complete: {text}")
        
        # If text is extremely short or just punctuation, consider it as silence
        if len(text.strip()) <= 2 or text.strip() in ['', '.', '?', '!']:
            return jsonify({
                'success': True,
                'text': '',
                'message': 'No meaningful speech detected'
            })
        
        return jsonify({
            'success': True,
            'text': text.strip()
        })
        
    except Exception as e:
        print(f"Error during transcription: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error during transcription: {str(e)}'
        })
    finally:
        # Clean up temporary files
        if input_file and os.path.exists(input_file.name):
            try:
                os.unlink(input_file.name)
            except Exception as e:
                print(f"Error deleting input file: {e}")
        if output_file and os.path.exists(output_file.name):
            try:
                os.unlink(output_file.name)
            except Exception as e:
                print(f"Error deleting output file: {e}")

def generate_self_signed_cert():
    """Generate self-signed SSL certificate if it doesn't exist"""
    cert_dir = os.path.join(current_directory, 'cert')
    os.makedirs(cert_dir, exist_ok=True)
    
    cert_path = os.path.join(cert_dir, 'cert.pem')
    key_path = os.path.join(cert_dir, 'key.pem')
    
    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        # Generate key
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 2048)
        
        # Generate certificate
        cert = crypto.X509()
        cert.get_subject().C = "US"
        cert.get_subject().ST = "State"
        cert.get_subject().L = "City"
        cert.get_subject().O = "Organization"
        cert.get_subject().OU = "Organizational Unit"
        cert.get_subject().CN = "localhost"
        
        # Add Subject Alternative Names
        san_extension = crypto.X509Extension(
            b'subjectAltName',
            False,
            b'DNS:localhost,IP:127.0.0.1,IP:0.0.0.0'
        )
        cert.add_extensions([san_extension])
        
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365*24*60*60)  # Valid for one year
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, 'sha256')
        
        # Save certificate and private key
        with open(cert_path, "wb") as f:
            f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        with open(key_path, "wb") as f:
            f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
    
    return cert_path, key_path

def load_tasks():
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tasks(tasks):
    with open(TASKS_FILE, 'w') as f:
        json.dump(tasks, f, indent=4)

@app.route('/calendar')
def calendar():
    if not check_auth('calendar'):
        return redirect(url_for('section_login', section='calendar'))
    return render_template('calendar.html', **get_back_context())

@app.route('/api/tasks')
def get_tasks():
    if not check_auth('calendar'):
        abort(403)
    return jsonify(load_tasks())

@app.route('/api/tasks', methods=['POST'])
def add_task():
    if not check_auth('calendar'):
        abort(403)
    data = request.json
    date = data.get('date')
    task = data.get('task')
    
    if not date or not task:
        return jsonify({'success': False, 'message': 'Invalid data'})
    
    tasks = load_tasks()
    if date not in tasks:
        tasks[date] = []
    tasks[date].append(task)
    save_tasks(tasks)
    
    return jsonify({'success': True})

@app.route('/api/tasks/toggle', methods=['POST'])
def toggle_task():
    data = request.json
    date = data.get('date')
    task_id = data.get('taskId')
    
    if not date or task_id is None:
        return jsonify({'success': False, 'message': 'Invalid data'})
    
    tasks = load_tasks()
    if date in tasks and 0 <= task_id < len(tasks[date]):
        tasks[date][task_id]['completed'] = not tasks[date][task_id]['completed']
        save_tasks(tasks)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Task not found'})

@app.route('/api/tasks/delete', methods=['POST'])
def delete_task():
    data = request.json
    date = data.get('date')
    task_id = data.get('taskId')
    
    if not date or task_id is None:
        return jsonify({'success': False, 'message': 'Invalid data'})
    
    tasks = load_tasks()
    if date in tasks and 0 <= task_id < len(tasks[date]):
        tasks[date].pop(task_id)
        if not tasks[date]:  # If no tasks left for this date, remove the date entry
            del tasks[date]
        save_tasks(tasks)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Task not found'})

@app.route('/locked-media/<path:filename>')
def serve_locked_media(filename):
    if not check_auth('private'):
        return redirect(url_for('section_login', section='private'))
    
    # Use LOCKED_DIR directly instead of app.config['UPLOAD_FOLDER']
    return send_from_directory(LOCKED_DIR, filename)

if __name__ == '__main__':
    print("Starting server...")
    os.makedirs(BOOK_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)
    os.makedirs(LOCKED_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(SHUFFLED_DIR, exist_ok=True)
    os.makedirs(NOTEBOOK_DIR, exist_ok=True)
    
    # Generate SSL certificates
    cert_path, key_path = generate_self_signed_cert()
    
    # Set the host to 0.0.0.0 to make the server accessible from other devices on the network
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    
    # Start HTTPS server in a separate thread
    def run_https():
        app.run(host='0.0.0.0', port=3000, ssl_context=context)
    
    # Start HTTP server in a separate thread
    def run_http():
        app.run(host='0.0.0.0', port=3001)
    
    # Start both servers
    https_thread = threading.Thread(target=run_https)
    http_thread = threading.Thread(target=run_http)
    
    https_thread.start()
    http_thread.start()
    
    print("Server started on:")
    print("  - HTTPS: https://localhost:3000")
    print("  - HTTP: http://localhost:3001")
    print("  - HTTPS: https://0.0.0.0:3000")
    print("  - HTTP: http://0.0.0.0:3001")
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")

