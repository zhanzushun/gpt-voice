from fastapi import FastAPI, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
import logging
import aiohttp
import time
from datetime import datetime
import os
import requests

import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
    level=logging.INFO
)

app = FastAPI()
STATIC_FOLDER_PATH = 'static'
os.makedirs(STATIC_FOLDER_PATH, exist_ok=True)

from fastapi.staticfiles import StaticFiles
app.mount("/api_12/static", StaticFiles(directory=STATIC_FOLDER_PATH), name="static")


from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

message_dict = {}
MSG_INIT = -1
MSG_DONE = -2
END_SENTENCE = '<|done|>'


@app.get("/api_12/sse/{msg_id}")
async def get_msg_status(msg_id: str):
    def event_stream():
        prev_idx = MSG_INIT
        cnt = 0
        while prev_idx != MSG_DONE:
            sentence_list = message_dict.get(msg_id, [])
            # logging.info(f'msg_id={msg_id}, status={prev_idx}, sentences={len(sentence_list)}, cnt={cnt}')
            if (len(sentence_list) > prev_idx + 1):
                new_idx = len(sentence_list) - 1
                if sentence_list[-1] == END_SENTENCE:
                    new_idx = new_idx - 1

                logging.info(f'msg_id={msg_id}, new idx={new_idx}')
                text = ' '.join(sentence_list[prev_idx+1:new_idx+1])
                text = f"data: {text}\n\n"
                logging.info(f'yield {text}')
                yield text
                prev_idx = new_idx

                if sentence_list[-1] == END_SENTENCE:
                    prev_idx = MSG_DONE
                cnt = 0
            else:
                if cnt > 60:
                    yield_text = f"data: ...Oops! 超时了\n\n"
                    logging.info(f'yield {yield_text}')
                    yield yield_text
                    break
            time.sleep(1)
            cnt += 1

        yield_text = f"data: done\n\n"
        logging.info(f'yield {yield_text}')
        yield yield_text
        
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api_12/think_and_reply")
async def post_chat(user:str=Query(...), message:str=Query(...), message_id:str=Query(...)):
    # 前端在发送这个请求之前，会先生成 message_id 并启动 sse 等待接收文本信息
    # 在 proxy_chat_generator 中把接收到的 llm 文本按句子标点断句：
    # 1. 句子文本通过sse返回前端
    # 2. 同时句子发送到语音stt服务转语音， proxy_speech_generator，转好的语音字节流通过本接口回传给前端
    logging.info(f'user={user}, message_id={message_id}')
    return StreamingResponse(combined_generator(user, message, message_id), media_type='audio/mpeg')


async def combined_generator(user, message, message_id):
    async for sentence in proxy_chat_generator(user, message, message_id, "gpt-4"):
        logging.info(f'sentence={sentence}')
        if sentence == END_SENTENCE:
            break
        async for voice_data in proxy_speech_generator(sentence):
            yield voice_data


@app.get("/api_12/speech")
async def get_speech(text: str = Query(...)):
    logging.info("/speech")
    return await proxy_speech(text)

import shutil
def del_file(file_to_delete):
    try:
        os.remove(file_to_delete)
        print(f"文件 {file_to_delete} 删除成功。")
    except OSError as e:
        print(f"Warning: 文件 {file_to_delete} 删除失败 - {e}")

from pydub import AudioSegment
import numpy as np

SILENT_THRESHOLD = 1500

def extract_audio_data0(file_path):
    audio = AudioSegment.from_file(file_path)
    samples = np.array(audio.get_array_of_samples())
    return samples, audio.frame_rate

def extract_audio_data(file_path, target_sr=22050):
    audio = AudioSegment.from_file(file_path)
    audio = audio.set_frame_rate(target_sr)
    samples = np.array(audio.get_array_of_samples())
    return samples, audio.frame_rate

def check_silence(audio_segment, threshold=SILENT_THRESHOLD):
    max_amplitude = np.max(np.abs(audio_segment))
    logging.info(f'Max amplitude of the segment: {max_amplitude}')
    return max_amplitude < threshold

# def check_silence_all(audio, sr, chunk_duration_ms=100):
#     chunk_size = int((chunk_duration_ms / 1000) * sr)
#     num_chunks = len(audio) // chunk_size
#     for i in range(num_chunks):
#         chunk = audio[i * chunk_size:(i + 1) * chunk_size]
#         if not check_silence(chunk):
#             logging.info(f'Chunk {i} is not silent')
#             return False
#     remainder = audio[num_chunks * chunk_size:]
#     if len(remainder) > 0 and not check_silence(remainder):
#         logging.info('Remainder is not silent')
#         return False
#     logging.info('File is silent')
#     return True

def has_extended_content(base_file, extended_file):
    logging.info('Start comparing')

    base_audio, base_sr = extract_audio_data(base_file)
    extended_audio, extended_sr = extract_audio_data(extended_file)
    
    base_length = len(base_audio)
    extended_length = len(extended_audio)
    
    if extended_length > base_length:
        extra_audio = extended_audio[base_length:extended_length]
        has_content = not check_silence(extra_audio)
        #has_content = not check_silence_all(extra_audio, base_sr)
        logging.info(f'Comparison done, has extend content={has_content}')
        return has_content
    else:
        logging.info('Extended file is not longer than the base file')
        return True

def is_file_silent(file_path):
    logging.info('Checking if the file is silent')
    audio, sr = extract_audio_data(file_path)
    is_silent = check_silence(audio)
    #is_silent = check_silence_all(audio, sr)
    logging.info(f'File {file_path} is {"silent" if is_silent else "not silent"}')
    return is_silent

@app.post("/api_12/upload")
async def upload_file(file: UploadFile = File(...), user: str = Form(...), tick: str = Form(...)):
    
    logging.info(f'receiving upload file, file={file.filename}, tick={tick}, user={user}')
    file_tick = file.filename.split('.')[0].split('_')[1]

    dir1 = datetime.now().strftime("%Y%m")
    os.makedirs(os.path.join(STATIC_FOLDER_PATH, user, dir1), exist_ok=True)
    file_path = os.path.join(STATIC_FOLDER_PATH, user, dir1, file.filename)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    process_next = True
    recent_file = file_path + ".recent"
    if os.path.exists(recent_file):
        if file_tick==tick:
            del_file(recent_file)
            if is_file_silent(file_path):
                process_next = False
        else:
            if not has_extended_content(recent_file, file_path):
                process_next = False
    shutil.copy(file_path, recent_file)
    if not process_next:
        logging.info(f'no change detected, file={recent_file}')
        return {"text": ""}

    try:
        # convert to m4a
        file_m4a = file_path + ".m4a"
        if os.path.exists(file_m4a):
            os.remove(file_m4a)
        convert_aac_to_m4a(file_path, file_m4a)
        file_path = file_m4a
    except:
        return {"text": ""}

    # audio to text
    logging.info(f'upload={file_path}')
    return {"text": _audio_to_script(file_path)}


import ffmpeg
def convert_aac_to_mp3(aac_file, mp3_file):
    ffmpeg.input(aac_file).output(mp3_file, acodec='libmp3lame').global_args('-loglevel', 'error').run()

def convert_aac_to_m4a(aac_file, m4a_file):
    ffmpeg.input(aac_file).output(m4a_file, c='copy').global_args('-loglevel', 'error').run()


def _audio_to_script(local_file_path):
    headers = {
        'Authorization': f'Bearer sk-{config.API_KEY}',
    }
    data = {
        'model': 'whisper-1',
        'temperature': '0.01'
    }
    files = {
        'file': open(local_file_path, 'rb'),
    }
    response = requests.post('https://api.openai.com/v1/audio/transcriptions', headers=headers, data=data, files=files)
    dict1 = response.json()
    logging.info(f'response={dict1}')
    if response.status_code == 200:
        return dict1['text']
    else:
        return dict1['error']['message']

# -----------------------------------

async def proxy_speech(text) -> StreamingResponse:
    generator = proxy_speech_generator(text)
    return StreamingResponse(generator, media_type='audio/mpeg')

async def proxy_speech_generator(text: str):
    async with aiohttp.ClientSession() as session:
        try:
            headers={
                'Authorization': f'Bearer sk-{config.API_KEY}',
                'Content-Type': 'application/json'
            }
            async with session.post('https://api.openai.com/v1/audio/speech', 
                                    headers = headers,
                                    json={"input":text, "model": "tts-1", "voice": "alloy"}) as response:
                logging.info(f'proxy speech start: {text}')
                async for data in response.content.iter_any():
                    yield data
                logging.info(f'proxy speech done: {text}')
        except Exception as e:
            yield f'Exception: {e}'


# -----------------------------------

URL = f'{config.PROXY_CHAT_HOST_PORT}/api_13/chat'


SEPERATORS = [
    "\n",
    "。","！","？",
    ". ", "! ", "? ",
    "；", "; ",
    "，", ", "
]

def contains_sep(text):
    for SEP in SEPERATORS:
        if SEP in text:
            arr = text.split(SEP, 1)
            left = arr[0] + SEP
            right = arr[1]
            return True, left, right
    return False, None, None


async def proxy_chat_generator(user: str, prompt: str, message_id:str, model: str):
    async with aiohttp.ClientSession() as session:
        try:
            sentences = []
            message_dict[message_id] = sentences
            async with session.post(URL, json={"prompt":prompt, "user": user, "user_group": "zzs", "model": model}) as response:
                sentence = ''
                async for bytes in response.content.iter_any():
                    data = bytes.decode('utf-8')
                    data = data.replace('\n\n', '\n') # \n\n conflict with SSE
                    exist,left,right = contains_sep(data)
                    if exist:
                        sentence += left
                        yield sentence
                        sentence = sentence.replace('\n', '  ') # I dont know why swift's SSE cant handle \n
                        sentences.append(sentence)
                        sentence = right
                    else:
                        sentence += data
                if sentence:
                    yield sentence
                    sentence = sentence.replace('\n', '  ') # I dont know why swift's SSE cant handle \n
                    sentences.append(sentence)
                sentences.append(END_SENTENCE)
                logging.info(f'sentences={sentences}')

        except Exception as e:
            yield f'Exception: {e}'

# sudo apt-get install ffmpeg
# ffmpeg -version

# conda activate env-gpt-voice
# pip install fastapi uvicorn aiohttp requests python-multipart ffmpeg-python pydub numpy==1.26.4
# nohup uvicorn web:app --reload --host 0.0.0.0 --port 5012 >> nohup.out &


if __name__ == '__main__':
    path = '/opt/disk2/gpt-voice/static/202407/'
    logging.info('converting from aac to mp3')
    convert_aac_to_mp3(path + 'record_5.aac', path + 'record_5.aac.a.mp3')
    logging.info('has converted from aac to mp3, starting convert aac to m4a')
    convert_aac_to_m4a(path + 'record_5.aac', path + 'record_5.aac.a.m4a')
    logging.info('has converted from aac to m4a')