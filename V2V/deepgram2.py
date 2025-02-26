from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
import wave
import os
import asyncio
import numpy as np
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
    SpeakWebSocketEvents,
    SpeakWSOptions,
)
import logging
import httpx
import re



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Create a directory to store audio files if it doesn't exist
AUDIO_DIR = "audio_files"
os.makedirs(AUDIO_DIR, exist_ok=True)

connection_id = 0  # For unique filenames

############################################### DEEPGRAM CONFIG ###########################################################
config = DeepgramClientOptions(
    options={"keepalive": "true"}
)

audio_data_g= bytearray()

CHANNELS = 1
RATE = 48000

listen_options = LiveOptions(
    model="nova-2",
    language="hi",
    encoding="linear16",
    channels=CHANNELS,
    sample_rate=RATE,
    smart_format=True,
    vad_events=True,
    interim_results=True,
    endpointing=100,
    utterance_end_ms="1000"   # should not be less than 1000ms
)

speak_options = SpeakWSOptions(
            model="en-US",
            encoding="linear16",
            sample_rate=16000,
)

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



AUDIO_FILE = "output.wav"


async def generate_speech(dg_connection_speak, response_string: str):
    print(f"Response string: {response_string}")

    audio_data = bytearray()
    audio_complete = asyncio.Event()

    def on_binary_data(self, data, **kwargs):
        print(f"Received binary data: {len(data)} bytes")
        audio_data.extend(data)
        print(f"Total audio data size: {len(audio_data)}")

    def on_close(self, close, **kwargs):
        print("WebSocket connection closed, received all audio data.")
        audio_complete.set()

    dg_connection_speak.on(SpeakWebSocketEvents.AudioData, on_binary_data)
    dg_connection_speak.on(SpeakWebSocketEvents.Close, on_close)

    options = SpeakWSOptions(
        model="aura-asteria-en",
        encoding="linear16",
        sample_rate=16000,
    )

    if not dg_connection_speak.start(options):
        print("Failed to start WebSocket connection")
        return

    print("WebSocket started successfully, sending text...")
    dg_connection_speak.send_text(response_string)

    # Wait for all audio data to be received, but add a timeout to avoid blocking forever
    try:
        await asyncio.wait_for(audio_complete.wait(), timeout=20)
    except asyncio.TimeoutError:
        print("Timed out waiting for audio data.")

    # Save audio file only if we received data
    if audio_data:
        with wave.open(AUDIO_FILE, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono audio
            wav_file.setsampwidth(2)  # 16-bit audio
            wav_file.setframerate(16000)  # Match sample rate in options
            wav_file.writeframes(audio_data)

        print(f"Audio saved to {AUDIO_FILE}")
    else:
        print("No audio data received, file not saved.")



async def call_exei_query_api(session_id: str, user_input: str, persona: str, domain_name: str, dg_connection_speak):
    """
    Calls the Exei API with user input and retrieves the response.
    The response is then used for speech generation.
    """
    url = "https://qa-chat.exei.ai/voice"
    payload = {
        "session_id": session_id,
        "user_input": user_input,
        "persona": persona,
        "domain_name": domain_name
    }

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            response_string = data.get("response", "")
            print(f"Response from Exei: {response_string}")

    except Exception as e:
        print(f"Error in Exei API: {e}")
        response_string = ""

    await generate_speech(dg_connection_speak, response_string)





async def single_function(websocket: WebSocket, input_audio_store_queue:asyncio.Queue,transcript_store_queue:asyncio.Queue,session_id:str,dg_connection,persona,domain_name,dg_connection_speak,response_string:str):
    global audio_data_g
    accumulated_transcript = ""
    counter = 0
    try:
        while True:
            raw_audio = await websocket.receive_bytes()
            audio_data_g.extend(raw_audio)
            print(f"Received raw audio chunk of size {len(raw_audio)} bytes")
            int16_audio = convert_float32_to_int16(raw_audio)
            await input_audio_store_queue.put(int16_audio)
            data = await input_audio_store_queue.get()

            try:
                await dg_connection.send(data)
                print(f"successfully sent {len(data)} to deepgram")

                async def on_message(self, result, **kwargs):
                        nonlocal accumulated_transcript
                        nonlocal counter
                        current_transcript = result.channel.alternatives[0].transcript
                        if len(current_transcript) == 0 and len(accumulated_transcript)!=0:
                            counter+=1
                            if counter == 5:
                                await transcript_store_queue.put(accumulated_transcript)
                                print("################################################################################################################")
                                print("No transcripts received  calling exei query api")
                                print("################################################################################################################")
                                await call_exei_query_api(session_id, accumulated_transcript, persona, domain_name,dg_connection_speak)
                                print("Finished calling exei api")
                                counter = 0


                        if (current_transcript not in accumulated_transcript) and len(current_transcript) < len(accumulated_transcript):
                            accumulated_transcript+=current_transcript + " "
                        elif len(current_transcript) > len(accumulated_transcript):
                            accumulated_transcript = current_transcript


                async def on_error(error, **kwargs):
                    print(f"Deepgram Error: {error}")
                    logger.error(f"Deepgram Error: {error}")

                dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
                dg_connection.on(LiveTranscriptionEvents.Error, on_error)
                print(f"Accumulated till now --> {accumulated_transcript}")
            except Exception as e:
                print(f"Error --> {e}")

    except WebSocketDisconnect:
        print("websocket Disconnected")

    except Exception as e:
        print(f"Error --> {e}")

    filename = os.path.join(AUDIO_DIR, f"audio_{connection_id}.wav")
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)  # Mono audio (adjust if needed)
        wf.setsampwidth(2)  # 16-bit sample width
        wf.setframerate(48000)  # 48000 Hz sample rate (match this to your AudioContext.sampleRate)
        int16_audio = convert_float32_to_int16(audio_data_g)
        wf.writeframes(int16_audio)
    print(f"Audio saved to {filename}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    input_audio_store_queue = asyncio.Queue()
    transcript_store_queue = asyncio.Queue()
    response_string = ""

    persona = "**Company Overview:**Xcelore is a fast-growing, AI-driven innovation hub that builds and enhances digital products and platforms for a modern world. With bases in Noida and the Netherlands, Xcelore specializes in high-impact digital product engineering, cloud solutions, and AI-driven innovations for startups and enterprises across diverse industries. Their mission is to help businesses excel in the digital realm while pushing the boundaries of technological advancement and innovation.**Industry:**Xcelore operates in the Digital Technology Services & Product Engineering space, with expertise in:1. Generative AI R&D and PoC Lab2. AI-Led Product Development3. Digital Product Engineering4. Kotlin Multiplatform & Kotlin Server-side Development5. Offshore Development Teams**Unique Aspects:**1. Design-First, Cloud-Native, Agile & Fullstack approach2. Commitment to providing value with transparency, empathy & complete ownership3. Emphasis on AI-driven innovation and cutting-edge technology4. Focus on delivering intelligent, future-ready digital experiences**Driving Force:**Xcelore aims to disrupt the Digital Technology Services & Product Engineering space by integrating AI and next-gen technology into its solutions, enhancing efficiency, automation, and user engagement.**Core Values:**1. Excellence and Exploration2. T.I.E (Trust, Integrity, and Empathy)3. Continuous Learning and Sharing4. Fun-filled culture with work-life balance5. Ownership with Responsible Freedom**Communication Channels:**1. Phone: +91 81784 97981 (India) | +31 616884242 (Netherlands)2. Email: sales@xcelore.com, inbound@xcelore.com3. WhatsApp: +91 81784 979814. Social Media: LinkedIn, Twitter, Facebook, Instagram**Services:**1. Generative AI Solutions2. AI-Led Product Development3. Conversational AI & Chatbots4. ML Ops5. Digital Product Engineering6. Product Discovery & Design7. Web & Mobile App Development8. Microservices Development9. Cloud and DevOps Services10. Kotlin Development (Multiplatform, Server-side, Android, and Migration)11. Cloud & DevOps as a Service12. Cloud Managed Services13. Audits, Assessments & Consulting14. Cloud Migration & Modernization**AI-Powered Key Products:**1. **Exei – Virtual Assistant:** 24/7 AI-driven support for enhanced customer engagement and operational efficiency.2. **Xcelight – Business Intelligence:** Transforms CCTV systems into powerful business insight tools for efficiency and decision-making.3. **Translore – Real-Time Audio Translation:** Instant, accurate translations for seamless global communication.**Unique Initiatives:**1. Generative AI R&D and PoC Lab2. Offshore Development Teams3. Kotlin Multiplatform & Kotlin Server-side Development**Experience & Success:**- 40+ years of cumulative leadership experience- 100+ team members- 75+ global clients across 10+ industries- 200+ successful projects**Growth Partner Network:**Xcelore invites businesses to join its Growth Partner network, fostering collaborative success in business growth and digital transformation.**Terms of Service & Privacy Policy:**Xcelore's Terms of Service and Privacy Policy can be found on their website, outlining service conditions and data protection measures.At Xcelore, AI meets digital innovation, delivering intelligent solutions for businesses seeking performance enhancements, cost reductions, and superior user experiences. We don’t just develop digital solutions—we create future-ready intelligent experiences that keep businesses ahead of the curve"
    domain_name = "xcelore"
    global audio_data_g
    deepgram = DeepgramClient("2249e682cbf802becf25aabd5acfa55f54b16540", config)
    dg_connection_listen = deepgram.listen.asyncwebsocket.v("1")
    dg_connection_speak = deepgram.speak.websocket.v("1")


    await dg_connection_listen.start(listen_options)
    # await dg_connection_speak.start(speak_options)

    # session_id = s_id["session_id"]

    session_id = "383883803803"
    try:
        # task_get_audio_for_transcription = asyncio.create_task(get_audio_for_transcription(websocket, input_audio_store_queue,audio_data))
        # task_send_audio_for_transcription = asyncio.create_task(send_audio_for_transcription(dg_connection_listen, input_audio_store_queue,transcript_store_list,session_id))
        #
        # tasks = [task_get_audio_for_transcription,task_send_audio_for_transcription]
        #
        # done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        # for task in pending:
        #     task.cancel()
        await single_function(websocket,input_audio_store_queue,transcript_store_queue,session_id,dg_connection_listen,persona,domain_name,dg_connection_speak,response_string)

    except Exception as e:
        print(f"Error: {e}")


    finally:
        await websocket.close()



if __name__ == "__main__":
    uvicorn.run("deepgram2:app", host="0.0.0.0", port=8000, reload=True)


glpat-gzgmvjfSMh5AR3Pm6ZoH