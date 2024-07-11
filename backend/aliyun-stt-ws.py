import asyncio
import threading
import logging
from dataclasses import dataclass
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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

import config

class AliyunTokenManager:
    def __init__(self, region="cn-shanghai"):
        self.client = AcsClient(
            config.ALIYUN_APP_ID,
            config.ALIYUN_APP_KEY,
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
    APPKEY: str = 'KSnmqH8ilz1N6z9x'
    URL: str = "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"
    CHUNK_SIZE: int = 1280*2

class SpeechRecognitionCallback:
    def __init__(self, name, websocket, speech_recog_ref):
        self.name = name
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
        logging.info(f'{self.name} - 识别开始: {message}')
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
        logging.info(f'{self.name} - 识别结束')
        try:
            message = json.loads(message)
            if message.get('payload', {}).get('confidence', 0) > 0.5:
                message_result = message.get('payload', {}).get('result', '')
                message_result = '<|final|>' + message_result
                logging.info(f'sending to websocket: {message_result}')
                await self.websocket.send_text(f"{message_result}")
            else:
                logging.info('confidence is toooo low')
        except:
            logging.exception(f'ops, _on_sentence_end')

    async def _on_start(self, message):
        logging.info(f'{self.name} - 识别启动: {message}')
        # if self.websocket:
        #     await self.websocket.send_text(f"识别启动: {message}")

    async def _on_error(self, message):
        logging.info(f'{self.name} - 识别错误: {message}')
        # if self.websocket:
        #     await self.websocket.send_text(f"识别错误: {message}")

    async def _on_close(self):
        try:
            speech_recognizer = self.speech_recog_ref()
            if speech_recognizer is not None:
                logging.info(f'{self.name} - 识别通道关闭')
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
        logging.info(f'{self.name} - 中间识别结果')
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
        logging.info(f'{self.name} - 识别完成: {message}')
        # if self.websocket:
        #     await self.websocket.send_text(f"识别完成: {message}")

class SpeechRecognizer:
    def __init__(self, config: Config, name: str, websocket: WebSocket):
        self.config = config
        self.name = name
        self.websocket = websocket
        self.callback = SpeechRecognitionCallback(name, websocket, weakref.ref(self))
        self.sr = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.started = False

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
            callback_args=[self.name]
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

app = FastAPI()

active_connections: Dict[str, WebSocket] = {}
audio_buffer = bytearray()

current_sent_cnt = 0
def log_sending():
    global current_sent_cnt
    current_sent_cnt += 1
    progress = '.' * current_sent_cnt
    sys.stdout.write(f'\r{progress}')
    sys.stdout.flush()
def log_sending_reset():
    global current_sent_cnt
    current_sent_cnt =0

@app.websocket("/api_16/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    logging.info(f'/ws/{user_id}')
    active_connections[user_id] = websocket
    config = Config()
    recognizer = SpeechRecognizer(config, f'user_{user_id}', websocket)
    global audio_buffer
    try:
        async def audio_receiver():
            global audio_buffer
            last_received_time = 0
            while True:
                try:
                    audio_content = await asyncio.wait_for(websocket.receive_bytes(), timeout=0.1)
                    last_received_time = time.time()
                    audio_buffer.extend(audio_content)
                    while len(audio_buffer) >= config.CHUNK_SIZE:
                        await recognizer.send_audio(audio_buffer[:config.CHUNK_SIZE])
                        # log_sending()
                        audio_buffer = audio_buffer[config.CHUNK_SIZE:]
                except asyncio.TimeoutError:
                    if last_received_time and time.time() - last_received_time > 1:
                        await recognizer.stop_transcriber()
                        # log_sending_reset()
                    pass
                except WebSocketDisconnect:
                    logging.info(f"WebSocket disconnected for user {user_id}")
                    await recognizer.stop_transcriber()
                    # log_sending_reset()
                    break
                except Exception as e:
                    logging.error(f"Error receiving audio for user {user_id}: {e}")
                    break

        # 持续接收直到用户关闭 websocket
        receiver_task = asyncio.create_task(audio_receiver())
        await asyncio.gather(receiver_task)
    
    except WebSocketDisconnect:
        logging.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logging.info(f"Error: {e}")
    finally:
        audio_buffer = bytearray()
        if user_id in active_connections:
            del active_connections[user_id]
        logging.info(f"Cleaned up connection for user {user_id}")

@app.get("/users")
async def get_active_users():
    return {"active_users": list(active_connections.keys())}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# conda activate aliyun-stt-ws

# 下载 https://github.com/aliyun/alibabacloud-nls-python-sdk
# 或者 https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20221222/efsj/alibabacloud-nls-python-sdk-1.0.0.zip
# pip install -r requirements.txt
# pip install .
# pip install aliyun-python-sdk-core==2.15.1
# pip install fastapi uvicorn aiohttp requests python-multipart

# nginx:
# proxy_http_version 1.1;                 #websocket
# proxy_set_header Upgrade $http_upgrade; #websocket
# proxy_set_header Connection "upgrade";  #websocket 

# nohup uvicorn aliyun-stt-ws:app --reload --host 0.0.0.0 --port 5016 >> nohup.out &