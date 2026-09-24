"""Mixin de audio: volumen, mute y voz de la PC."""

from core.logger import log_error

import os

from core.state_manager import state_mgr, AssistantState

from typing import Any, Dict, Optional


class AudioMixin:

    def get_volume(self) -> int:
        if self._volume_interface:
            try:
                current = self._volume_interface.GetMasterVolumeLevelScalar()
                return int(round(current * 100))
            except Exception:
                pass
        return 50

    def set_volume_silent(self, level: int):
        """Ajusta el volumen de forma silenciosa (sin emitir eventos ni cambiar estado), para ducking de audio"""
        level = max(0, min(100, level))
        if self._volume_interface:
            try:
                self._volume_interface.SetMasterVolumeLevelScalar(level / 100.0, None)
            except Exception:
                pass

    def set_volume(self, level: int) -> Dict[str, Any]:
        """Ajusta el volumen del sistema de 0 a 100"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("set_volume", {"level": level}, f"Puse el volumen al {level}%.")
            if remote_res:
                return remote_res
        state_mgr.set_state(AssistantState.EXECUTING_TOOL, f"Ajustando volumen al {level}%...")
        level = max(0, min(100, level))
        if self._volume_interface:
            try:
                self._volume_interface.SetMasterVolumeLevelScalar(level / 100.0, None)
                msg = f"Volumen puesto al {level}%."
                state_mgr.emit_tool_call("set_volume", {"level": level}, msg)
                return {"status": "success", "message": msg, "level": level}
            except Exception as e:
                log_error(f"Error pycaw: {e}")

        return {
            "status": "error",
            "message": "No pude ajustar el volumen porque la interfaz de audio no está disponible.",
            "level": level,
        }

    def volume_up(self, step: int = 15) -> Dict[str, Any]:
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("volume_up", {"step": step}, f"Subí el volumen.")
            if remote_res:
                return remote_res
        curr = self.get_volume()
        new_vol = min(100, curr + step)
        return self.set_volume(new_vol)

    def volume_down(self, step: int = 15) -> Dict[str, Any]:
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("volume_down", {"step": step}, f"Bajé el volumen.")
            if remote_res:
                return remote_res
        curr = self.get_volume()
        new_vol = max(0, curr - step)
        return self.set_volume(new_vol)

    def mute(self, mute_state: Optional[bool] = None) -> Dict[str, Any]:
        """Mutea o desmutea el audio"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("mute", {}, "Audio muteado/desmuteado.")
            if remote_res:
                return remote_res
        if self._volume_interface:
            try:
                is_muted = self._volume_interface.GetMute()
                target = not is_muted if mute_state is None else mute_state
                self._volume_interface.SetMute(1 if target else 0, None)
                estado = "muteado" if target else "desmuteado"
                msg = f"Audio {estado}."
                state_mgr.emit_tool_call("mute", {"target": target}, msg)
                return {"status": "success", "message": msg, "muted": target}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {
            "status": "error",
            "message": "No pude acceder a la interfaz de audio para cambiar el estado de mute.",
        }

    def toggle_pc_voice(self) -> Dict[str, Any]:
        """Activa o desactiva la salida de voz de Titán en la PC Principal Windows (por defecto sale por DDR3)"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("toggle_pc_voice", {}, "Cambié el estado de la voz en la PC Principal.")
            if remote_res:
                return remote_res
            return {"status": "warning", "message": "El satélite en Windows no está conectado."}
        # H-5: delega en set_pc_voice para no duplicar la lógica local
        # (el punto de entrada se conserva: lo usa el botón del HUD y el RPC).
        return self.set_pc_voice(not self.pc_voice_enabled)

    def set_pc_voice(self, enabled: bool) -> Dict[str, Any]:
        """Establece explícitamente si la voz de Titán sale por la PC Principal Windows"""
        if os.name != 'nt':
            remote_res = self._remote_exec_if_linux("set_pc_voice", {"enabled": enabled}, "Ajusté la voz en la PC Principal.")
            if remote_res:
                return remote_res
            return {"status": "warning", "message": "El satélite en Windows no está conectado."}
        # B-26: éxito real — antes devolvía "Comando recibido en Windows" sin hacer nada.
        self.pc_voice_enabled = bool(enabled)
        st = "activada" if self.pc_voice_enabled else "silenciada"
        msg = f"Voz de Titán en la PC Principal {st}."
        state_mgr.emit_tool_call("set_pc_voice", {"enabled": enabled}, msg)
        return {"status": "success", "enabled": self.pc_voice_enabled, "message": msg}
