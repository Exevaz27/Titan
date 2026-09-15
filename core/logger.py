import sys
from datetime import datetime

# Asegurar codificación UTF-8 en Windows
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

class TermColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"

def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")

def log_info(msg: str):
    print(f"{TermColors.DIM}[{_timestamp()}]{TermColors.RESET} {TermColors.CYAN}[INFO]{TermColors.RESET} {msg}", flush=True)

def log_success(msg: str):
    print(f"{TermColors.DIM}[{_timestamp()}]{TermColors.RESET} {TermColors.GREEN}[OK]{TermColors.RESET} {msg}", flush=True)

def log_warning(msg: str):
    print(f"{TermColors.DIM}[{_timestamp()}]{TermColors.RESET} {TermColors.YELLOW}[ALERTA]{TermColors.RESET} {msg}", flush=True)

def log_error(msg: str):
    print(f"{TermColors.DIM}[{_timestamp()}]{TermColors.RESET} {TermColors.RED}[ERROR]{TermColors.RESET} {msg}", file=sys.stderr, flush=True)

def log_state(state: str, detail: str = ""):
    colors = {
        "IDLE": TermColors.BLUE,
        "LISTENING": TermColors.GREEN,
        "PROCESSING": TermColors.MAGENTA,
        "EXECUTING_TOOL": TermColors.CYAN,
        "SPEAKING": TermColors.YELLOW,
        "ERROR": TermColors.RED
    }
    col = colors.get(state, TermColors.BOLD)
    extra = f" - {detail}" if detail else ""
    print(f"{TermColors.DIM}[{_timestamp()}]{TermColors.RESET} {col}● [{state}]{TermColors.RESET}{extra}", flush=True)
