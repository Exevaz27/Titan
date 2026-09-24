import os
from pathlib import Path
from core.logger import log_info, log_warning

ASSETS_DIR = Path(__file__).parent.parent / "assets"
ICON_PATH = ASSETS_DIR / "titan.ico"

class NotificationService:
    def __init__(self):
        self.app_id = "Titán Asistente"
        self._enabled = True

    def notify(self, title: str, message: str, icon_path: str = None):
        """Muestra una notificación nativa Toast en la esquina inferior derecha de Windows"""
        if not self._enabled:
            return

        icon = icon_path or str(ICON_PATH) if ICON_PATH.exists() else None

        try:
            from winotify import Notification, audio
            toast = Notification(
                app_id=self.app_id,
                title=title,
                msg=message,
                icon=icon if icon and os.path.exists(icon) else ""
            )
            toast.set_audio(audio.Default, loop=False)
            toast.show()
        except Exception as e:
            # Fallback a PowerShell si winotify falla
            try:
                from core.process_utils import run_silent
                # S-17: title/message se interpolaban sin escape dentro del
                # script (una comilla " lo rompía; inyección si el texto
                # viniera de una fuente no confiable). En strings PowerShell
                # con comillas dobles hay que escapar `, $ y ".
                ps_title = str(title).replace("`", "``").replace("$", "`$").replace('"', '`"')
                ps_message = str(message).replace("`", "``").replace("$", "`$").replace('"', '`"')
                ps_script = f"""
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
                $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
                $texts = $template.GetElementsByTagName("text")
                $texts.Item(0).AppendChild($template.CreateTextNode("{ps_title}")) > $null
                $texts.Item(1).AppendChild($template.CreateTextNode("{ps_message}")) > $null
                $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{self.app_id}").Show($toast)
                """
                run_silent(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, timeout=2)
            except Exception as ps_err:
                log_warning(f"No se pudo mostrar notificación Windows: {e} | {ps_err}")

notifier = NotificationService()
