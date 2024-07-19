from google.cloud import speech
from google.oauth2 import service_account
from google.protobuf import duration_pb2

import weakref
import asyncio
from dataclasses import dataclass
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from typing import Dict
import uvicorn
import sys
from concurrent.futures import ThreadPoolExecutor

import time
import json
import logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
    level=logging.INFO
)
import queue

import config as gloabl_config


CONFIDENCE_MIN = 0.5
SENTENCE_COMPLETE_SEC = 1  # SECONDS

class Config:
    CHUNK_SIZE: int = 3200

class RecognizerCallback:
    def __init__(self, name, websocket, recognizer_ref):
        self.name = name
        self.websocket = websocket
        self.recognizer_ref = recognizer_ref

    async def on_sentence_begin(self):
        logging.info(f'{self.name} - 识别开始')

    async def on_result_changed(self, message):
        logging.info(f'{self.name} - 中间识别结果')
        try:
            transcript = message.transcript
            logging.info(f'sending to websocket: {transcript}')
            await self.websocket.send_text(f"{transcript}")
        except Exception as e:
            logging.exception(f'ops, on_result_changed: {str(e)}')

    async def on_sentence_end(self, message):
        logging.info(f'{self.name} - 识别结束')
        try:
            transcript = message.transcript
            confidence = message.confidence
            if confidence > CONFIDENCE_MIN:
                message_result = '<|final|>' + transcript
                logging.info(f'confidence={confidence}, sending to websocket: {message_result}')
                await self.websocket.send_text(f"{message_result}")
            else:
                logging.info(f'confidence is too low={confidence}')
        except Exception as e:
            logging.exception(f'ops, on_sentence_end: {str(e)}')


credentials = service_account.Credentials.from_service_account_file(gloabl_config.CREDENTIALS_FILE)
global_speech_client = speech.SpeechClient(credentials=credentials)

global_streaming_config = speech.StreamingRecognitionConfig(
    config=speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="zh-CN",
        alternative_language_codes=["en-US",],
        enable_automatic_punctuation=True,
        model="command_and_search",
    ),
    interim_results=True,
    single_utterance=True,
    enable_voice_activity_events=True,
    voice_activity_timeout=speech.StreamingRecognitionConfig.VoiceActivityTimeout(
        speech_end_timeout=duration_pb2.Duration(seconds=1)
    )
)

class Recognizer:
    def __init__(self, name, websocket):
        self.audio_async_queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.is_running = False
        self.process_task = None
        self.websocket = websocket
        self.callback = RecognizerCallback(name, websocket, weakref.ref(self))

    async def start(self):
        self.is_running = True
        logging.info('recog start')
        await self.callback.on_sentence_begin()
        self.process_task = asyncio.create_task(self._process_audio_data())

    async def stop(self):
        if self.is_running:
            self.is_running = False
            logging.info('recog stop')
            await self.audio_async_queue.put(None)  # 发送终止信号
            if self.process_task:
                await self.process_task
    
    def shutdown(self):
        self.executor.shutdown(wait=True)

    async def send(self, audio_data):
        if not self.is_running:
            await self.start()
        await self.audio_async_queue.put(audio_data)

    async def _process_audio_data(self):

        sync_queue = queue.Queue()

        def sync_generator():
            while True:
                try:
                    chunk = sync_queue.get(timeout=1)
                    if chunk is None:
                        break
                    yield speech.StreamingRecognizeRequest(audio_content=bytes(chunk))
                except queue.Empty:
                    continue
        
        async def async_to_sync_queue():
            while self.is_running:
                chunk = await self.audio_async_queue.get()
                if chunk is None:
                    sync_queue.put(None)
                    break
                sync_queue.put(chunk)

        async_to_sync_queue_task = asyncio.create_task(async_to_sync_queue())

        try:
            # 使用 run_in_executor 来在线程池中运行同步的 streaming_recognize
            responses = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                global_speech_client.streaming_recognize,
                global_streaming_config,
                sync_generator()
            )
            for response in responses:
                for result in response.results:
                    if result.is_final:
                        # 选择置信度最高的替代结果
                        best_alternative = max(result.alternatives, key=lambda alt: alt.confidence)
                        await self.callback.on_sentence_end(best_alternative)
                    else:
                        # 对于非最终结果，我们仍然可以只使用第一个替代结果
                        await self.callback.on_result_changed(result.alternatives[0])

        except Exception as e:
            logging.exception(f"Error in audio processing.")
        finally:
            self.is_running = False
            async_to_sync_queue_task.cancel()
            try:
                await async_to_sync_queue_task
            except asyncio.CancelledError:
                pass

app = FastAPI()

active_connections: Dict[str, WebSocket] = {}
user_bytes = {}
audio_buffer = bytearray()

import jwt
ALGORITHM = "HS256"

@app.websocket("/api_16/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    try:
        token = await websocket.receive_text()
        logging.info(f'ws token={token}')
        payload = jwt.decode(token, gloabl_config.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        phone = payload.get("sub")
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

    logging.info(f'/ws/, user_id={user_id}, phone={phone}')
    active_connections[phone] = websocket
    active_users = list(active_connections.keys())
    logging.info(f'active_users.cnt={len(active_users)}, active_users={active_users[:10]}')

    config = Config()
    recognizer = Recognizer(phone, websocket)
    await recognizer.start()
    
    global audio_buffer
    try:
        async def audio_receiver():
            global audio_buffer
            last_received_time = 0
            while True:
                try:
                    audio_content = await asyncio.wait_for(websocket.receive_bytes(), timeout=0.1)
                    user_bytes[phone] = user_bytes.get(phone, 0) + len(audio_content)
                    
                    last_received_time = time.time()
                    audio_buffer.extend(audio_content)
                    while len(audio_buffer) >= config.CHUNK_SIZE:
                        await recognizer.send(audio_buffer[:config.CHUNK_SIZE])
                        audio_buffer = audio_buffer[config.CHUNK_SIZE:]
                except asyncio.TimeoutError:
                    if last_received_time and time.time() - last_received_time > 1:
                        await recognizer.stop()
                    pass
                except WebSocketDisconnect:
                    logging.info(f"WebSocket disconnected for user {phone}")
                    await recognizer.stop()
                    break
                except Exception as e:
                    logging.error(f"Error receiving audio for user {phone}: {e}")
                    break

        # 持续接收直到用户关闭 websocket
        receiver_task = asyncio.create_task(audio_receiver())
        await asyncio.gather(receiver_task)
    
    except WebSocketDisconnect:
        logging.info(f"WebSocket disconnected for user {phone}")
    except Exception as e:
        logging.info(f"Error: {e}")
    finally:
        users_to_file()
        recognizer.shutdown()
        audio_buffer = bytearray()
        if phone in active_connections:
            del active_connections[phone]
        logging.info(f"Cleaned up connection for user {phone}")

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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

# google：每月前60分钟免费/超过60分钟后,价格是0.006美分每15秒，0.024刀/min，1.44刀/小时
# aliyun：3个月免费试用，试用期限制2路并发，商用后3.5元/小时

# conda activate aliyun-stt-ws

# pip install fastapi uvicorn google-cloud-speech websockets pyjwt==2.8.0

# nginx:
# proxy_http_version 1.1;                 #websocket
# proxy_set_header Upgrade $http_upgrade; #websocket
# proxy_set_header Connection "upgrade";  #websocket 

# nohup uvicorn google-stt-ws:app --reload --host 0.0.0.0 --port 5016 >> nohup.out &