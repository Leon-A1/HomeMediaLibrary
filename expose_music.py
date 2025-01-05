import os
from flask import Flask, send_from_directory, jsonify, render_template

app = Flask(__name__,template_folder="C:/Users/leona/Desktop/Code 2025/YouTubeMusicDownloader/templates")

# Set the directory where your music is stored
MUSIC_DIR = "C:/Users/leona/Desktop/Code 2025/YouTubeMusicDownloader/Music"

@app.route('/')
def index():
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
    
    return render_template('index.html', 
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
    
if __name__ == '__main__':
    # Set the host to 0.0.0.0 to make the server accessible from other devices on the network
    app.run(host='0.0.0.0', port=5000)
