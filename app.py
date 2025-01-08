import os
from flask import Flask, render_template, send_from_directory, abort, jsonify, request, session, redirect, url_for
import ebooklib
from ebooklib import epub
from PIL import Image
import io
import base64
import json
from datetime import datetime
import os

current_directory = os.getcwd()

app = Flask(__name__,template_folder= current_directory+"/templates")

# Set the directory where your music is stored
MUSIC_DIR = current_directory+"/Music"
MEDIA_DIR = current_directory+"/Photos&Videos"

# Configuration
BOOK_DIR = current_directory+"/Books"  # Directory where your EPUB files are stored
ALLOWED_EXTENSIONS = {'epub'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
ALLOWED_PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}
FINISHED_BOOKS_FILE = current_directory+"/finished_books.json"
LOCKED_DIR = current_directory+"/Locked"
PASSWORD = "123"  # In a real application, use a secure hashed password

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

def check_auth():
    return session.get('authenticated', False)

@app.route('/')
def index():

    return render_template('index.html')

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
    photos = []
    for filename in os.listdir(MEDIA_DIR):
        if filename.lower().endswith(tuple(ALLOWED_PHOTO_EXTENSIONS)):
            photos.append(filename)
    return render_template('photos.html', photos=photos)

@app.route('/videos')
def videos():
    videos = []
    for filename in os.listdir(MEDIA_DIR):
        if filename.lower().endswith(tuple(ALLOWED_VIDEO_EXTENSIONS)):
            videos.append(filename)
    return render_template('videos.html', videos=videos)

@app.route('/media/<path:filename>')
def serve_media(filename):
    return send_from_directory(MEDIA_DIR, filename)

@app.route('/locked')
def locked():
    if not check_auth():
        return render_template('login.html')
    
    photos = []
    videos = []
    for filename in os.listdir(LOCKED_DIR):
        if filename.lower().endswith(tuple(ALLOWED_PHOTO_EXTENSIONS)):
            photos.append(filename)
        elif filename.lower().endswith(tuple(ALLOWED_VIDEO_EXTENSIONS)):
            videos.append(filename)
    
    return render_template('locked.html', photos=photos, videos=videos)

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

# Add a secret key for session management
app.secret_key = 'your-secret-key-here'  # Change this to a secure random key in production

if __name__ == '__main__':
    os.makedirs(BOOK_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)
    os.makedirs(LOCKED_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    # Set the host to 0.0.0.0 to make the server accessible from other devices on the network
    app.run(host='0.0.0.0', port=5000)
