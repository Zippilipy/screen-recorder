import cv2
import mss
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
import pyaudiowpatch as pyaudio
import wave
import time
import threading
from pydub import AudioSegment
import ffmpeg
import os

# Video settings
fourcc = cv2.VideoWriter_fourcc(*"XVID")
fps = 30.0
screen_output = "screen_record.avi"

# Audio settings
p = pyaudio.PyAudio()
dev_index = 0
for i in range(p.get_device_count()):
    dev = p.get_device_info_by_index(i)
    if (dev['name'] == 'Stereo Mix (Realtek High Defini' and dev['hostApi'] == 0):
        dev_index = dev['index'];
FORMAT = pyaudio.paInt16
CHUNK = 2048
CHANNELS = 2
samplerate = 44100
duration = 10
mic_output = "mic_audio.wav"
system_output = "loopback_record.wav"

# Output files
combined_audio = "combined_audio.mp3"
final_output = "final_output.mp4"

# Function to record audio
def record_microphone():
    print("Recording microphone audio...")
    mic_audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, device=1)  # Set device to your microphone
    sd.wait()
    write(mic_output, samplerate, mic_audio)
    print("Microphone recording finished.")

# Record audio from the system (loopback)
def record_system_audio():
    try:
        # Get default WASAPI info
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        print("Looks like WASAPI is not available on the system. Exiting...")
        exit()
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])

    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            """
            Try to find loopback device with same name(and [Loopback suffix]).
            Unfortunately, this is the most adequate way at the moment.
            """
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback
                break
        else:
            print(
                "Default loopback output device not found.\n\nRun `python -m pyaudiowpatch` to check available devices.\nExiting...\n")
            exit()

    print(f"Recording from: ({default_speakers['index']}){default_speakers['name']}")

    wave_file = wave.open(system_output, 'wb')
    wave_file.setnchannels(default_speakers["maxInputChannels"])
    wave_file.setsampwidth(pyaudio.get_sample_size(pyaudio.paInt16))
    wave_file.setframerate(int(default_speakers["defaultSampleRate"]))

    def callback(in_data, frame_count, time_info, status):
        """Write frames and return PA flag"""
        wave_file.writeframes(in_data)
        return (in_data, pyaudio.paContinue)

    with p.open(format=FORMAT,
                channels=default_speakers["maxInputChannels"],
                rate=int(default_speakers["defaultSampleRate"]),
                frames_per_buffer=CHUNK,
                input=True,
                input_device_index=default_speakers["index"],
                stream_callback=callback
                ) as stream:
        """
        Opena PA stream via context manager.
        After leaving the context, everything will
        be correctly closed(Stream, PyAudio manager)            
        """
        print(f"The next {duration} seconds will be written to {system_output}")
        time.sleep(duration)  # Blocking execution while playing

    wave_file.close()

# Function to record screen
def record_screen():
    print("Recording screen...")

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screen_width = monitor["width"]
        screen_height = monitor["height"]

        out = cv2.VideoWriter(screen_output, fourcc, fps, (screen_width, screen_height))

        frame_duration = 1/fps
        start_time = time.time()

        for _ in range(int(fps*duration)):
            frame_start = time.time()
            img = np.array(sct.grab(monitor))
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            out.write(frame)

            # Sleep to maintain frame rate
            elapsed = time.time() - frame_start
            time.sleep(max(0, frame_duration - elapsed))

        out.release()
        print("Screen recording finished.")

def merge_audio():
    print("Merging system and microphone audio...")
    sound1 = AudioSegment.from_file(mic_output, format="wav")
    sound2 = AudioSegment.from_file(system_output, format="wav")
    combined = sound1.overlay(sound2, position=0)
    file_handle = combined.export(combined_audio, format="mp3")

def merge_video_and_audio():
    video = ffmpeg.input(screen_output).video
    audio = ffmpeg.input(combined_audio).audio
    ffmpeg.output(audio, video, final_output, y=final_output, vcodec='copy', acodec='copy').run()

if __name__ == '__main__':
    mic_thread = threading.Thread(target=record_microphone)
    system_thread = threading.Thread(target=record_system_audio)
    screen_thread = threading.Thread(target=record_screen)

    mic_thread.start()
    system_thread.start()
    screen_thread.start()

    mic_thread.join()
    system_thread.join()
    screen_thread.join()

    merge_audio()
    merge_video_and_audio()

    os.remove(mic_output)
    os.remove(system_output)
    os.remove(screen_output)
    os.remove(combined_audio)