from openai import OpenAI
import os
import io
import numpy as np
import sounddevice as sd
from pydub import AudioSegment


client = OpenAI(api_key="***************************88")

output_text= "namaste, aap kaise hain ?"

mp3_bytes_io = io.BytesIO()
response = client.audio.speech.create(model="tts-1", voice="alloy", input=output_text)
print(f"Type of response --> {type(response)}")

for chunk in response.iter_bytes():
    print(f"type, {type(chunk)}chunk--> {chunk}")
    print('\n')
    mp3_bytes_io.write(chunk)
mp3_bytes_io.seek(0)

processed_data = mp3_bytes_io.getvalue()

audio = AudioSegment.from_file(mp3_bytes_io, format="mp3")
pcm_data = np.array(audio.get_array_of_samples(), dtype=np.int16)

# Play the audio
sd.play(pcm_data, samplerate=audio.frame_rate)
sd.wait()

print(processed_data)