import asyncio
from queue import Queue

import json
import requests
import uvicorn
import websockets
import httpx
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents, DeepgramClientOptions, SpeakWebSocketEvents, SpeakWSOptions
import logging
import numpy as np



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


##################################### DEEPGRAM CONFIG #######################################

config = DeepgramClientOptions(
    options={"keepalive": "true"}
)

CHANNELS = 1
RATE = 48000
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
Persona = "dlkmmlskdmclksdmclkfsdmclkm"
domain_name = "mfma"

app = FastAPI()

s_id = {}
current_utterance = ""
user_input = ""

audio_data = bytearray()

def convert_float32_to_int16(raw_bytes: bytes) -> bytes:
    """
    Convert a bytes object containing little-endian float32 samples (range -1.0 to 1.0)
    to a bytes object of int16 samples using NumPy.
    """
    # Convert raw bytes to a NumPy array of float32 values
    float_samples = np.frombuffer(raw_bytes, dtype=np.float32)

    # Clip the values to the range [-1.0, 1.0]
    clipped_samples = np.clip(float_samples, -1.0, 1.0)

    # Scale to int16 range and convert the data type
    int16_samples = (clipped_samples * 32767).astype(np.int16)

    return int16_samples.tobytes()






async def get_audio_for_transcription(websocket: WebSocket, input_audio_store_queue: asyncio.Queue):
    """Continuously read audio chunks from the browser and store them into an asyncio Queue."""
    print("entered get_audio")
    global audio_data
    try:
        while True:
            raw_audio = await websocket.receive_bytes()
            audio_data.extend(raw_audio)
            print(f"Received raw audio chunk of size {len(raw_audio)} bytes")
            int16_audio = convert_float32_to_int16(raw_audio)
            await input_audio_store_queue.put(int16_audio)


    except WebSocketDisconnect:
        print("Client Disconnected from Websocket")
    except Exception as e:
        print(f"Error: {e}")

async def send_audio_for_transcription(dg_connection,input_audio_store_queue:asyncio.Queue):
    try:
        while True:
            data = await input_audio_store_queue.get()
            await dg_connection.send(data)

    except asyncio.CancelledError:
        print("Transcription process cancelled")
    except Exception as e:
        print(f"Error --> {e}")


async def receive_transcript(dg_connection, transcript_store_queue: asyncio.Queue, response_store_queue: asyncio.Queue,
                             session_id: str):
    """
    Receive transcript from Deepgram, accumulate transcript chunks, and when a final result is received,
    send the accumulated transcript to the transcription store queue and trigger the Exei API call.
    """
    accumulated_transcript = ""  # Local variable to accumulate transcript text

    async def on_message(result, **kwargs):
        nonlocal accumulated_transcript
        try:
            # Extract the current transcript chunk from Deepgram result
            transcript_chunk = result.channel.alternatives[0].transcript
            if result.is_final:
                # Append the final chunk to our accumulated transcript (trim any extra spaces)
                if transcript_chunk:
                    accumulated_transcript += transcript_chunk.strip() + " "

                # Once a final result is reached, send the transcript for further processing
                if accumulated_transcript.strip():
                    print(f"Final transcript: {accumulated_transcript.strip()}")
                    await transcript_store_queue.put(accumulated_transcript.strip())
                    # Trigger the Exei API call asynchronously
                    asyncio.create_task(
                        call_exei_query_api(session_id, accumulated_transcript.strip(), Persona, domain_name,
                                            response_store_queue))
                    # Reset the accumulated transcript for the next utterance
                    accumulated_transcript = ""
            else:
                # Optionally handle interim results, e.g., log or update UI
                print(f"Interim transcript: {transcript_chunk}")
        except Exception as e:
            print(f"Error in on_message: {e}")
            logger.error(f"Error in on_message: {e}")

    async def on_error(error, **kwargs):
        print(f"Deepgram Error: {error}")
        logger.error(f"Deepgram Error: {error}")

    # Register event callbacks with the Deepgram connection
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

    # Keep the function running indefinitely
    while True:
        await asyncio.sleep(1)


async def call_exei_query_api(session_id: str, user_input: str, persona: str, domain_name: str,response_store_queue: asyncio.Queue):

    """ Calls the exei api with the user_input as transcription from deepgram  and streams text chunks as response from the exei,
        results are stored in response_store_queue.

        :return -- >
    """
    url = "https://qa-chat.exei.ai/stream_voice"
    payload = {
        "session_id": session_id,
        "user_input": user_input,
        "persona": persona,
        "domain_name": domain_name
    }

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST",url,json = payload) as response:
                 pattern = r"'chunk':\s*'([^']*)'"
                 async for line in response.aiter_lines():
                     line = line.strip()
                     if not line:
                         continue
                     match = re.search(pattern,line)
                     if match:
                         chunk_text = match.group(1)
                         print(f"Response from Exei: {chunk_text}")
                         await response_store_queue.put(chunk_text)
                     else:
                         continue

    except Exception as e:
        print(f"Error in Exei API: {e}")




# async def produce_audio_of_response(dg_connection,response_store_queue,output_audio_store_queue):
#     try:
#         async def on_binary_data(self,data, **kwargs):
#             try:
#                 await output_audio_store_queue.put(data)
#             except Exception as e:
#                 print(f"Error: {e}")
#
#         dg_connection.on(SpeakWebSocketEvents.AudioData, on_binary_data)
#         options = SpeakWSOptions(
#             model="aura-asteria-en",
#             encoding="linear16",
#             sample_rate=24000,
#
#         )
#         await dg_connection.start(options)
#         if not await dg_connection.start(options):
#             print("Failed to start connection")
#             return
#         while True:
#             try:
#                 tts_text = await response_store_queue.get()
#
#                 await dg_connection.send_text(tts_text)
#                 await dg_connection.flush()
#                 await dg_connection.wait_for_complete()
#
#
#             except Exception as e:
#                 print(f"Error: {e}")
#
#
#     except Exception as e:
#         print(f"Error: {e}")
#
#     finally:
#         await dg_connection.finish()
#
# async def send_tts_audio(websocket: WebSocket, output_audio_store_queue: asyncio.Queue):
#     try:
#         while True:
#             data = await output_audio_store_queue.get()
#             await websocket.send_bytes(data)
#     except Exception as e:
#         logger.error(f"Error sending TTS audio: {e}")



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    input_audio_store_queue = asyncio.Queue()
    transcript_store_queue = asyncio.Queue()
    response_store_queue = asyncio.Queue()
    # output_audio_store_queue = asyncio.Queue()


    deepgram = DeepgramClient("49630c797e6d4eede50979dfc25c9e629af77b10",config)
    dg_connection_listen = deepgram.listen.asyncwebsocket.v("1")
    dg_connection_speak = deepgram.speak.asyncwebsocket.v("1")


    await dg_connection_listen.start(options)

    # session_id = s_id["session_id"]
    session_id = "383883803803"

    try:
        task_get_audio_for_transcription = asyncio.create_task(get_audio_for_transcription(websocket,input_audio_store_queue))
        task_send_audio_for_transcription = asyncio.create_task(send_audio_for_transcription(dg_connection_listen,input_audio_store_queue))
        task_receive_transcript = asyncio.create_task(receive_transcript(dg_connection_listen,transcript_store_queue,response_store_queue,session_id))
        # task_produce_audio_of_response = asyncio.create_task(produce_audio_of_response(dg_connection_speak,response_store_queue,output_audio_store_queue))
        # task_audio_send_to_user = asyncio.create_task(send_tts_audio(websocket, output_audio_store_queue))
        tasks = [task_get_audio_for_transcription, task_send_audio_for_transcription, task_receive_transcript]

        done,pending = await asyncio.wait(tasks,return_when=asyncio.FIRST_EXCEPTION)
        for task in pending:
            task.cancel()

    except Exception as e:
            print(f"Error: {e}")


    finally:
        await websocket.close()


if __name__ == "__main__":
    uvicorn.run("deepgram_1:app",host="0.0.0.0", port=8000,reload=True)

try:
    await dg_connection.send(data)
    print(f"successfully sent {len(data)} to deepgram")


    async def on_message(self, result, **kwargs):
        nonlocal accumulated_transcript
        try:
            transcript_chunk = result.channel.alternatives[0].transcript
            if result.is_final:
                # Append the final chunk to our accumulated transcript (trim any extra spaces)
                if transcript_chunk:
                    accumulated_transcript += transcript_chunk.strip() + " "

                # Once a final result is reached, send the transcript for further processing
                if accumulated_transcript.strip():
                    print(f"Final transcript: {accumulated_transcript.strip()}")
                    await transcript_store_queue.put(accumulated_transcript.strip())
                    # Trigger the Exei API call asynchronously
                    asyncio.create_task(
                        call_exei_query_api(session_id, accumulated_transcript.strip(), persona, domain_name,
                                            response_store_queue))
                    # Reset the accumulated transcript for the next utterance
                    accumulated_transcript = ""
            else:
                # Optionally handle interim results, e.g., log or update UI
                # print(f"Interim transcript: {transcript_chunk}")
                pass

        except Exception as e:
            print(f"Error in on_message: {e}")
            logger.error(f"Error in on_message: {e}")


    async def on_error(error, **kwargs):
        print(f"Deepgram Error: {error}")
        logger.error(f"Deepgram Error: {error}")


    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

except Exception as e:
    print(f"Error --> {e}")


