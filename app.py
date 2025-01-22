import os
from flask import Flask, render_template, send_from_directory, abort, jsonify, request, session, redirect, url_for
import ebooklib
from ebooklib import epub
from PIL import Image
import io
import base64
import json
from datetime import datetime
from PIL.ExifTags import TAGS
import time

current_directory = os.path.dirname(os.path.realpath(__file__)).replace("\\","/")

app = Flask(__name__,template_folder= current_directory+"/templates")

NOTEBOOK_DIR = current_directory + "/Notebook"
MUSIC_DIR = current_directory+"/Music"
MEDIA_DIR = current_directory+"/Photos&Videos"
BOOK_DIR = current_directory+"/Books"  
LOCKED_DIR = current_directory+"/Locked"
SHUFFLED_DIR = current_directory + "/shuffled"

# Configuration
ALLOWED_EXTENSIONS = {'epub'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
ALLOWED_PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}
FINISHED_BOOKS_FILE = current_directory+"/finished_books.json"
PASSWORD = "123"  # Locked will be hidden until a password is set


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


def has_books():
    return any(f.endswith('.epub') for f in os.listdir(BOOK_DIR))

def has_music():
    # Check root music directory and Downloads folder
    downloads_path = os.path.join(MUSIC_DIR, 'Downloads')
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


def check_auth():
    return session.get('authenticated', False)
    
def has_protected_content():
    return bool(PASSWORD.strip()) 

    
@app.route('/')
def index():
    return render_template('index.html',
                         has_books=has_books(),
                         has_music=has_music(),
                         has_photos=has_photos(),
                         has_videos=has_videos(),
                         has_protected=has_protected_content())

@app.route('/books')
def books():
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
    
    return render_template('books.html', books=books)

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
    if not allowed_file(filename):
        abort(404)
    return send_from_directory(BOOK_DIR, filename)

@app.route('/music')
def music():
    # Get folders and their file counts
    # Use Downloads folder as root folder
    folders = ['Downloads']  # Empty string represents root Music folder
    folder_counts = {}
    downloads_folder_path = MUSIC_DIR + '/Downloads'
    # Count files in root folder
    root_files = [f for f in os.listdir(downloads_folder_path) 
                  if os.path.isfile(os.path.join(downloads_folder_path, f)) 
                  and f.lower().endswith(('.mp3', '.wav', '.flac', '.aac'))]
    folder_counts['Downloads'] = len(root_files)
    print(folder_counts['Downloads'])
    # Count files in subfolders
    for item in os.listdir(MUSIC_DIR):
        if(item == "Downloads"):
            continue
        if os.path.isdir(os.path.join(MUSIC_DIR, item)):
            folders.append(item)
            folder_path = os.path.join(MUSIC_DIR, item)
            files = [f for f in os.listdir(folder_path) 
                    if os.path.isfile(os.path.join(folder_path, f)) 
                    and f.lower().endswith(('.mp3', '.wav', '.flac', '.aac'))]
            folder_counts[item] = len(files)
    
    return render_template('music.html', 
                         music_files=root_files, 
                         folders=folders, 
                         folder_counts=folder_counts, 
                         current_folder='')

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
    # Split the path into folder and filename
    parts = os.path.split(filename)
    if len(parts) > 1:
        folder, file = parts
        return send_from_directory(os.path.join(MUSIC_DIR, folder), file)
    return send_from_directory(MUSIC_DIR, filename)

@app.route('/photos')
def photos():
    return render_template('photos.html')

@app.route('/api/photos')
def get_photos():
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
    return render_template('videos.html')

@app.route('/api/videos')
def get_videos():
    page = int(request.args.get('page', 1))
    path = request.args.get('path', '')
    per_page = 5

    # Get folders and files using the video-specific function
    folders, videos = scan_video_contents(MEDIA_DIR, path)
    
    # Sort folders and videos
    folders.sort(key=lambda x: x['name'].lower())
    videos.sort()

    # Paginate videos
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_videos = videos[start_idx:end_idx]

    # Fix hasMore calculation
    has_more = end_idx < len(videos)

    return jsonify({
        'folders': folders if page == 1 else [],  # Only send folders on first page
        'items': paginated_videos,
        'hasMore': has_more,
        'total': len(videos)
    })

@app.route('/media/<path:filename>')
def serve_media(filename):
    parts = filename.split('/')
    directory = os.path.join(MEDIA_DIR, *parts[:-1])
    return send_from_directory(directory, parts[-1])

@app.route('/locked')
def locked():
    if not check_auth():
        return render_template('login.html')
    return render_template('locked.html')

@app.route('/api/locked')
def get_locked():
    if not check_auth():
        abort(403)
    page = int(request.args.get('page', 1))
    per_page = 5
    media_type = request.args.get('type', 'all')
    
    if media_type == 'photos':
        items, total = get_paginated_files(LOCKED_DIR, ALLOWED_PHOTO_EXTENSIONS, page, per_page)
    elif media_type == 'videos':
        items, total = get_paginated_files(LOCKED_DIR, ALLOWED_VIDEO_EXTENSIONS, page, per_page)
    else:
        photos, photos_total = get_paginated_files(LOCKED_DIR, ALLOWED_PHOTO_EXTENSIONS, page, per_page)
        videos, videos_total = get_paginated_files(LOCKED_DIR, ALLOWED_VIDEO_EXTENSIONS, page, per_page)
        items = photos + videos
        total = photos_total + videos_total
    
    start_idx = (page - 1) * per_page
    has_more = (start_idx + len(items)) < total
    
    return jsonify({
        'items': items,
        'hasMore': has_more,
        'total': total
    })

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('password') == PASSWORD:
        session['authenticated'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Invalid password'})

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('locked'))

@app.route('/locked-media/<path:filename>')
def serve_locked_media(filename):
    if not check_auth():
        abort(403)
    return send_from_directory(LOCKED_DIR, filename)

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
    return pages




@app.route('/notebook')
def notebook():
    if not check_auth():
        return render_template('login.html')
    pages = load_notebook_pages()
    pages.sort(key=lambda x: x['createdAt'], reverse=True)
    return render_template('notebook.html', pages=pages)

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
    filename = f"{name}.json"
    filepath = os.path.join(NOTEBOOK_DIR, filename)

    if not os.path.exists(filepath):
        abort(404)

    with open(filepath, 'r') as f:
        page = json.load(f)

    return render_template('notebook_page.html', page=page)

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

if __name__ == '__main__':
    print("Starting server...")
    os.makedirs(BOOK_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)
    os.makedirs(LOCKED_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(SHUFFLED_DIR, exist_ok=True)
    os.makedirs(NOTEBOOK_DIR, exist_ok=True)
    # Set the host to 0.0.0.0 to make the server accessible from other devices on the network
    app.run(host='0.0.0.0', port=5000)
