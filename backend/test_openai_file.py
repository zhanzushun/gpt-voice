import requests
import logging
import os

import config

def transcribe_file(local_file_path):
    headers = {
        'Authorization': f'Bearer sk-{config.API_KEY}',
    }
    data = {
        'model': 'whisper-1',
        'temperature': '0',
        'prompt': '我说简体中文，I also speek English. 音频中可能的文本是”what food do you like“',
    }
    files = {
        'file': open(local_file_path, 'rb'),
    }
    response = requests.post('https://api.openai.com/v1/audio/transcriptions', headers=headers, data=data, files=files)
    dict1 = response.json()
    logging.info(f'response={dict1}')
    if response.status_code == 200:
        return dict1
    else:
        return dict1['error']['message']
    
def process_directory(directory_path):
    """Process all MP3 files in the given directory."""
    for filename in os.listdir(directory_path):
        if filename.endswith(".mp3"):
            file_path = os.path.join(directory_path, filename)
            print(f"Processing file: {filename}")
            try:
                transcription = transcribe_file(file_path)
                output_filename = os.path.splitext(filename)[0] + ".txt"
                output_path = os.path.join(directory_path, output_filename)
                with open(output_path, "w", encoding="utf-8") as output_file:
                    output_file.write(f'{transcription}')
                print(f"Transcription saved to: {output_filename}")
            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")

# 使用示例
directory_path = "temp"
#process_directory(directory_path)
print(transcribe_file('static/18616699733_20240719_161019_373.mp3'))