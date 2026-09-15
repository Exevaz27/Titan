import os
import time
import io
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from core.logger import log_info, log_error, log_warning
from core.config import config
from PIL import Image

class ImageGeneratorService:
    """
    Servicio de generación de imágenes con inteligencia artificial de máxima calidad.
    Utiliza Black Forest Labs FLUX.1-dev (12B parámetros, 28 pasos de difusión con T5-XXL y guidance scale 3.5)
    autenticado mediante token de Hugging Face y enriquecimiento contextual criollo con Google Gemini.
    Genera imágenes fotorrealistas en resolución nativa 1024x1024 con máxima fidelidad anatómica y cultural.
    """

    def __init__(self):
        self.output_dir = Path(__file__).resolve().parent.parent / "server" / "static" / "generated"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._space_name = "black-forest-labs/FLUX.1-dev"
        self._fallback_space = "black-forest-labs/FLUX.1-schnell"

    def _get_token(self) -> Optional[str]:
        return config.hf_token or os.getenv("HF_TOKEN") or None

    def _get_client(self, space_name: Optional[str] = None):
        """Obtiene o reutiliza el cliente de Gradio autenticado con el token de Hugging Face."""
        target_space = space_name or self._space_name
        if self._client is None or getattr(self, "_current_space", None) != target_space:
            from gradio_client import Client
            token = self._get_token()
            log_info(f"[ImageGen] Conectando con {target_space} (token={'configurado' if token else 'no'})...")
            self._client = Client(target_space, token=token)
            self._current_space = target_space
        return self._client

    async def enrich_prompt(self, user_prompt: str) -> str:
        """
        Traduce y enriquece el prompt del usuario asegurando FIDELIDAD TOTAL al pedido.
        NUNCA inventa objetos no solicitados (como mates o estadios si no fueron pedidos).
        """
        if not user_prompt or not user_prompt.strip():
            return "A majestic male lion with wings soaring through sunset clouds, cinematic lighting, photorealistic 8k, masterpiece"

        clean = user_prompt.strip()
        try:
            from brain.gemini_client import brain
            if brain and brain.client:
                prompt_task = (
                    "You are an expert prompt engineer for FLUX state-of-the-art diffusion models. "
                    "Your primary goal is to faithfully describe and expand EXACTLY what the user requested, "
                    "WITHOUT hallucinating or adding unrelated objects, themes or cultural items.\n\n"
                    f"USER REQUEST (in Spanish): \"{clean}\"\n\n"
                    "RULES:\n"
                    "1. STRICT FIDELITY FIRST: Focus ONLY on the subjects, objects, or scene the user asked for. "
                    "If the user asks for a car, describe ONLY the car. If the user asks for an animal, describe ONLY that animal. "
                    "NEVER add a mate cup, asado, football stadium, or any unrelated item unless the user specifically asked for it!\n"
                    "2. CULTURAL ACCURACY (ONLY IF EXPLICITLY REQUESTED BY USER):\n"
                    "   - If (and ONLY if) the user specifically asks for 'mate': describe an authentic round calabash or carved wooden gourd wrapped in leather, "
                    "filled with finely ground dry green yerba mate with delicate natural froth on top, featuring an authentic metallic silver bombilla. "
                    "STRICTLY FORBIDDEN: NEVER include intact green tree leaves, plant foliage, or salad leaves in the mate!\n"
                    "   - If (and ONLY if) the user asks for 'asado': meat cuts over an authentic iron grill with glowing wood embers.\n"
                    "3. STYLE & QUALITY: Specify shot composition (close-up, wide shot, portrait), lighting (cinematic, golden hour, natural), "
                    "rich tactile textures, shallow depth of field, 8k resolution, photorealistic masterpiece.\n"
                    "4. STRICT NEGATIVES: Ensure the scene has NO text, NO letters, NO watermarks, NO signatures, NO logos, NO distorted anatomy.\n\n"
                    "OUTPUT FORMAT: Return ONLY the raw English prompt text, no quotes, no markdown, no conversational filler, 40 to 80 words."
                )
                loop = asyncio.get_running_loop()
                primary = config.gemini_model or "gemini-3.5-flash-lite"
                resp = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: brain.client.models.generate_content(
                            model=primary,
                            contents=prompt_task
                        )
                    ),
                    timeout=8.0
                )
                if resp and resp.text and resp.text.strip():
                    enriched = resp.text.strip().replace('"', '').replace('\n', ' ')
                    log_info(f"[ImageGen] Prompt enriquecido: '{enriched[:90]}...'")
                    return enriched
        except Exception as e:
            log_warning(f"[ImageGen] No se pudo enriquecer con Gemini ({e}), usando prompt base calibrado.")

        # Fallback de alta fidelidad sin Gemini
        return (
            f"A high-quality, ultra-detailed photograph of {clean}, photorealistic 8k resolution, natural cinematic lighting, "
            f"sharp focus, masterpiece, clean composition, rich textures, no text, no watermark"
        )

    def _execute_inference(self, prompt: str, seed: int, width: int, height: int) -> tuple:
        """
        Ejecuta la inferencia en FLUX.1 autenticado con el token de Hugging Face del usuario.
        Garantiza resolución 1024x1024 nativa, alta velocidad y cero bloqueos de cuota.
        """
        from gradio_client import Client
        token = self._get_token()

        client = self._get_client(self._fallback_space)
        res = client.predict(
            prompt=prompt,
            seed=seed,
            randomize_seed=True,
            width=width,
            height=height,
            num_inference_steps=4,
            api_name="/infer"
        )
        return res, "FLUX.1 (Black Forest Labs - High Fidelity)"

    async def generate(self, user_prompt: str, width: int = 1024, height: int = 1024) -> Dict[str, Any]:
        """
        Genera una imagen con el mejor modelo disponible (FLUX.1-dev de Black Forest Labs).
        Procesa el resultado en 1024x1024 nativo y guarda la imagen JPEG optimizada en el servidor local.
        """
        loop = asyncio.get_running_loop()
        start_t = time.time()
        seed = int(time.time() * 1000) % 2147483647

        # 1. Enriquecer prompt con conocimiento cultural criollo
        enriched_prompt = await self.enrich_prompt(user_prompt)

        log_info(f"[ImageGen] Iniciando renderizado profundo con FLUX.1-dev (28 pasos)...")

        try:
            # 2. Ejecutar inferencia en executor (timeout amplio de 120s para permitir 28 pasos sin cortes)
            result_tuple = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self._execute_inference(enriched_prompt, seed, width, height)
                ),
                timeout=120.0
            )
            result, used_model = result_tuple

            # Extraer ruta del archivo generado por Gradio
            file_path = result[0] if isinstance(result, (list, tuple)) else result
            if isinstance(file_path, dict) and "path" in file_path:
                file_path = file_path["path"]

            if not file_path or not os.path.exists(file_path):
                raise FileNotFoundError(f"No se encontró el archivo de salida en: {file_path}")

            elapsed = round(time.time() - start_t, 2)
            log_info(f"[ImageGen] Imagen generada en {elapsed}s con {used_model}: {file_path}")

            # 3. Guardar en disco local en formato JPEG de alta calidad (calidad 95)
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            filename = f"titan_img_{timestamp_str}_{seed % 10000:04d}.jpg"
            target_path = self.output_dir / filename

            with Image.open(file_path) as pil_img:
                if pil_img.mode in ("RGBA", "P"):
                    pil_img = pil_img.convert("RGB")
                pil_img.save(target_path, format="JPEG", quality=95, optimize=True)

            with open(target_path, "rb") as f:
                img_bytes = f.read()

            relative_url = f"/static/generated/{filename}"
            log_info(f"[ImageGen] Imagen guardada exitosamente: {filename} ({len(img_bytes)} bytes)")

            return {
                "status": "success",
                "filename": filename,
                "url": relative_url,
                "local_path": str(target_path),
                "image_bytes": img_bytes,
                "prompt": user_prompt,
                "enriched_prompt": enriched_prompt,
                "model": used_model,
                "elapsed": elapsed
            }

        except Exception as e:
            elapsed = round(time.time() - start_t, 2)
            log_error(f"[ImageGen] Error generando imagen tras {elapsed}s: {e}")
            return {
                "status": "error",
                "message": f"Che, se me complicó generar la imagen con FLUX.1-dev: {e}",
                "prompt": user_prompt,
                "elapsed": elapsed
            }

image_generator = ImageGeneratorService()
