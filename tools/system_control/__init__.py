"""Paquete SystemControl (control de la PC Windows).

Fachada compatible: re-exporta `system_control` y `SystemControl`
como antes, así ningún import externo cambia.
"""

from .base import SystemControlBase
from .audio import AudioMixin
from .spotify import SpotifyMixin
from .soccer import SoccerMixin
from .web import WebMixin
from .windows import WindowsMixin
from .power import PowerMixin
from .sysadmin import SysAdminMixin

class SystemControl(SystemControlBase, AudioMixin, SpotifyMixin, SoccerMixin, WebMixin, WindowsMixin, PowerMixin, SysAdminMixin):
    """Clase final: compone todos los mixins. Sin lógica propia."""


system_control = SystemControl()
