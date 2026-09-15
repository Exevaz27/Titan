import os
import subprocess

def get_silent_flags():
    """Retorna creationflags y startupinfo para ejecutar subprocesos sin ventanas en Windows"""
    if os.name == 'nt':
        flags = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return flags, si
    return 0, None

def run_silent(cmd, **kwargs):
    """Ejecuta un comando sin abrir ninguna ventana de consola negra (CMD) en Windows"""
    if os.name == 'nt':
        flags = kwargs.pop('creationflags', 0) | subprocess.CREATE_NO_WINDOW
        si = kwargs.pop('startupinfo', None)
        if si is None:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
        return subprocess.run(cmd, creationflags=flags, startupinfo=si, **kwargs)
    return subprocess.run(cmd, **kwargs)

def popen_silent(cmd, **kwargs):
    """Lanza un proceso en segundo plano sin abrir ventana de consola (CMD) en Windows"""
    if os.name == 'nt':
        flags = kwargs.pop('creationflags', 0) | subprocess.CREATE_NO_WINDOW
        si = kwargs.pop('startupinfo', None)
        if si is None:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
        return subprocess.Popen(cmd, creationflags=flags, startupinfo=si, **kwargs)
    return subprocess.Popen(cmd, **kwargs)
