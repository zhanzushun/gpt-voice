from fastapi import FastAPI, Body
from fastapi.responses import StreamingResponse
import logging
import aiohttp

import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
    level=logging.INFO
)

app = FastAPI()


@app.post("/api_12/chat")
async def post_chat(text):
    return await proxy_chat('user', text, "gpt-3.5")


@app.post("/api_12/speech")
async def post_speech(text: str = Body(...)):
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
                    logging.info(len(data))
                    yield data
        except Exception as e:
            yield f'Exception: {e}'


# -----------------------------------

URL = f'{config.PROXY_CHAT_HOST_PORT}/openai-api-proxy/chat'

async def proxy_chat(user, prompt, model) -> StreamingResponse:
    generator = proxy_chat_generator(user, prompt, model)
    return StreamingResponse(generator)

async def proxy_chat_generator(user: str, prompt: str, model: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(URL, json={"prompt":prompt, "user": user, "user_group": "marvin", "model": model}) as response:
                async for data in response.content.iter_any():
                    yield data
        except Exception as e:
            yield f'Exception: {e}'

async def proxy_sync(user: str, prompt: str, model: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(URL, json={"prompt":prompt, "user": user, "user_group": "marvin", "model": model}) as response:
            return await response.text()


# conda activate env-gpt-voice
# pip install fastapi uvicorn aiohttp
# nohup uvicorn web:app --reload --host 0.0.0.0 --port 5012 >> nohup.out &
