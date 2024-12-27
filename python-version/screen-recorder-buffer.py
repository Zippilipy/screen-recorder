import os
import threading
import time
import wave

import cv2
import ffmpeg
import numpy as np
import bettercam
from collections import deque
import keyboard
import pyaudiowpatch as pyaudio
from pydub import AudioSegment
import helper

#Threading
buffer_lock = threading.Lock()
stop_event = threading.Event()

#Screen record
frame_rate = 30
buffer_duration = 60
buffer_size_video = frame_rate * buffer_duration
fourcc = cv2.VideoWriter_fourcc(*"XVID")
frame_buffer = deque(maxlen=buffer_size_video)
camera = bettercam.create(output_color="BGR")
camera.start(target_fps=30, video_mode=True)
screen_size = (camera.width, camera.height)

#Audio
CHUNK = 4096
FORMAT = pyaudio.paInt16

#System audio
system_audio = pyaudio.PyAudio()
default_speakers = helper.speakers(system_audio)
samplerate_system = int(default_speakers["defaultSampleRate"])
channels_system = default_speakers["maxInputChannels"]
buffer_size_system = int(buffer_duration * samplerate_system / CHUNK)
buffer_system = deque(maxlen=buffer_size_system)
system_stream = system_audio.open(format=FORMAT,
                                  channels=channels_system,
                                  rate=samplerate_system,
                                  frames_per_buffer=CHUNK,
                                  input=True,
                                  input_device_index=default_speakers["index"]
                                  )

#Microphone audio
microphone_audio = pyaudio.PyAudio()
default_mic = helper.get_mic(microphone_audio)
samplerate_mic = int(default_mic["defaultSampleRate"])
channels_mic = default_mic["maxInputChannels"]
buffer_size_mic = int(buffer_duration * samplerate_mic / CHUNK)
mic_buffer = deque(maxlen=buffer_size_mic)
microphone_stream = microphone_audio.open(format=FORMAT,
                               channels=channels_mic,
                               rate=samplerate_mic,
                               frames_per_buffer=CHUNK,
                               input=True,
                               input_device_index=default_mic["index"]
                               )

#Temporary files
mic_output = "mic.wav"
system_output = "device.wav"
screen_output = "screen.avi"
combined_output = "combined.mp3"

#Resulting file
final_output = "final.mp4"

def record_screen():
    print("Recording... Press 'q' to quit or 's' to save the last minute.")
    while not stop_event.is_set():
        frame_buffer.append(camera.get_latest_frame())

def record_audio_to_buffer():
    print(f"Recording from: ({default_speakers['index']}){default_speakers['name']}")
    while not stop_event.is_set():
        data = system_stream.read(CHUNK)
        buffer_system.append(data)

def record_mic_to_buffer():
    print(f"Recording from: ({default_mic['index']}){default_mic['name']}")
    while not stop_event.is_set():
        data = microphone_stream.read(CHUNK)
        mic_buffer.append(data)

def save_audio(output_file):
    """Save the audio stored in the circular buffer to a WAV file."""
    print(f"Saving audio to {output_file}...")

    # Combine all chunks in the buffer
    buffer_copy = list(buffer_system)
    combined_audio = b"".join(buffer_copy)

    # Save to a WAV file
    with wave.open(output_file, 'wb') as wf:
        wf.setnchannels(channels_system)
        wf.setsampwidth(pyaudio.get_sample_size(FORMAT))
        wf.setframerate(samplerate_system)
        wf.writeframes(combined_audio)

    print(f"Buffered audio saved to {output_file}")

def save_mic(output_file):
    """Save the audio stored in the circular buffer to a WAV file."""
    print(f"Saving audio to {output_file}...")

    # Combine all chunks in the buffer
    buffer_copy = list(mic_buffer)
    combined_audio = b"".join(buffer_copy)

    # Save to a WAV file
    with wave.open(output_file, 'wb') as wf:
        wf.setnchannels(channels_mic)
        wf.setsampwidth(pyaudio.get_sample_size(FORMAT))
        wf.setframerate(samplerate_mic)
        wf.writeframes(combined_audio)

    print(f"Buffered audio saved to {output_file}")


def save_screen():
    print(f"Saving video to {screen_output}")

    # Create a VideoWriter object
    out = cv2.VideoWriter(screen_output, fourcc, frame_rate, screen_size)

    # Write frames from the buffer
    buffer_copy = list(frame_buffer)
    for frame in buffer_copy:
        out.write(frame)
    out.release()
    print(f"Video saved to {screen_output}")

def merge_audio():
    print("Merging system and microphone audio...")
    sound1 = AudioSegment.from_file(mic_output, format="wav")
    sound2 = AudioSegment.from_file(system_output, format="wav")
    combined = sound1.overlay(sound2, position=0)
    file_handle = combined.export(combined_output, format="mp3")

def merge_video_and_audio():
    video = ffmpeg.input(screen_output).video
    audio = ffmpeg.input(combined_output).audio
    ffmpeg.output(audio, video, final_output, y=final_output, vcodec='copy', acodec='copy').run()

def update_framerate():
    global frame_rate
    global frame_buffer
    global buffer_size_video
    l1 = len(frame_buffer)
    time.sleep(1)
    frame_rate = len(frame_buffer) - l1
    buffer_size_video = frame_rate * buffer_duration
    frame_buffer = deque(frame_buffer, maxlen=buffer_size_video)

if __name__ == '__main__':
    stop = False
    system_thread = threading.Thread(target=record_audio_to_buffer)
    screen_thread = threading.Thread(target=record_screen)
    mic_thread = threading.Thread(target=record_mic_to_buffer)
    framerate_thread = threading.Thread(target=update_framerate)

    try:
        system_thread.start()
        screen_thread.start()
        mic_thread.start()
        framerate_thread.start()

        while not stop:
            if keyboard.is_pressed('p'):
                print(frame_rate)
            elif keyboard.is_pressed('s'):
                save_audio(system_output)
                save_mic(mic_output)
                save_screen()
                merge_audio()
                merge_video_and_audio()
                os.remove(system_output)
                os.remove(screen_output)
                os.remove(mic_output)
                os.remove(combined_output)
            elif keyboard.is_pressed('q'):
                stop_event.set()
                stop = True

    finally:
        system_thread.join()
        screen_thread.join()
        mic_thread.join()
        framerate_thread.join()

        system_stream.stop_stream()
        system_stream.close()
        system_audio.terminate()
        microphone_stream.stop_stream()
        microphone_stream.close()
        microphone_audio.terminate()
        cv2.destroyAllWindows()
        camera.stop()