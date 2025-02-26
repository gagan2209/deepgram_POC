import asyncio
from csv import excel

import requests
import uvicorn
import websockets
import httpx
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents, DeepgramClientOptions, SpeakWebSocketEvents, SpeakWSOptions
import logging
import numpy as np

from test import websocket_endpoint

config = DeepgramClientOptions(
    options={"keepalive": "true"}
)
CHANNELS = 1
RATE = 16000
options = LiveOptions(
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


app = FastAPI()
s_id = {}

async def get_audio_for_transcription(websocket: WebSocket, input_audio_store_queue: asyncio.Queue):
    print("Entered_get_audio function")
    try:
        while True:
            message = await websocket.receive()
            print(type(message))

    except WebSocketDisconnect:
        print("Websocket Disconnected")

    except Exception as e:
        print(f"Error--> {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket.accept()
    except Exception as e:
        print(f"Error--> {e}")

    input_audio_store_queue = asyncio.Queue()
    deepgram = DeepgramClient("49630c797e6d4eede50979dfc25c9e629af77b10", config)
    dg_connection_listen = deepgram.listen.asyncwebsocket.v("1")
    await dg_connection_listen.start(options)

    session_id = "383883803803"
