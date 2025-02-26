import asyncio
import json
import re
import requests
import httpx
import websockets

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
import neuralspace as ns
from pydantic import BaseModel
import logging


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VoiceRequest(BaseModel):
    session_id: str
    # user_input: str
    # persona: str
    # domain_name: str



# === Global Constants and Initialization ===

API_KEY = "sk_fb0b6af94e89fe36afc3a0913b766f0794b28681c1b96716220f5fe395450829"
vai = ns.VoiceAI(api_key=API_KEY)

# NeuralSpace Transcription Configuration
LANGUAGE = "en"
MIN_CHUNK_SIZE = 2
VAD_THRESHOLD = 0.5
DISABLE_PARTIAL = "True"
AUDIO_FORMAT = "pcm_16k"
DURATION = 600  # seconds (token valid duration)

# Exei API details (hard-coded persona and domain)
PERSONA = (
    "**Company Overview:**Xcelore is a fast-growing, AI-driven innovation hub that builds and enhances digital products and platforms for a modern world. "
    "With bases in Noida and the Netherlands, Xcelore specializes in high-impact digital product engineering, cloud solutions, and AI-driven innovations for startups and enterprises across diverse industries. "
    "Their mission is to help businesses excel in the digital realm while pushing the boundaries of technological advancement and innovation."
    "**Industry:**Xcelore operates in the Digital Technology Services & Product Engineering space, with expertise in:1. Generative AI R&D and PoC Lab2. AI-Led Product Development3. Digital Product Engineering4. Kotlin Multiplatform & Kotlin Server-side Development5. Offshore Development Teams. "
    "**Unique Aspects:**1. Design-First, Cloud-Native, Agile & Fullstack approach2. Commitment to providing value with transparency, empathy & complete ownership3. Emphasis on AI-driven innovation and cutting-edge technology4. Focus on delivering intelligent, future-ready digital experiences. "
    "**Driving Force:**Xcelore aims to disrupt the Digital Technology Services & Product Engineering space by integrating AI and next-gen technology into its solutions, enhancing efficiency, automation, and user engagement. "
    "**Core Values:**1. Excellence and Exploration2. T.I.E (Trust, Integrity, and Empathy)3. Continuous Learning and Sharing4. Fun-filled culture with work-life balance5. Ownership with Responsible Freedom. "
    "**Communication Channels:**1. Phone: +91 81784 97981 (India) | +31 616884242 (Netherlands)2. Email: sales@xcelore.com, inbound@xcelore.com3. WhatsApp: +91 81784 97981. "
    "**Services:**1. Generative AI Solutions2. AI-Led Product Development3. Conversational AI & Chatbots4. ML Ops5. Digital Product Engineering6. Product Discovery & Design7. Web & Mobile App Development8. Microservices Development9. Cloud and DevOps Services10. Kotlin Development (Multiplatform, Server-side, Android, and Migration)11. Cloud & DevOps as a Service12. Cloud Managed Services13. Audits, Assessments & Consulting14. Cloud Migration & Modernization. "
    "**AI-Powered Key Products:**1. **Exei – Virtual Assistant:** 24/7 AI-driven support for enhanced customer engagement and operational efficiency.2. **Xcelight – Business Intelligence:** Transforms CCTV systems into powerful business insight tools for efficiency and decision-making.3. **Translore – Real-Time Audio Translation:** Instant, accurate translations for seamless global communication. "
    "**Unique Initiatives:**1. Generative AI R&D and PoC Lab2. Offshore Development Teams3. Kotlin Multiplatform & Kotlin Server-side Development. "
    "**Experience & Success:**- 40+ years of cumulative leadership experience- 100+ team members- 75+ global clients across 10+ industries- 200+ successful projects. "
    "**Growth Partner Network:**Xcelore invites businesses to join its Growth Partner network, fostering collaborative success in business growth and digital transformation. "
    "**Terms of Service & Privacy Policy:**Xcelore's Terms of Service and Privacy Policy can be found on their website, outlining service conditions and data protection measures. "
    "At Xcelore, AI meets digital innovation, delivering intelligent solutions for businesses seeking performance enhancements, cost reductions, and superior user experiences. "
    "We don’t just develop digital solutions—we create future-ready intelligent experiences that keep businesses ahead of the curve."
)
DOMAIN_NAME = "xcelore"

app = FastAPI()

# === Helper Functions and Tasks ===
# s_id = {}
# @app.post("/get_data_for_voice")
# async def get_data(request: VoiceRequest):
#     s_id["session_id"]=request.session_id
#     return request.session_id


async def call_exei_api(session_id: str, user_input: str, persona: str, domain_name: str, response_store_queue: asyncio.Queue):
    """
    Calls the Exei API with the given transcription (user_input) and streams text chunks,
    which are then enqueued to the response_store_queue.
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
            async with client.stream("POST", url, json=payload) as response:
                pattern = r"'chunk':\s*'([^']*)'"
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    match = re.search(pattern, line)
                    if match:
                        chunk_text = match.group(1)
                        print("Exei API chunk:", chunk_text)
                        await response_store_queue.put(chunk_text)
                    else:
                        continue
    except Exception as e:
        print("Error calling Exei API:", e)


async def read_client(websocket: WebSocket, chunk_store_queue: asyncio.Queue):
    """
    Continuously read binary audio data sent by the client and enqueue it.
    """
    try:
        while True:
            data = await websocket.receive_bytes()
            await chunk_store_queue.put(data)
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket.")
    except Exception as e:
        print("Error in read_client:", e)


async def process_audio(ns_ws, chunk_store_queue: asyncio.Queue):
    """
    Dequeue audio chunks and send them to NeuralSpace’s transcription WebSocket.
    """
    try:
        while True:
            data = await chunk_store_queue.get()
            await ns_ws.send(data)
    except asyncio.CancelledError:
        print("Audio processing task cancelled.")
    except Exception as e:
        print("Error in process_audio:", e)


async def receive_response(ns_ws, response_store_queue: asyncio.Queue, session_id: str):
    """
    Listen for transcription responses from NeuralSpace.
    For each transcription received, trigger a task to call the Exei API.
    """
    try:
        async for message in ns_ws:
            try:
                response_data = json.loads(message)
                msg = response_data.get('text', '')
                if msg:
                    print("Transcription:", msg)
                    logger.info(f"session_id: {session_id}, transcription: {msg}")
                    # Trigger the Exei API call (its streamed output will be enqueued)
                    asyncio.create_task(call_exei_api(session_id, msg, PERSONA, DOMAIN_NAME, response_store_queue))
            except json.JSONDecodeError as e:
                print("JSON decode error:", e)
    except websockets.ConnectionClosed as e:
        print("NeuralSpace connection closed:", e)
    except Exception as e:
        print("Error in receive_response:", e)



async def process_tts(websocket: WebSocket, response_store_queue: asyncio.Queue):
    try:
        while True:
            # Wait for the next text chunk from the Exei API.
            chunk_text = await response_store_queue.get()

            # Prepare TTS synthesis data.
            tts_data = {
                "text": chunk_text,
                "speaker_id": "en-male-Oscar-english-neutral",
                "stream": True,
                "sample_rate": 16000,
                "config": {
                    "pace": 0.75,
                    "volume": 1.0,
                    "pitch_shift": 0,
                    "pitch_scale": 1.0
                }
            }
            try:
                loop = asyncio.get_event_loop()
                # Run the synchronous TTS synthesis in an executor to avoid blocking.
                result = await loop.run_in_executor(None, vai.synthesize, tts_data)
                print(f"TTS Response Type: {type(result)}")
                # Before sending, optionally check if the connection is still open.
                if websocket.client_state.name != "CONNECTED":
                    print("WebSocket no longer connected; stopping TTS processing.")
                    break

                await websocket.send_bytes(result)

            except WebSocketDisconnect:
                print("WebSocket disconnected during TTS synthesis; stopping TTS processing.")
                break

            except Exception as e:
                print("Error in TTS synthesis:", e)
                # Optionally, you might want to break here if the error is critical.
                break

    except Exception as e:
        print("Error in process_tts:", e)


# === FastAPI WebSocket Endpoint ===

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    A single WebSocket endpoint that:
      - Receives audio data from the client.
      - Forwards audio to NeuralSpace for transcription.
      - Listens for transcription responses.
      - Calls the Exei API to get response text.
      - Synthesizes TTS audio from the text.
      - Sends the TTS audio back to the client.
    """
    await websocket.accept()
    # Create in-memory queues for audio and text chunks.
    chunk_store_queue = asyncio.Queue()
    response_store_queue = asyncio.Queue()

    # Retrieve the transcription token from NeuralSpace.
    token_url = f"https://voice.neuralspace.ai/api/v2/token?duration={DURATION}"
    token_response = requests.get(token_url, headers={"Authorization": API_KEY})
    token_json = token_response.json()
    TOKEN = token_json.get("data", {}).get("token")
    if not TOKEN:
        print("Failed to retrieve NeuralSpace token.")
        await websocket.close()
        return

    # session_id = s_id["session_id"]
    session_id = "ndndlnfc"
    if not session_id:
        await websocket.close()
        return {"error": "No session found"}
    # Build the NeuralSpace transcription WebSocket URL.
    NS_WEBSOCKET_URL = (
        f"wss://voice.neuralspace.ai/voice/stream/live/transcribe/{LANGUAGE}/{TOKEN}/{session_id}"
        f"?max_chunk_size={MIN_CHUNK_SIZE}&vad_threshold={VAD_THRESHOLD}"
        f"&disable_partial={DISABLE_PARTIAL}&format={AUDIO_FORMAT}"
    )

    # Connect to NeuralSpace’s transcription WebSocket.
    try:
        async with websockets.connect(NS_WEBSOCKET_URL) as ns_ws:
            # Launch concurrent tasks:
            task_read_client = asyncio.create_task(read_client(websocket, chunk_store_queue))
            task_process_audio = asyncio.create_task(process_audio(ns_ws, chunk_store_queue))
            task_receive_response = asyncio.create_task(receive_response(ns_ws, response_store_queue, session_id))
            task_process_tts = asyncio.create_task(process_tts(websocket, response_store_queue))

            tasks = [task_read_client, task_process_audio, task_receive_response, task_process_tts]
            # Wait until any one task raises an exception (or completes)
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in pending:
                task.cancel()
    except Exception as e:
        print("Error with NeuralSpace connection or task execution:", e)
    finally:
        await websocket.close()


# === Run the FastAPI App ===

if __name__ == "__main__":
    uvicorn.run("test:app", host="0.0.0.0", port=8000, reload=True)
