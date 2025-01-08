import os
import subprocess
from mutagen.mp3 import MP3

def split_mp3(input_file_path: str, split_point_minutes: int) -> tuple[str, str]:
    """
    Splits an MP3 file into two parts at the specified time point using ffmpeg.
    
    Args:
        input_file_path (str): Path to the input MP3 file
        split_point_minutes (int): Point at which to split the file (in minutes)
    
    Returns:
        tuple[str, str]: Paths to the two output files
    """
    # Validate input file exists
    if not os.path.exists(input_file_path):
        raise FileNotFoundError(f"Input file not found: {input_file_path}")
    
    # Get audio file duration
    audio = MP3(input_file_path)
    total_duration = audio.info.length  # duration in seconds
    split_point_seconds = split_point_minutes * 60
    
    # Validate split point
    if split_point_seconds <= 0:
        raise ValueError("Split point must be positive")
    if split_point_seconds >= total_duration:
        raise ValueError(f"Split point ({split_point_seconds}s) exceeds file duration ({total_duration}s)")
    
    # Generate output file paths
    file_name = os.path.splitext(input_file_path)[0]
    first_output = f"{file_name}_part1.mp3"
    second_output = f"{file_name}_part2.mp3"
    
    try:
        # Split first part
        subprocess.run([
            'ffmpeg', '-i', input_file_path,
            '-t', str(split_point_seconds),
            '-acodec', 'copy',
            '-y',  # Overwrite output files without asking
            first_output
        ], check=True, capture_output=True)
        
        # Split second part
        subprocess.run([
            'ffmpeg', '-i', input_file_path,
            '-ss', str(split_point_seconds),
            '-acodec', 'copy',
            '-y',  # Overwrite output files without asking
            second_output
        ], check=True, capture_output=True)
        
        return first_output, second_output
        
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error splitting file: {e.stderr.decode()}")

if __name__ == "__main__":
    try:
        input_file = "selfLove.mp3"  # Replace with your file name
        split_time = 2  # 2 hours in minutes
        
        part1, part2 = split_mp3(input_file, split_time)
        print(f"Successfully split file into:\n{part1}\n{part2}")
        
    except Exception as e:
        print(f"Error: {str(e)}")