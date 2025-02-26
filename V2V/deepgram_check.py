# import pyaudio
# import wave
# import os
# from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
#
# # === Configuration ===
# CHUNK = 8000
# FORMAT = pyaudio.paInt16
# CHANNELS = 1
# RATE = 16000
# OUTPUT_FILE = "recorded_audio.wav"  # Audio file to save
#
# # Initialize PyAudio
# p = pyaudio.PyAudio()
# stream = p.open(format=FORMAT,
#                 channels=CHANNELS,
#                 rate=RATE,
#                 input=True,
#                 frames_per_buffer=CHUNK)
#
# # Initialize Deepgram client
# deepgram = DeepgramClient(api_key="49630c797e6d4eede50979dfc25c9e629af77b10")
# dg_connection = deepgram.listen.websocket.v("1")
#
# def on_message(self, result, **kwargs):
#     """Callback function for receiving transcriptions."""
#     sentence = result.channel.alternatives[0].transcript
#     if len(sentence) > 0:
#         print(f"Transcript: {sentence}")
#
# dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
#
# # Set up Deepgram options
# options = LiveOptions(
#     model="nova-2",
#     language="en-US",
#     encoding="linear16",
#     channels=CHANNELS,
#     sample_rate=RATE,
#     endpointing=500,
#     vad_events=True,
#     interim_results=True,
#     utterance_end_ms="1000",
#     punctuate=True
#
# )
#
#
#
# # Start the Deepgram connection
# dg_connection.start(options)
#
# print("Listening... Press Ctrl+C to stop.")
#
# # === Record and Stream Audio ===
# frames = []  # Store audio chunks
#
# try:
#     while True:
#         data = stream.read(CHUNK)
#         frames.append(data)  # Store recorded audio
#         dg_connection.send(data)  # Send to Deepgram
# except KeyboardInterrupt:
#     print("Stopping...")
#
# finally:
#     # Stop PyAudio stream
#     stream.stop_stream()
#     stream.close()
#     p.terminate()
#     dg_connection.finish()
#
#     # === Save Audio to a File ===
#     with wave.open(OUTPUT_FILE, 'wb') as wf:
#         wf.setnchannels(CHANNELS)
#         wf.setsampwidth(p.get_sample_size(FORMAT))
#         wf.setframerate(RATE)
#         wf.writeframes(b''.join(frames))
#
#     print(f"Audio saved as: {OUTPUT_FILE}")
#


import pyaudio
import wave
import os
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents

# === Configuration ===
CHUNK = 8000
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
OUTPUT_FILE = "recorded_audio.wav"  # Audio file to save

# Initialize PyAudio
p = pyaudio.PyAudio()
stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK)

# Initialize Deepgram client
deepgram = DeepgramClient(api_key="49630c797e6d4eede50979dfc25c9e629af77b10")
dg_connection = deepgram.listen.websocket.v("1")

full_transcript = ""
current_utterance = ""


# def on_message(self, result, **kwargs):
#     """Callback function for receiving transcriptions."""
#     global full_transcript, current_utterance
#     transcript = result.channel.alternatives[0].transcript
#     print(f"Transcript from DEEPGRAM: {transcript}")
    # if len(transcript)!=0:
    #     full_transcript += transcript
    #
    # print(f"Transcript till now: {full_transcript}")


    # # interim_result = result.channel.alternatives[0].transcript
    # # if interim_result == "":
    # #     print("No voice detected")
    # x = result.channel.alternatives[0].transcript
    # if len(x)==0  and  len(current_utterance)!=0 :
    #     print(f"current_utterance: {current_utterance}")
    #     current_utterance = ""
    #     print("###########################################################################################################################################################################3")
    #
    #
    # current_utterance = result.channel.alternatives[0].transcript + " "
    # # print(f"current utterance: {current_utterance} ")
    #
    # # if result.speech_final:
    # #     sentence = result.channel.alternatives[0].transcript
    # #     if sentence:
    # #         full_transcript += current_utterance + sentence + " "
    # #         print(f"Complete Transcript: {full_transcript}")
    # #         current_utterance = ""  # Reset for the next utterance
    # # elif result.is_final:
    # #     current_utterance += result.channel.alternatives[0].transcript + " "
    # #     print(f"Current Utterance: {current_utterance}")
    # # else:
    # #     # This is an interim result
    # #     print(f"Interim: {result.channel.alternatives[0].transcript}")


def on_message(self, result, **kwargs):
    """Callback function for receiving transcriptions."""
    global full_transcript, current_utterance
    transcript = result.channel.alternatives[0].transcript
    # print(f"Transcript from DEEPGRAM: {transcript}")
    if result.is_final:
        if transcript not in current_utterance:
            current_utterance += transcript + " "
            print(f"Current Utterance : {current_utterance}")
        if transcript == "" and len(current_utterance)!=0:
            print(f"No utterance found, final utterance is: {current_utterance}")

    #
    # if result.speech_final:
    #     # This is the end of an utterance, append it to full_transcript
    #     full_transcript += current_utterance + transcript + " "
    #     print(f"Complete Transcript: {full_transcript}")
    #     current_utterance = ""  # Reset for the next utterance
    # elif result.is_final:
    #     # This is a  part of the current utterance
    #     if transcript not in current_utterance:
    #         current_utterance += transcript + " "
    #     print(f"Current Utterance: {current_utterance}")
    # else:
    #     # This is an interim result, you can choose to print it or ignore
    #     print(f"Interim: {transcript}")

dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

# Set up Deepgram options
options = LiveOptions(
    model="nova-2",
    language="en-US",
    encoding="linear16",
    channels=CHANNELS,
    sample_rate=RATE,
    endpointing=1,
    vad_events=True,
    interim_results=True,
    utterance_end_ms="1000",
    punctuate=True
)

# Start the Deepgram connection
dg_connection.start(options)

print("Listening... Press Ctrl+C to stop.")

# === Record and Stream Audio ===
frames = []  # Store audio chunks

try:
    while True:
        data = stream.read(CHUNK)
        frames.append(data)  # Store recorded audio
        dg_connection.send(data)  # Send to Deepgram
except KeyboardInterrupt:
    print("Stopping...")

finally:
    # Stop PyAudio stream
    stream.stop_stream()
    stream.close()
    p.terminate()
    dg_connection.finish()

    # === Save Audio to a File ===
    with wave.open(OUTPUT_FILE, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

    print(f"Audio saved as: {OUTPUT_FILE}")
    print(f"Final Complete Transcript: {full_transcript}")