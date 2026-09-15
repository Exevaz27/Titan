import os
import math
import struct
import wave
from pathlib import Path

def generate_sfx_files(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_rate = 44100

    # 1. rebel_on.wav: Distorsion agresiva descendente + zumbido
    path_on = output_dir / "rebel_on.wav"
    duration_on = 0.55
    num_samples_on = int(sample_rate * duration_on)
    with wave.open(str(path_on), 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(num_samples_on):
            t = i / sample_rate
            freq = 280.0 - (190.0 * (t / duration_on))
            val = 0.55 * math.sin(2.0 * math.pi * freq * t)
            val += 0.30 * math.sin(4.0 * math.pi * freq * t)
            val += 0.15 * (1.0 if math.sin(2.0 * math.pi * (freq * 0.5) * t) > 0 else -1.0)
            env = math.exp(-2.5 * t)
            sample = int(val * env * 28000)
            sample = max(-32767, min(32767, sample))
            wav.writeframes(struct.pack('<h', sample))

    # 2. rebel_off.wav: Acorde armonico zen / campana tibetana suave
    path_off = output_dir / "rebel_off.wav"
    duration_off = 0.85
    num_samples_off = int(sample_rate * duration_off)
    with wave.open(str(path_off), 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(num_samples_off):
            t = i / sample_rate
            val = (0.50 * math.sin(2.0 * math.pi * 528.0 * t) +
                   0.35 * math.sin(2.0 * math.pi * 660.0 * t) +
                   0.15 * math.sin(2.0 * math.pi * 792.0 * t))
            env = math.exp(-3.2 * t)
            sample = int(val * env * 26000)
            sample = max(-32767, min(32767, sample))
            wav.writeframes(struct.pack('<h', sample))

    # 3. slap.wav: Bofetada / golpe seco
    path_slap = output_dir / "slap.wav"
    duration_slap = 0.22
    num_samples_slap = int(sample_rate * duration_slap)
    import random
    with wave.open(str(path_slap), 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(num_samples_slap):
            t = i / sample_rate
            noise = (random.random() * 2.0 - 1.0) * 0.6
            thump = math.sin(2.0 * math.pi * (160.0 - 120.0 * (t / duration_slap)) * t) * 0.4
            env = math.exp(-18.0 * t)
            val = (noise + thump) * env
            sample = int(val * 30000)
            sample = max(-32767, min(32767, sample))
            wav.writeframes(struct.pack('<h', sample))

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    sfx_dir = base_dir / "sfx"
    generate_sfx_files(sfx_dir)
    print(f"SFX generados exitosamente en {sfx_dir}")
