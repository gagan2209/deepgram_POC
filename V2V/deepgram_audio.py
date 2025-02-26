# import os
# import logging
# from deepgram.utils import verboselogs
#
# from deepgram import (
#     DeepgramClient,
#     SpeakOptions,
# )
#
# SPEAK_TEXT = {"text": "Hey there how are you, I hope you are doing fine, we are testing text to voice today for Exei"}
# filename = "test.mp3"
#
#
# def main():
#     try:
#         # STEP 1 Create a Deepgram client using the API key from environment variables
#         deepgram = DeepgramClient("49630c797e6d4eede50979dfc25c9e629af77b10")
#
#         # STEP 2 Call the save method on the speak property
#         options = SpeakOptions(
#             model="aura-asteria-en",
#         )
#
#         response = deepgram.speak.rest.v("1").save(filename, SPEAK_TEXT, options)
#         print(response.to_json(indent=4))
#
#     except Exception as e:
#         print(f"Exception: {e}")
#
# if __name__ == "__main__":
#     main()


import time
from deepgram.utils import verboselogs
import wave

from deepgram import (
    DeepgramClient,
    SpeakWebSocketEvents,
    SpeakWSOptions,
)

AUDIO_FILE = "output.wav"
TTS_TEXT = "Hello, this is a text to speech example using Deepgram. How are you doing today? I am fine thanks for asking."


def main():
    try:
        # use default config
        deepgram: DeepgramClient = DeepgramClient("49630c797e6d4eede50979dfc25c9e629af77b10")

        # Create a websocket connection to Deepgram
        dg_connection = deepgram.speak.websocket.v("1")

        def on_binary_data(self, data, **kwargs):
            print("Received binary data")
            with open(AUDIO_FILE, "ab") as f:
                f.write(data)
                f.flush()

        dg_connection.on(SpeakWebSocketEvents.AudioData, on_binary_data)

        # Generate a generic WAV container header
        # since we don't support containerized audio, we need to generate a header
        header = wave.open(AUDIO_FILE, "wb")
        header.setnchannels(1)  # Mono audio
        header.setsampwidth(2)  # 16-bit audio
        header.setframerate(16000)  # Sample rate of 16000 Hz
        header.close()

        # connect to websocket
        options = SpeakWSOptions(
            model="aura-asteria-en",
            encoding="linear16",
            sample_rate=16000,
        )

        print("\n\nPress Enter to stop...\n\n")
        if dg_connection.start(options) is False:
            print("Failed to start connection")
            return

        # send the text to Deepgram
        dg_connection.send_text(TTS_TEXT)

        # if auto_flush_speak_delta is not used, you must flush the connection by calling flush()
        dg_connection.flush()

        # Indicate that we've finished
        time.sleep(7)
        print("\n\nPress Enter to stop...\n\n")
        input()

        # Close the connection
        dg_connection.finish()

        print("Finished")

    except ValueError as e:
        print(f"Invalid value encountered: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()








import asyncio
import wave
from deepgram import DeepgramClient, SpeakWebSocketEvents, SpeakWSOptions

AUDIO_FILE = "output.wav"

async def generate_speech(dg_connection_speak, response_string: str):
    print(f"response string {response_string}")
    audio_data = bytearray()
    audio_complete = asyncio.Event()

    def on_binary_data(self, data, **kwargs):
        print(f"Received binary data, {len(data)} bytes")
        audio_data.extend(data)

    def on_close(self, close, **kwargs):
        print("WebSocket connection closed")
        audio_complete.set()

    dg_connection_speak.on(SpeakWebSocketEvents.AudioData, on_binary_data)
    dg_connection_speak.on(SpeakWebSocketEvents.Close, on_close)

    options = SpeakWSOptions(
        model="aura-asteria-en",
        encoding="linear16",
        sample_rate=16000,
    )

    if dg_connection_speak.start(options) is False:
        print("Failed to start connection")
        return

    dg_connection_speak.send_text(response_string)

    # Wait for all audio data to be received
    await audio_complete.wait()

    with wave.open(AUDIO_FILE, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono audio
        wav_file.setsampwidth(2)  # 16-bit audio
        wav_file.setframerate(16000)  # Match the sample rate in options
        wav_file.writeframes(audio_data)

    print(f"Audio saved to {AUDIO_FILE}")

# Usage
async def main():
    deepgram = DeepgramClient("YOUR_DEEPGRAM_API_KEY")
    dg_connection_speak = deepgram.speak.asyncwebsocket.v("1")
    await generate_speech(dg_connection_speak, "Your long response string here")

if __name__ == "__main__":
    asyncio.run(main())