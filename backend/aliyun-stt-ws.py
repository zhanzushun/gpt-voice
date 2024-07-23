import asyncio
import threading
import logging
from dataclasses import dataclass
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict
import uvicorn
import sys
from concurrent.futures import ThreadPoolExecutor
import weakref
import time
import json
import logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
    level=logging.INFO
)

import os
import time
import json
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
import numpy as np
import soundfile as sf
import jwt
import requests


import config as gloabl_config


ALGORITHM = "HS256"
bearer_scheme = HTTPBearer()

def get_phone_from_token(token):
    payload = jwt.decode(token, gloabl_config.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    return payload.get("sub")

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        phone = get_phone_from_token(token)
        if phone is None:
            logging.error(f'验证码无效, 手机号码为:{phone}')
            raise HTTPException(status_code=401, detail="Invalid token")
        return phone
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

class AliyunTokenManager:
    def __init__(self, region="cn-shanghai"):
        self.client = AcsClient(
            gloabl_config.ALIYUN_APP_ID,
            gloabl_config.ALIYUN_APP_KEY,
            region
        )
        self.token = None
        self.expire_time = 0
        self.refresh_threshold = 300  # 刷新阈值，单位为秒，这里设置为5分钟

    def _create_token(self):
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')

        try:
            response = self.client.do_action_with_exception(request)
            jss = json.loads(response)
            if 'Token' in jss and 'Id' in jss['Token']:
                self.token = jss['Token']['Id']
                self.expire_time = jss['Token']['ExpireTime']
                print(f"New token created: {self.token}")
                print(f"Expire time: {self.expire_time}")
            else:
                raise Exception("Failed to create token: Invalid response format")
        except Exception as e:
            print(f"Error creating token: {e}")
            raise

    def get_token(self):
        current_time = int(time.time())
        
        # 如果 token 不存在或者即将过期，则刷新 token
        if self.token is None or (self.expire_time - current_time) <= self.refresh_threshold:
            self._create_token()
        
        return self.token

token_manager = AliyunTokenManager()

import nls

CONFIDENCE_MIN = 0.5
SENTENCE_COMPLETE_SEC = 1 # SECONDS

@dataclass
class Config:
    APPKEY: str = gloabl_config.ALIYUN_STT_APP_KEY
    URL: str = "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"
    CHUNK_SIZE: int = 1280*2

class SpeechRecognitionCallback:
    def __init__(self, phone, websocket, speech_recog_ref):
        self.phone = phone
        self.websocket = websocket
        self.speech_recog_ref = speech_recog_ref
        self.loop = asyncio.get_event_loop()

    def on_sentence_begin(self, message, *args):
        asyncio.run_coroutine_threadsafe(self._on_sentence_begin(message), self.loop)

    def on_sentence_end(self, message, *args):
        asyncio.run_coroutine_threadsafe(self._on_sentence_end(message), self.loop)

    def on_start(self, message, *args):
        asyncio.run_coroutine_threadsafe(self._on_start(message), self.loop)

    def on_error(self, message, *args):
        asyncio.run_coroutine_threadsafe(self._on_error(message), self.loop)

    def on_close(self, *args):
        asyncio.run_coroutine_threadsafe(self._on_close(), self.loop)

    def on_result_changed(self, message, *args):
        asyncio.run_coroutine_threadsafe(self._on_result_changed(message), self.loop)

    def on_completed(self, message, *args):
        asyncio.run_coroutine_threadsafe(self._on_completed(message), self.loop)

    async def _on_sentence_begin(self, message):
        logging.info(f'{self.phone} - 识别开始: {message}')
        # if self.websocket:
        #     await self.websocket.send_text(f"识别开始: {message}")

# 识别结束 消息格式
# {
#     "header": {
#         "namespace": "SpeechTranscriber",
#         "name": "SentenceEnd",
#         "status": 20000000,
#         "message_id": "866a68591b924556bb0f3ed59af09fdb",
#         "task_id": "c71740af276548e9b9f0b606491bfd91",
#         "status_text": "Gateway:SUCCESS:Success."
#     },
#     "payload": {
#         "index": 1,
#         "time": 2500,
#         "result": "Hello hello hello 3 hello 4。Hello. ",
#         "confidence": 0.827,
#         "words": [],
#         "status": 0,
#         "gender": "",
#         "begin_time": 0,
#         "fixed_result": "",
#         "unfixed_result": "",
#         "stash_result": {
#             "sentenceId": 2,
#             "beginTime": 2500,
#             "text": "",
#             "fixedText": "",
#             "unfixedText": "",
#             "currentTime": 2500,
#             "words": []
#         },
#         "audio_extra_info": "",
#         "sentence_id": "02a151e50b8c46838a07add2de97559f",
#         "gender_score": 0.0
#     }
# }
    async def _on_sentence_end(self, message):
        logging.info(f'{self.phone} - 识别结束')
        try:
            message = json.loads(message)
            if message.get('payload', {}).get('confidence', 0) > 0.5:
                message_result = message.get('payload', {}).get('result', '')
                message_result = '<|final|>' + message_result
                logging.info(f'sending to websocket: {message_result}')
                await self.websocket.send_text(f"{message_result}")
                speech_recognizer = self.speech_recog_ref()
                if speech_recognizer is not None:
                    speech_recognizer.start_save_wav()

            else:
                logging.info('confidence is toooo low')
        except:
            logging.exception(f'ops, _on_sentence_end')

    async def _on_start(self, message):
        logging.info(f'{self.phone} - 识别启动: {message}')
        # if self.websocket:
        #     await self.websocket.send_text(f"识别启动: {message}")

    async def _on_error(self, message):
        logging.info(f'{self.phone} - 识别错误: {message}')
        # if self.websocket:
        #     await self.websocket.send_text(f"识别错误: {message}")

    async def _on_close(self):
        try:
            speech_recognizer = self.speech_recog_ref()
            if speech_recognizer is not None:
                logging.info(f'{self.phone} - 识别通道关闭')
                speech_recognizer.started = False
            else:
                logging.info("SpeechRecognizer object no longer exists")
            # if self.websocket:
            #     await self.websocket.send_text("识别通道关闭")
        except:
            logging.exception(f'ops, _on_close')


# 中间识别结果
# {
#     "header": {
#         "namespace": "SpeechTranscriber",
#         "name": "TranscriptionResultChanged",
#         "status": 20000000,
#         "message_id": "08c115289c214f18876d121ecf68f8a7",
#         "task_id": "c71740af276548e9b9f0b606491bfd91",
#         "status_text": "Gateway:SUCCESS:Success."
#     },
#     "payload": {
#         "index": 1,
#         "time": 2200,
#         "result": "Hello hello hello hello. ",
#         "confidence": 0.86,
#         "words": [],
#         "status": 0,
#         "fixed_result": "",
#         "unfixed_result": ""
#     }
# }

    async def _on_result_changed(self, message):
        logging.info(f'{self.phone} - 中间识别结果')
        try:
            message = json.loads(message)
            if message.get('payload', {}).get('confidence', 0) > 0.5:
                message_result = message.get('payload', {}).get('result', '')
                logging.info(f'sending to websocket: {message_result}')
                await self.websocket.send_text(f"{message_result}")
            else:
                logging.info('confidence is toooo low')
        except:
            logging.exception(f'ops, _on_result_changed')


    async def _on_completed(self, message):
        logging.info(f'{self.phone} - 识别完成: {message}')
        # if self.websocket:
        #     await self.websocket.send_text(f"识别完成: {message}")

class SpeechRecognizer:
    def __init__(self, config: Config, phone: str, msg_id: str, websocket: WebSocket):
        self.config = config
        self.phone = phone
        self.msg_id = msg_id
        self.websocket = websocket
        self.callback = SpeechRecognitionCallback(phone, websocket, weakref.ref(self))
        self.sr = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.started = False
        self.all_audio_buffer = bytearray()

    def create_transcriber(self):
        return nls.NlsSpeechTranscriber(
            url=self.config.URL,
            token=token_manager.get_token(),
            appkey=self.config.APPKEY,
            on_sentence_begin=self.callback.on_sentence_begin,
            on_sentence_end=self.callback.on_sentence_end,
            on_start=self.callback.on_start,
            on_result_changed=self.callback.on_result_changed,
            on_completed=self.callback.on_completed,
            on_error=self.callback.on_error,
            on_close=self.callback.on_close,
            callback_args=[self.phone]
        )

    def start_transcriber_sync(self):
        self.sr.start(
            aformat="pcm",
            enable_intermediate_result=True,
            enable_punctuation_prediction=True,
            enable_inverse_text_normalization=True
        )

    async def start_transcriber(self):
        if self.started:
            return
        loop = asyncio.get_event_loop()
        self.sr = await loop.run_in_executor(self.executor, self.create_transcriber)
        logging.info(f'sr created')

        await loop.run_in_executor(self.executor, self.start_transcriber_sync)
        logging.info(f'sr.started')
        self.started = True

    async def stop_transcriber(self):
        if self.sr:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self.sr.stop)

    async def send_audio(self, audio_chunk):
        await self.start_transcriber()
        if self.sr:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self.sr.send_audio, audio_chunk)
        
    def start_save_wav(self):
        asyncio.create_task(audio_tofile(self.phone, self.msg_id, self.all_audio_buffer)) # 启动一个任务然后不管他

app = FastAPI()

active_connections: Dict[str, WebSocket] = {}
user_bytes = {}


@app.websocket("/api_16/ws/{msg_id}")
async def websocket_endpoint(websocket: WebSocket, msg_id: str):
    await websocket.accept()
    try:
        token = await websocket.receive_text()
        logging.info(f'ws token={token}')
        phone = get_phone_from_token(token)
        if phone is None:
            await websocket.send_text("TOKEN_INVALID")
            await websocket.close()
            return
    except jwt.ExpiredSignatureError:
        await websocket.send_text("TOKEN_INVALID")
        await websocket.close()
        return
    except jwt.InvalidTokenError:
        await websocket.send_text("TOKEN_INVALID")
        await websocket.close()
        return

    logging.info(f'/ws/, msg_id={msg_id}, phone={phone}')
    active_connections[phone] = websocket
    active_users = list(active_connections.keys())
    logging.info(f'active_users.cnt={len(active_users)}, active_users={active_users[:10]}')

    config = Config()
    recognizer = SpeechRecognizer(config, phone, msg_id, websocket)
    try:
        async def audio_receiver():
            temp_audio_buffer = bytearray()
            last_received_time = 0
            while True:
                try:
                    audio_content = await asyncio.wait_for(websocket.receive_bytes(), timeout=0.1)
                    user_bytes[phone] = user_bytes.get(phone, 0) + len(audio_content)
                    last_received_time = time.time()
                    temp_audio_buffer.extend(audio_content)
                    recognizer.all_audio_buffer.extend(audio_content)
                    while len(temp_audio_buffer) >= config.CHUNK_SIZE:
                        await recognizer.send_audio(temp_audio_buffer[:config.CHUNK_SIZE])
                        temp_audio_buffer = temp_audio_buffer[config.CHUNK_SIZE:]
                except asyncio.TimeoutError:
                    if last_received_time and time.time() - last_received_time > 1:
                        last_received_time = 0
                        await recognizer.stop_transcriber()
                    pass
                except WebSocketDisconnect:
                    logging.info(f"WebSocket disconnected for user {phone}")
                    await recognizer.stop_transcriber()
                    break
                except Exception as e:
                    logging.error(f"Error receiving audio for user {phone}: {e}")
                    break
            temp_audio_buffer.clear()
            temp_audio_buffer = None

        # 持续接收直到用户关闭 websocket
        receiver_task = asyncio.create_task(audio_receiver())
        await asyncio.gather(receiver_task)
    
    except WebSocketDisconnect:
        logging.info(f"WebSocket disconnected for user {phone}")
    except Exception as e:
        logging.info(f"Error: {e}")
    finally:
        users_to_file()
        if phone in active_connections:
            del active_connections[phone]
        logging.info(f"Cleaned up connection for user {phone}")

from collections import defaultdict
# 为每个唯一的 key 创建一个锁
file_locks = defaultdict(asyncio.Lock)

async def async_write_wav(wav_file, audio_data, sample_rate):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, 
        lambda: sf.write(wav_file, audio_data, sample_rate, subtype='PCM_16')
    )

async def audio_tofile(phone, msg_id, all_audio_buffer):
    key = f"{phone}_{msg_id}"
    filename = f"{key}.wav"
    # 获取或创建这个 key 的锁
    lock = file_locks[key]
    # 使用这个 key 的锁来控制对文件的访问
    async with lock:
        try:
            audio_data = np.frombuffer(all_audio_buffer, dtype=np.int16)
            sample_rate=16000
            wav_file = os.path.join('static', phone, filename)
            os.makedirs(os.path.join('static', phone), exist_ok=True)
            await async_write_wav(wav_file, audio_data, sample_rate)
            logging.info(f"Audio saved as {wav_file}")
            return True
        except:
            logging.exception("audio_tofile")

import ffmpeg

async def async_convert_wav_to_mp3(wav_file, mp3_file):
    await asyncio.to_thread(
        ffmpeg.input(wav_file)
        .output(mp3_file, acodec='libmp3lame')
        .global_args('-loglevel', 'error', '-y')
        .run
    )

@app.get("/api_16/re_recognize/{msg_id}")
async def get_re_recognize(msg_id: str, phone: str = Depends(verify_token)):
    return await re_recognize(phone, msg_id)

async def re_recognize(phone, msg_id):
    wav_file = os.path.join('static', phone, f'{phone}_{msg_id}.wav')
    mp3_file = os.path.join('static', phone, f'{phone}_{msg_id}.mp3')

    await async_convert_wav_to_mp3(wav_file, mp3_file)
    logging.info(f"Audio saved as {mp3_file}")

    with open(mp3_file, 'rb') as file:
        files = {'file': file}
        response = requests.post(gloabl_config.INTERNAL_FILE_STT_URL, files=files)
        
        if response.status_code == 200:
            logging.info(f"remote file stt successed, response={response.json()}")
            return response.json()
        else:
            logging.info(f"Failed to remote file stt . Status code: {response.status_code}")
            logging.info(f"Response: {response.text}")
            return {"text": ""}



def users_to_file():
    with open("users_bytes.json", "w") as f:
        json.dump(user_bytes, f, indent=2, ensure_ascii=False)

def users_from_file():
    global user_bytes
    try:
        with open("users_bytes.json", "r") as f:
            user_bytes = json.load(f)
    except FileNotFoundError:
        pass

users_from_file()

# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000)

# 单独部署到阿里云机器

# 1. ubuntu:
# sudo apt-get install ffmpeg
# ffmpeg -version

# 2. centos7
# sudo mv /etc/yum.repos.d/CentOS-Base.repo /etc/yum.repos.d/CentOS-Base.repo.backup
# sudo wget -O /etc/yum.repos.d/CentOS-Base.repo http://mirrors.aliyun.com/repo/Centos-7.repo
# sudo rm -f /etc/yum.repos.d/nodesource*.repo
# sudo yum clean all
# sudo yum makecache
# sudo yum install -y epel-release
# sudo sed -e 's!^metalink=!#metalink=!g' \
#     -e 's!^#baseurl=!baseurl=!g' \
#     -e 's!//download\.fedoraproject\.org/pub!//mirrors.aliyun.com!g' \
#     -e 's!http://mirrors\.aliyun!https://mirrors.aliyun!g' \
#     -i /etc/yum.repos.d/epel*
# sudo rpm --import http://li.nux.ro/download/nux/RPM-GPG-KEY-nux.ro
# sudo rpm -Uvh http://li.nux.ro/download/nux/dextop/el7/x86_64/nux-dextop-release-0-5.el7.nux.noarch.rpm
# sudo yum install ffmpeg ffmpeg-devel
# ffmpeg -version

# ==============================
# conda activate aliyun-stt-ws

# 下载 https://github.com/aliyun/alibabacloud-nls-python-sdk
# 或者 https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20221222/efsj/alibabacloud-nls-python-sdk-1.0.0.zip
# pip install -r requirements.txt
# pip install .
# pip install aliyun-python-sdk-core==2.15.1
# pip install fastapi uvicorn aiohttp requests python-multipart pyjwt==2.8.0 numpy==1.26.4 soundfile ffmpeg-python

# nginx:
# proxy_http_version 1.1;                 #websocket
# proxy_set_header Upgrade $http_upgrade; #websocket
# proxy_set_header Connection "upgrade";  #websocket 

# nohup uvicorn aliyun-stt-ws:app --reload --host 0.0.0.0 --port 5016 >> nohup.out &

async def _main():
    await re_recognize('18616699733', '20240720_090914_108')

if __name__ == '__main__':
    import asyncio
    asyncio.run(_main())