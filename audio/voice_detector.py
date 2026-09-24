import numpy as np
from typing import Tuple, Optional

def detect_speaker(pcm_bytes: bytes, sample_rate: int = 16000) -> Tuple[str, Optional[float]]:
    """
    Analiza un búfer de audio PCM de 16 bits mono y estima la frecuencia fundamental (F0 / Pitch)
    mediante autocorrelación con filtro pasa-bajos, remuestreo a 16kHz y protección contra saltos de octava.
    
    Clasificación:
    - F0 < 175 Hz         -> 'hombre' (tono grave masculino adulto)
    - 175 <= F0 < 255 Hz  -> 'mujer' (tono medio/agudo femenino)
    - F0 >= 265 Hz        -> 'nino' (tono infantil confirmado con alta consistencia)
    - Caso dudoso / ruido -> 'hombre' (perfil predeterminado del dueño de la casa)
    
    Retorna: (tipo_hablante: str, pitch_mediano_hz: Optional[float])
    """
    if not pcm_bytes or len(pcm_bytes) < int(sample_rate * 0.2):  # Mínimo 200ms de audio
        return "hombre", None

    try:
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    except Exception:
        return "hombre", None

    # 1. Remuestreo/Decimación a ~16kHz si la frecuencia de entrada es 44.1k o 48k
    target_sr = 16000
    if sample_rate > 20000:
        # 1a. Anti-alias ANTES de diezmar (2026-09-15): sin este pasa-bajos,
        # los tonos ultrasónicos (fuentes switching, backlights, ~16-17 kHz)
        # se pliegan a la banda vocal al diezmar y falsean la detección.
        aa_kernel = np.ones(9, dtype=np.float32) / 9.0
        samples = np.convolve(samples, aa_kernel, mode="same")
        step = int(round(sample_rate / target_sr))
        samples = samples[::step]
        actual_sr = float(sample_rate / step)
    else:
        actual_sr = float(sample_rate)

    if len(samples) < 1024:
        return "hombre", None

    # 1b. Filtro peine anti-hum de red (2026-09-15): y[n] = x[n] - x[n-K] con
    # K = sr/50 pone nulos en 50, 100, 150... Hz. Los mics baratos suelen
    # captar zumbido eléctrico de la red; como el rango de búsqueda (75-380 Hz)
    # excluye los 50 Hz pero no sus armónicos, el detector se enganchaba de
    # esos armónicos y clasificaba mal (p. ej. "niño" a 386.8 Hz).
    k_hum = max(1, int(round(actual_sr / 50.0)))
    if len(samples) > k_hum:
        samples = samples[k_hum:] - samples[:-k_hum]

    # 2. Filtro pasa-bajos simple (media móvil de 5 muestras) para atenuar armónicos altos
    # y evitar que los formantes de 300-800 Hz superen la frecuencia fundamental en micrófonos baratos
    kernel = np.ones(5, dtype=np.float32) / 5.0
    filtered = np.convolve(samples, kernel, mode="same")

    win_size = 1024  # 64ms de ventana a 16kHz (cubre holgadamente ciclos de 75 a 380 Hz)
    hop_size = 512
    # Rango de lag para F0 humana (75 Hz a 380 Hz)
    min_lag = max(2, int(actual_sr / 380))
    max_lag = min(win_size - 1, int(actual_sr / 75))

    if min_lag >= max_lag:
        return "hombre", None

    pitches = []

    for i in range(0, len(filtered) - win_size, hop_size):
        w = filtered[i : i + win_size]
        rms = np.sqrt(np.mean(w ** 2))
        
        # Ignorar silencio o ruido de fondo bajo
        if rms < 250:
            continue

        corr = np.correlate(w, w, mode="full")
        corr = corr[len(corr) // 2 :]

        if corr[0] <= 0:
            continue

        norm_corr = corr / corr[0]
        sub = norm_corr[min_lag:max_lag]
        if len(sub) == 0:
            continue

        best_idx = int(np.argmax(sub))
        best_val = sub[best_idx]
        lag = min_lag + best_idx

        # Un pico justo en el borde del rango de búsqueda es artefacto
        # (ruido de banda ancha/tonos fuera de rango), no un pitch real:
        # se descarta la ventana en vez de informar un pitch falso.
        if lag == min_lag or lag == max_lag - 1:
            continue

        # Umbral de periodicidad mínima (autocorrelación normalizada)
        if best_val > 0.32 and lag > 0:
            pitch = actual_sr / lag
            if 70 <= pitch <= 400:
                pitches.append(pitch)

    if not pitches:
        return "hombre", None

    med_pitch = float(np.median(pitches))

    if med_pitch < 175.0:
        return "hombre", round(med_pitch, 1)
    elif med_pitch < 260.0:
        return "mujer", round(med_pitch, 1)
    elif len(pitches) >= 6:
        # Frecuencias >= 260 Hz con consistencia temporal corresponden a voces infantiles
        return "nino", round(med_pitch, 1)
    else:
        # Registro agudo femenino sin suficientes ventanas infantiles
        return "mujer", round(med_pitch, 1)


def format_speaker_prompt_tag(speaker_type: str, pitch_hz: Optional[float] = None) -> str:
    """
    Genera la instrucción contextual para inyectar en Gemini indicando quién está hablando.
    Solo restringe cuando se detecta fehacientemente un menor/niño para modo ATP.
    """
    if speaker_type == "nino":
        hz_str = f" ({pitch_hz} Hz)" if pitch_hz else ""
        return f"[VOZ DETECTADA: Menor{hz_str} - Tono infantil]. Adaptá tu trato hacia un niño/a sin insultos."
    return ""
