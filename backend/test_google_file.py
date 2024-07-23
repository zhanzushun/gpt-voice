import os
from google.cloud import speech_v1
import io

def transcribe_file(speech_file):
    """Transcribe the given audio file."""
    client = speech_v1.SpeechClient()

    with io.open(speech_file, "rb") as audio_file:
        content = audio_file.read()

    audio = speech_v1.RecognitionAudio(content=content)
    config = speech_v1.RecognitionConfig(
        encoding=speech_v1.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=16000,
        language_code="zh-CN",
        alternative_language_codes=["en-US"],
        enable_automatic_punctuation=True,
        model="default",
        use_enhanced=True
    )

    response = client.recognize(config=config, audio=audio)

    transcriptions = []
    for result in response.results:
        transcriptions.append(result.alternatives[0].transcript)
    
    return " ".join(transcriptions)

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
                    output_file.write(transcription)
                print(f"Transcription saved to: {output_filename}")
            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")

# 使用示例
directory_path = "static"
process_directory(directory_path)


# export GOOGLE_APPLICATION_CREDENTIALS='zhanzushun-8dd339d73749.json'