from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import StreamingResponse
import asyncio
import os
import httpx
from sse_starlette.sse import EventSourceResponse
import logging
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
import os

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
    level=logging.INFO
)

app = FastAPI()

# 初始化 Deepgram 客户端
DEEPGRAM_API_KEY = 'b14aa702d2e2a9d811619ab15aaf0f02abeb220f'
deepgram = DeepgramClient(DEEPGRAM_API_KEY)

# 存储用户转录结果的字典
transcriptions = {}

dg_connection = deepgram.listen.live.v("1")
def on_message(self, result, **kwargs):
    sentence = result.channel.alternatives[0].transcript
    if len(sentence) > 0:
        key = f"{user_id}:{msg_id}"
        if key not in transcriptions:
            transcriptions[key] = []
        transcriptions[key].append(sentence)
        logging.info(f'transript={sentence}')
def on_metadata(self, metadata, **kwargs):
    print(f"\n\n{metadata}\n\n")
def on_error(self, error, **kwargs):
    print(f"\n\n{error}\n\n")
dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
dg_connection.on(LiveTranscriptionEvents.Error, on_error)
options = LiveOptions(
    model="nova-2",
#        language="en-US",
    smart_format=True,
)
dg_connection.start(options)

@app.post("/api_12/audio")
async def receive_audio(audio: UploadFile = File(...), user_id: str = Form(...), msg_id: str = Form(...)):
    logging.info('/audio received')
    content = await audio.read()
    chunk_size = 1024*1000
    idx = 0
    for i in range(0, len(content), chunk_size):
        logging.info(f'chunk {idx}')
        idx += 1
        chunk = content[i:i+chunk_size]
        if chunk:
            logging.info(f'chunk size={len(chunk)}')
            dg_connection.send(chunk)
    return {"message": "Audio received and processing started"}

@app.get("/transcriptions")
async def get_transcriptions(request: Request, user_id: str, msg_id: str):
    async def event_generator():
        key = f"{user_id}:{msg_id}"
        while True:
            if key in transcriptions and transcriptions[key]:
                yield {
                    "event": "transcription",
                    "data": {"transcription": transcriptions[key].pop(0)}
                }
            if await request.is_disconnected():
                break
            await asyncio.sleep(0.1)

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# pip install sse_starlette 
# pip install deepgram-sdk==3.*

# nohup uvicorn web2:app --reload --host 0.0.0.0 --port 5012 >> nohup.out &
