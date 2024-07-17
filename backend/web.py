from typing import List
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse
import logging
import aiohttp
import time
from datetime import datetime
import os
from queue import Queue, Empty
import json

from pydantic import BaseModel

import config
from login import router as login_router
from login import verify_token

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(funcName)s - %(message)s",
    level=logging.INFO
)

app = FastAPI()
app.include_router(login_router)

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

message_dict = {} # sse消息队列
END_SENTENCE = ''

def msg_from_file(phone):
    now_obj = datetime.now()
    date = now_obj.strftime("%Y%m%d")
    ym = now_obj.strftime("%Y%m")
    t = now_obj.strftime('%Y-%m-%d %H:%M:%S')

    os.makedirs(os.path.join(STATIC_FOLDER_PATH, phone, ym), exist_ok=True)
    file_path = os.path.join(STATIC_FOLDER_PATH, phone, ym, date + '.json')
    msgs = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding='utf-8') as f:
            msgs = json.load(f)
    return msgs, file_path, t

def msg_to_file(phone, sentbyme, sentences):
    msgs, file_path, t = msg_from_file(phone)
    msgs.append({'time':t, 'sentbyme':sentbyme, 'content': ' '.join(sentences)})
    with open(file_path, "w", encoding='utf-8') as f:
        json.dump(msgs, f, indent=2, ensure_ascii=False)


@app.get("/api_12/sse/{msg_id}")
async def get_msg_status(msg_id: str, phone: str = Depends(verify_token)):
    def event_stream():
        sentences = []
        if msg_id not in message_dict:
            message_dict[msg_id] = Queue()
        while True:
            try:
                sentence = message_dict[msg_id].get(timeout=60)  # 等待60秒来获取新消息
                if sentence == END_SENTENCE:
                    break
                logging.info(f'msg_id={msg_id}, new message={sentence}')
                sentences.append(sentence)
                text = f"data: {sentence}\n\n"
                logging.info(f'yield {text}')
                yield text
            except Empty:
                yield_text = f"data: ...Oops! 超时了\n\n"
                logging.info(f'yield {yield_text}')
                yield yield_text
                break
        yield_text = f"data: done\n\n"
        logging.info(f'yield {yield_text}')
        del message_dict[msg_id]
        msg_to_file(phone, False, sentences)
        yield yield_text
    return StreamingResponse(event_stream(), media_type="text/event-stream")

import jwt
ALGORITHM = "HS256"

@app.get("/api_12/think_and_reply")
async def post_chat(token:str=Query(...), message:str=Query(...), message_id:str=Query(...)):
    # 前端在发送这个请求之前，会先生成 message_id 并启动 sse 等待接收文本信息
    # 在 proxy_chat_generator 中把接收到的 llm 文本按句子标点断句：
    # 1. 句子文本通过sse返回前端
    # 2. 同时句子发送到语音stt服务转语音， proxy_speech_generator，转好的语音字节流通过本接口回传给前端
    try:
        logging.info(f'ws token={token}')
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        phone = payload.get("sub")
        if phone is None:
            return {}
    except jwt.ExpiredSignatureError:
        return {}
    except jwt.InvalidTokenError:
        return {}
    logging.info(f'user={phone}, message_id={message_id}')
    msg_to_file(phone, True, [message,])
    return StreamingResponse(piped_generator(phone, message, message_id), media_type='audio/mpeg')


async def piped_generator(user, message, message_id):
    async for sentence in proxy_chat_generator(user, message, message_id, "gpt-4"):
        logging.info(f'sentence={sentence}')
        if sentence == END_SENTENCE:
            break
        async for voice_data in proxy_speech_generator(sentence):
            yield voice_data


async def proxy_speech_generator(text: str):
    async with aiohttp.ClientSession() as session:
        try:
            headers={
                'Authorization': f'Bearer sk-{config.API_KEY}',
                'Content-Type': 'application/json'
            }
            async with session.post('https://api.openai.com/v1/audio/speech', 
                                    headers = headers,
                                    json={"input":text, "model": "tts-1", "voice": "nova"}) as response:
                logging.info(f'proxy speech start: {text}')
                async for data in response.content.iter_any():
                    yield data
                logging.info(f'proxy speech done: {text}')
        except Exception as e:
            yield f'Exception: {e}'


# -----------------------------------

CHAT_URL = f'{config.PROXY_CHAT_HOST_PORT}/api_13/chat'


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
            if message_id not in message_dict:
                message_dict[message_id] = Queue()
            async with session.post(CHAT_URL, json={"prompt":prompt, "user": user, "user_group": "zzs", "model": model}) as response:
                sentence = ''
                async for bytes in response.content.iter_any():
                    data = bytes.decode('utf-8')
                    data = data.replace('\n\n', '\n') # \n\n conflict with SSE
                    exist,left,right = contains_sep(data)
                    if exist:
                        sentence += left
                        sentence = sentence.replace('\n', '  ') # I dont know why swift's SSE cant handle \n
                        message_dict[message_id].put(sentence)
                        yield sentence
                        sentence = right
                    else:
                        sentence += data
                if sentence:
                    sentence = sentence.replace('\n', '  ') # I dont know why swift's SSE cant handle \n
                    message_dict[message_id].put(sentence)
                    yield sentence
                message_dict[message_id].put(END_SENTENCE)
                logging.info(f'sentences done')

        except Exception as e:
            yield f'Exception: {e}'

class HistoryResponse(BaseModel):
    content: str
    sentbyme: bool
    time: str


@app.get("/api_12/history", response_model=List[HistoryResponse])
def get_chat_history(phone: str = Depends(verify_token)):
    msgs, _, _ = msg_from_file(phone)
    return [HistoryResponse(**item) for item in msgs]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# conda activate env-gpt-voice

# pip install fastapi uvicorn aiohttp requests python-multipart pyjwt aliyunsdkcore
# nohup uvicorn web:app --reload --host 0.0.0.0 --port 5012 >> nohup.out &
