import os
import asyncio
import wave
import logging
import numpy as np

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Create a directory to store audio files if it doesn't exist
AUDIO_DIR = "audio_files"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Global counter for unique connection IDs
connection_id_counter = 0

###############################################
# DEEPGRAM CONFIGURATION
###############################################
config = DeepgramClientOptions(options={"keepalive": "true"})
CHANNELS = 1
RATE = 16000
dg_options = LiveOptions(
    model="nova-2",
    language="en-US",
    encoding="linear16",
    channels=CHANNELS,
    sample_rate=RATE,
    endpointing=300,
    vad_events=True,
    interim_results=True,
    utterance_end_ms="1000"
)

def convert_float32_to_int16(raw_bytes: bytes) -> bytes:
    """
    Convert a bytes object containing little-endian float32 samples (range -1.0 to 1.0)
    to a bytes object of int16 samples using NumPy.
    """
    float_samples = np.frombuffer(raw_bytes, dtype=np.float32)
    clipped_samples = np.clip(float_samples, -1.0, 1.0)
    int16_samples = (clipped_samples * 32767).astype(np.int16)
    return int16_samples.tobytes()

class TranscriptionSession:
    def __init__(self, websocket: WebSocket, session_id: int):
        self.websocket = websocket
        self.session_id = session_id
        self.input_audio_queue = asyncio.Queue()
        self.transcript_list = []
        self.audio_data = bytearray()

        # Initialize Deepgram connection
        self.deepgram = DeepgramClient("49630c797e6d4eede50979dfc25c9e629af77b10", config)
        self.dg_connection = self.deepgram.listen.asyncwebsocket.v("1")

    async def start_deepgram(self):
        await self.dg_connection.start(dg_options)
        # Register event handlers only once.
        self.dg_connection.on(LiveTranscriptionEvents.Transcript, self.on_transcript)
        self.dg_connection.on(LiveTranscriptionEvents.Error, self.on_error)
        logger.info("Deepgram connection started and handlers registered (session %s)", self.session_id)

    async def on_transcript(self, result, **kwargs):
        try:
            sentence = result.channel.alternatives[0].transcript
            if sentence:
                logger.info("Transcript: %s (session %s)", sentence, self.session_id)
                self.transcript_list.append(sentence)
        except Exception as e:
            logger.error("Error processing transcript (session %s): %s", self.session_id, e)

    async def on_error(self, error, **kwargs):
        logger.error("Deepgram error (session %s): %s", self.session_id, error)

    async def receive_audio(self):
        """
        Continuously receive audio chunks from the websocket,
        append them to the local audio_data buffer and enqueue
        converted audio for transcription.
        """
        logger.info("Starting to receive audio (session %s)", self.session_id)
        try:
            while True:
                raw_audio = await self.websocket.receive_bytes()
                self.audio_data.extend(raw_audio)
                logger.info("Received audio chunk of size %d bytes (session %s)", len(raw_audio), self.session_id)
                int16_audio = convert_float32_to_int16(raw_audio)
                await self.input_audio_queue.put(int16_audio)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected (session %s)", self.session_id)
        except Exception as e:
            logger.error("Error in receive_audio (session %s): %s", self.session_id, e)

    async def send_audio(self):
        """
        Continuously get audio from the input queue and send it to Deepgram.
        """
        logger.info("Starting to send audio to Deepgram (session %s)", self.session_id)
        try:
            while True:
                data = await self.input_audio_queue.get()
                await self.dg_connection.send(data)
                logger.info("Sent %d bytes to Deepgram (session %s)", len(data), self.session_id)
        except asyncio.CancelledError:
            logger.info("send_audio task cancelled (session %s)", self.session_id)
        except Exception as e:
            logger.error("Error in send_audio (session %s): %s", self.session_id, e)

    async def run(self):
        # Start Deepgram connection and register event handlers
        await self.start_deepgram()

        # Create tasks for receiving audio and sending audio to Deepgram
        task_receive_audio = asyncio.create_task(self.receive_audio())
        task_send_audio = asyncio.create_task(self.send_audio())

        tasks = [task_receive_audio, task_send_audio]
        try:
            # Wait until one task encounters an exception.
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in pending:
                task.cancel()
        except Exception as e:
            logger.error("Error during session run (session %s): %s", self.session_id, e)
        finally:
            await self.websocket.close()
            await self.save_audio()

    async def save_audio(self):
        """
        Save the accumulated audio data to a WAV file using the defined RATE and CHANNELS.
        """
        filename = os.path.join(AUDIO_DIR, f"audio_{self.session_id}.wav")
        try:
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit sample width
                wf.setframerate(RATE)
                int16_audio = convert_float32_to_int16(self.audio_data)
                wf.writeframes(int16_audio)
            logger.info("Audio saved to %s (session %s)", filename, self.session_id)
        except Exception as e:
            logger.error("Error saving audio (session %s): %s", self.session_id, e)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global connection_id_counter
    connection_id_counter += 1
    session = TranscriptionSession(websocket, connection_id_counter)
    await session.run()

if __name__ == "__main__":
    uvicorn.run("deepgram2:app", host="0.0.0.0", port=8000, reload=True)
