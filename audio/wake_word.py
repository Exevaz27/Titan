import re
from typing import Tuple, Optional, List
from core.config import config

class WakeWordDetector:
    def __init__(self):
        self.wake_words: List[str] = [w.lower() for w in config.wake_words]

    def reload(self):
        self.wake_words = [w.lower() for w in config.wake_words]

    def check(self, text: str, strict_start: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Comprueba si el texto contiene una palabra clave de activación.
        Retorna (detectado: bool, comando_restante: Optional[str]).
        
        Si strict_start es True (ej. cuando hay música sonando), la palabra clave debe
        estar al inicio absoluto de la frase para evitar falsos positivos con letras de canciones.
        """
        if not text:
            return False, None

        clean_text = text.strip().lower()
        clean_text = re.sub(r'^[¡!¿?\.,;:\s]+', '', clean_text)

        sorted_keywords = sorted(self.wake_words, key=len, reverse=True)

        for kw in sorted_keywords:
            pattern = rf'(?:^|\b){re.escape(kw)}(?:\b|$)'
            match = re.search(pattern, clean_text)
            if match:
                before = clean_text[:match.start()].strip(" ,.:;!?")
                after = clean_text[match.end():].strip(" ,.:;!?")
                remainder = f"{before} {after}".strip()
                # Si el resto solo contiene muletillas, artículos o prefijos comunes, tratarlo como invocación pura
                rem_lower = remainder.lower().strip()
                filler_set = {
                    "che", "eh", "y", "ah", "ey", "eu", "oye", "hola", "che che",
                    "un", "una", "uno", "el", "la", "los", "las", "al", "del", "de",
                    "a ver", "bueno", "dale", "a ver che", "che bueno"
                }
                if rem_lower in filler_set or len(rem_lower) <= 2:
                    remainder = ""
                else:
                    # Limpiar prefijos de muletilla al inicio del comando
                    for filler in ["che ", "eh ", "y ", "ah ", "ey ", "eu ", "oye ", "un ", "el ", "la ", "a ver ", "bueno "]:
                        if remainder.lower().startswith(filler):
                            remainder = remainder[len(filler):].strip()
                    if len(remainder.strip()) <= 2 or remainder.lower().strip() in filler_set:
                        remainder = ""
                return True, remainder

        return False, None

# Frases COMPUESTAS para interrupción / Barge-In (NUNCA palabras sueltas aisladas)
BARGE_IN_PHRASES: List[str] = [
    # Interpelación / Atención directa
    "ehu titán", "ehu titan", "eu titán", "eu titan", "eh titán", "eh titan", "ey titán", "ey titan",
    "che titán", "che titan", "oye titán", "oye titan", "hola titán", "hola titan",
    # Parar / Frenar
    "pará titán", "para titan", "titán pará", "titan para",
    "pará un poco titán", "para un poco titan", "pará un toque titán", "para un toque titan",
    "pará la mano titán", "para la mano titan", "frená titán", "frena titan", "titán frená", "titan frena",
    # Callar / Silenciar / Basta
    "callate titán", "callate titan", "cállate titán", "cállate titan", "titán callate", "titan callate",
    "silencio titán", "silencio titan", "titán silencio", "titan silencio",
    "basta titán", "basta titan", "titán basta", "titan basta",
    # Escuchar / Esperar
    "escuchá titán", "escucha titan", "titán escuchá", "titan escucha",
    "escuchame titán", "escuchame titan", "titán escuchame", "titan escuchame",
    "esperá titán", "espera titan", "titán esperá", "titan espera",
    "bancá titán", "banca titan", "bancame titán", "bancame titan", "bancá un toque titán"
]

def check_barge_in_phrase(text: str) -> Tuple[bool, Optional[str]]:
    """
    Verifica si el texto contiene una frase COMPUESTA explícita de interrupción (Barge-In).
    NUNCA se activa con palabras sueltas como 'titán', 'pará' o 'callate'.
    Retorna (es_barge_in: bool, frase_encontrada: Optional[str]).
    """
    if not text:
        return False, None
    clean = text.lower().strip()
    clean = re.sub(r'^[¡!¿?\.,;:\s]+', '', clean)

    from core.config import config
    name = config.assistant_name.lower().strip()
    all_phrases = list(BARGE_IN_PHRASES)

    # Si se configuró otro nombre distinto a Titán, expandir también sus frases compuestas
    if name and name not in ["titán", "titan"]:
        for prefix in [
            "ehu", "eu", "eh", "ey", "che", "oye", "pará", "para", "callate", "cállate",
            "escuchá", "escucha", "escuchame", "basta", "silencio", "frená", "frena", "esperá", "espera", "bancá", "banca"
        ]:
            all_phrases.append(f"{prefix} {name}")
            all_phrases.append(f"{name} {prefix}")

    # Ordenar por longitud descendente para matchear frases más largas primero
    all_phrases.sort(key=len, reverse=True)

    for phrase in all_phrases:
        if re.search(rf'(?:^|\b){re.escape(phrase)}(?:\b|$)', clean):
            return True, phrase

    return False, None

wake_detector = WakeWordDetector()

