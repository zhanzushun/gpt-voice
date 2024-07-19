import os
import time
import random
from google.cloud import speech
from google.oauth2 import service_account

# 设置Google Cloud凭证路径
credentials = service_account.Credentials.from_service_account_file('zhanzushun-8dd339d73749.json')

# 音频文件路径
audio_file = 'recorded_audio.wav'

class MyCallback:
    def on_started(self):
        print('识别开始')

    def on_result_changed(self, message):
        print('中间识别结果: {}'.format(message))

    def on_completed(self, message):
        print('识别完成: {}'.format(message))

    def on_error(self, message):
        print('识别错误: {}'.format(message))

    def on_close(self):
        print('识别通道关闭')

def process(credentials):
    callback = MyCallback()
    client = speech.SpeechClient(credentials=credentials)

    with open(audio_file, 'rb') as f:
        audio_data = f.read()

    audio_data = audio_data[44:] # skip head

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        audio_channel_count=1,
        language_code='zh-CN',
        enable_automatic_punctuation=True,
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True,
    )

    requests = (speech.StreamingRecognizeRequest(audio_content=chunk) for chunk in generate_chunks(audio_data))

    try:
        callback.on_started()
        responses = client.streaming_recognize(config=streaming_config, requests=requests)

        for response in responses:
            if not response.results:
                continue

            result = response.results[0]

            if result.is_final:
                callback.on_completed(result.alternatives[0].transcript)
            else:
                callback.on_result_changed(result.alternatives[0].transcript)
    except Exception as e:
        callback.on_error(e)
    finally:
        callback.on_close()

def generate_chunks(audio_data, chunk_size=3200):
    print(f'audio_data={len(audio_data)}')
    idx = 0
    for i in range(0, len(audio_data), chunk_size):
        yield audio_data[i:i + chunk_size]
        pause_time = random.uniform(1, 3)
        print(f'idx={idx}')
        idx += 1
        print(f"停顿 {pause_time:.2f} 秒")
        time.sleep(pause_time)

if __name__ == "__main__":
    process(credentials)

# google：每月前60分钟免费/超过60分钟后,价格是0.006美分每15秒，0.024刀/min，1.44刀/小时
# aliyun：3个月免费试用，试用期限制2路并发，商用后3.5元/小时

# export GOOGLE_APPLICATION_CREDENTIALS="zhanzushun-8dd339d73749.json"