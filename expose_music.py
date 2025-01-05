import os
from flask import Flask, send_from_directory, jsonify, render_template

app = Flask(__name__)

# Set the directory where your music is stored
MUSIC_DIR = "Music"

@app.route('/')
def index():
    # List all files in the MUSIC_DIR
    music_files = []
    for root, dirs, files in os.walk(MUSIC_DIR):
        for file in files:
            if file.lower().endswith(('.mp3', '.wav', '.flac', '.aac')):
                music_files.append(file)
    return render_template('index.html', music_files=music_files)

@app.route('/music/<filename>')
def stream_music(filename):
    # Serve the music file
    return send_from_directory(MUSIC_DIR, filename)

if __name__ == '__main__':
    # Set the host to 0.0.0.0 to make the server accessible from other devices on the network
    app.run(host='0.0.0.0', port=5000)
