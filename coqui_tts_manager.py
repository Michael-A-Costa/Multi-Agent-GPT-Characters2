# CoquiTTSManager: Wrapper for Coqui TTS
from TTS.api import TTS
import os
import soundfile as sf
from pydub import AudioSegment

class CoquiTTSManager:
    def __init__(self, model_name="tts_models/en/ljspeech/tacotron2-DDC", gpu=False):
        self.tts = TTS(model_name=model_name, progress_bar=False, gpu=gpu)
        self.sample_rate = self.tts.synthesizer.output_sample_rate
        # Print available voices for this TTS model
        # if hasattr(self.tts, 'speakers') and self.tts.speakers:
        #     print(f"[cyan]Available voices for model '{model_name}': {self.tts.speakers}")
        # else:
        #     print(f"[yellow]No speaker list found for model '{model_name}'.")

    def text_to_audio(self, input_text, save_as_wave=True, subdirectory="audio_msg", speaker=None, speedup=1.15):
        if speaker:
            print(f"[blue]CoquiTTSManager: Using speaker '{speaker}' for synthesis.")
            wav = self.tts.tts(input_text, speaker=speaker)
        else:
            wav = self.tts.tts(input_text)
        # Ensure the subdirectory exists
        output_dir = os.path.join(os.path.abspath(os.curdir), subdirectory)
        os.makedirs(output_dir, exist_ok=True)
        if save_as_wave:
            file_name = f"___Msg{str(hash(input_text))}.wav"
            tts_file = os.path.join(output_dir, file_name)
            sf.write(tts_file, wav, self.sample_rate)
            # Speed up audio with pydub if needed
            if speedup != 1.0:
                sound = AudioSegment.from_wav(tts_file)
                so = sound.speedup(playback_speed=speedup, chunk_size=150, crossfade=25)
                so.export(tts_file, format="wav")
        else:
            file_name = f"___Msg{str(hash(input_text))}.mp3"
            tts_file = os.path.join(output_dir, file_name)
            sf.write(tts_file, wav, self.sample_rate)
            # Speed up audio with pydub if needed
            if speedup != 1.0:
                sound = AudioSegment.from_file(tts_file)
                so = sound.speedup(playback_speed=speedup, chunk_size=150, crossfade=25)
                so.export(tts_file, format="mp3")
        return tts_file
