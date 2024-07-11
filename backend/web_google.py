import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.cloud import speech
from typing import Dict
import logging
import time

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

active_connections: Dict[str, WebSocket] = {}

client = speech.SpeechClient()

config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=16000,
    language_code="zh-CN",
    alternative_language_codes=["en-US"],
    enable_automatic_punctuation=True,
)

streaming_config = speech.StreamingRecognitionConfig(
    config=config, interim_results=True
)

CONFIDENCE_THRESHOLD = 0.8

SILENCE_THRESHOLD = 300  # milliseconds
CHUNK_SIZE = 1024  # silent frame size in bytes

@app.websocket("/api_12/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    logging.info(f"WebSocket connection opened for user {user_id}")

    audio_queue = asyncio.Queue()
    recognition_task = None

    async def audio_receiver():
        last_audio_time = time.time()
        while True:
            try:
                audio_content = await asyncio.wait_for(websocket.receive_bytes(), timeout=0.1)
                logging.info(f'receiving bytes={len(audio_content)}')
                await audio_queue.put(audio_content)
                last_audio_time = time.time()
            except asyncio.TimeoutError:
                if time.time() - last_audio_time > SILENCE_THRESHOLD / 1000:
                    audio_content = b'\0' * CHUNK_SIZE
                    await audio_queue.put(audio_content)
                    last_audio_time = time.time()
            except WebSocketDisconnect:
                logging.info(f"WebSocket disconnected for user {user_id}")
                break
            except Exception as e:
                logging.error(f"Error receiving audio for user {user_id}: {e}")
                break

    async def audio_generator():
        while True:
            audio_content = await audio_queue.get()
            if audio_content is None:
                break
            yield speech.StreamingRecognizeRequest(audio_content=audio_content)

    def sync_generator():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async_gen = audio_generator()
        try:
            while True:
                try:
                    yield loop.run_until_complete(async_gen.__anext__())
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    async def process_responses(responses):
        try:
            response_count = 0
            for response in responses:
                response_count += 1
                logging.info(f"Received response {response_count}")
                if not response.results:
                    logging.info("Response has no results")
                    continue
                for result in response.results:
                    if not result.alternatives:
                        logging.info("Result has no alternatives")
                        continue
                    alternative = result.alternatives[0]
                    logging.info(f"Transcript: {alternative.transcript}")
                    logging.info(f"Confidence: {alternative.confidence}")
                    
                    if alternative.confidence >= CONFIDENCE_THRESHOLD:
                        await websocket.send_json({
                            "user_id": user_id,
                            "transcript": alternative.transcript,
                            "confidence": alternative.confidence
                        })
            if response_count == 0:
                logging.info("No responses received from Google Speech-to-Text")
        except Exception as e:
            logging.info(f"Error processing responses: {e}")

    async def run_recognition():
        try:
            logging.info("Starting speech recognition")
            responses = await asyncio.to_thread(
                client.streaming_recognize,
                streaming_config,
                sync_generator()
            )
            logging.info("Speech recognition started, processing responses")
            await process_responses(responses)
            logging.info("Finished processing responses")
        except Exception as e:
            logging.error(f"Error in speech recognition for user {user_id}: {e}")

    try:
        receiver_task = asyncio.create_task(audio_receiver())
        recognition_task = asyncio.create_task(run_recognition())
        await asyncio.gather(receiver_task, recognition_task)
    except Exception as e:
        logging.error(f"Unexpected error for user {user_id}: {e}")
    finally:
        if recognition_task:
            recognition_task.cancel()
        logging.info(f"Closing WebSocket connection for user {user_id}")
        await websocket.close()

@app.on_event("startup")
async def startup_event():
    logging.info("Server started, ready to accept connections.")

@app.on_event("shutdown")
async def shutdown_event():
    for connection in active_connections.values():
        await connection.close()
    logging.info("Server shutting down, all connections closed.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# pip install fastapi uvicorn google-cloud-speech websockets numpy==1.26.4 soundfile

# nohup uvicorn web3:app --reload --host 0.0.0.0 --port 5012 >> nohup.out &