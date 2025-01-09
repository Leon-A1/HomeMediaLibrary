import os
import ffmpeg

def process_media_in_directory(directory):
    # Define the file extensions for videos and images
    video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv')
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')

    # Iterate over each file in the directory
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            # Check if the file is a video
            if filename.lower().endswith(video_extensions):
                # Probe the video file to get its metadata
                probe = ffmpeg.probe(file_path)
                # Extract width and height from the video stream
                video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
                if video_stream:
                    width = int(video_stream['width'])
                    height = int(video_stream['height'])
                    print(f'Processing video: {filename}, Width: {width}, Height: {height}')
                    # Check if the video is vertical
                    if height > width:
                        # Rotate the video to horizontal
                        output_path = os.path.join(directory, f'rotated_{filename}')
                        (
                            ffmpeg
                            .input(file_path)
                            .filter('transpose', 2)  # Rotate 90 degrees counterclockwise
                            .output(output_path)
                            .run()
                        )
                        print(f'Rotated video saved as: {output_path}')
            # Check if the file is an image
            elif filename.lower().endswith(image_extensions):
                # Use ffmpeg to get image dimensions
                probe = ffmpeg.probe(file_path)
                image_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
                if image_stream:
                    width = int(image_stream['width'])
                    height = int(image_stream['height'])
                    print(f'Processing image: {filename}, Width: {width}, Height: {height}')
                    # Check if the image is vertical
                    if height > width:
                        # Rotate the image to horizontal
                        output_path = os.path.join(directory, f'rotated_{filename}')
                        (
                            ffmpeg
                            .input(file_path)
                            .filter('transpose', 2)  # Rotate 90 degrees counterclockwise
                            .output(output_path)
                            .run()
                        )
                        print(f'Rotated image saved as: {output_path}')
        except ffmpeg.Error as e:
            print(f'Error processing {file_path}: {e.stderr.decode()}')

# Example usage
process_media_in_directory('C:/Users/leona/Desktop/Code 2025/HomeMediaLibrary/Photos&Videos/testing_videos')
