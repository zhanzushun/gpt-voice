from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
import logging
import aiohttp
import time

import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
    level=logging.INFO
)

app = FastAPI()

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
            logging.info(f'msg_id={msg_id}, status={prev_idx}, sentences={len(sentence_list)}')
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

            time.sleep(1)
            cnt += 1
            if (cnt > 30) and (prev_idx == MSG_INIT):
                logging.info(f'no response from server, quit sse')
                break

        yield_text = f"data: done\n\n"
        logging.info(f'yield {yield_text}')
        yield yield_text
        
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api_12/think_and_reply")
async def post_chat(user:str=Query(...), message:str=Query(...), message_id:str=Query(...)):
    logging.info(f'user={user}, message_id={message_id}')
    return StreamingResponse(combined_generator(user, message, message_id), media_type='audio/mpeg')


async def combined_generator(user, message, message_id):
    async for sentence in proxy_chat_generator(user, message, message_id, "gpt-3.5-turbo"):
        logging.info(f'sentence={sentence}')
        if sentence == END_SENTENCE:
            break
        async for voice_data in proxy_speech_generator(sentence):
            yield voice_data


@app.get("/api_12/speech")
async def get_speech(text: str = Query(...)):
    logging.info("/speech")
    return await proxy_speech(text)

# -----------------------------------

g_content_type = None

async def proxy_speech(text) -> StreamingResponse:
    generator = proxy_speech_generator(text)
    return StreamingResponse(generator, media_type=g_content_type)

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
                global g_content_type
                g_content_type = response.content_type
                logging.info('content_type=' + g_content_type)
                async for data in response.content.iter_any():
                    #logging.info(len(data))
                    yield data
                logging.info('proxy speech done')
        except Exception as e:
            yield f'Exception: {e}'


# -----------------------------------

URL = f'{config.PROXY_CHAT_HOST_PORT}/openai-api-proxy/chat'

async def proxy_chat(user, prompt, model) -> StreamingResponse:
    generator = proxy_chat_generator(user, prompt, model)
    return StreamingResponse(generator)


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
            async with session.post(URL, json={"prompt":prompt, "user": user, "user_group": "marvin", "model": model}) as response:
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


# conda activate env-gpt-voice
# pip install fastapi uvicorn aiohttp
# nohup uvicorn web:app --reload --host 0.0.0.0 --port 5012 >> nohup.out &
