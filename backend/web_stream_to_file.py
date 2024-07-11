import asyncio
import numpy as np
import soundfile as sf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import logging
import time

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
    level=logging.INFO
)

app = FastAPI()

audio_buffer = bytearray()
sample_rate = 16000


@app.websocket("/api_12/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    global audio_buffer, is_recording
    await websocket.accept()
    async def audio_receiver():
        while True:
            try:
                audio_content = await asyncio.wait_for(websocket.receive_bytes(), timeout=0.1)
                logging.info(f'receiving length={len(audio_content)}')
                logging.info(audio_content[0:10])
                audio_buffer.extend(audio_content)
                if try_save_audio():
                    break
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                logging.info(f"WebSocket disconnected for user {user_id}")
                break
            except Exception as e:
                logging.error(f"Error receiving audio for user {user_id}: {e}")
                break
    try:
        receiver_task = asyncio.create_task(audio_receiver())
        await asyncio.gather(receiver_task)
    except Exception as e:
        logging.info(f"Error: {e}")
    finally:
        audio_buffer = bytearray()

def try_save_audio():
    global audio_buffer
    if len(audio_buffer) > 5*16000:
        audio_data = np.frombuffer(audio_buffer, dtype=np.int16)
        sf.write('recorded_audio.wav', audio_data, sample_rate, subtype='PCM_16')
        logging.info("Audio saved as recorded_audio.wav")
        return True
    return False

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
