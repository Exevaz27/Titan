"""Paquete de herramientas (function calling de Gemini).

Fachada compatible: re-exporta todo lo que antes vivía en
brain/tool_registry.py, así ningún import externo cambia.
"""

__all__ = [
    "_clamp",
    "_remember_file",
    "AVAILABLE_TOOLS",
    "TOOLS_MAP",
    "add_note",
    "analyze_screen",
    "append_to_file",
    "brightness_down",
    "brightness_up",
    "cancel_timer",
    "capture_j2_photo",
    "cool_down_pc",
    "copy_file",
    "create_file",
    "delete_note",
    "empty_recycle_bin",
    "explain_clipboard",
    "extract_text_from_screen",
    "extract_zip",
    "flip_camera",
    "flush_dns",
    "get_boca_juniors_info",
    "get_brightness",
    "get_clipboard",
    "get_current_song",
    "get_fotmob_team_info",
    "get_last_file_path",
    "get_network_info",
    "get_notes",
    "get_presence_sensor_status",
    "get_soccer_info",
    "get_system_metrics",
    "get_top_processes",
    "get_weather",
    "kill_process",
    "launch_app",
    "list_memories",
    "list_timers",
    "lock_workstation",
    "media_next",
    "media_play_pause",
    "media_prev",
    "minimize_all",
    "move_file",
    "mute",
    "open_file",
    "open_web_service",
    "optimize_pc_gaming",
    "organize_folder",
    "play_spotify",
    "play_youtube",
    "read_file_content",
    "recall",
    "register_portable_app",
    "remember",
    "restart_pc",
    "rewrite_clipboard",
    "search_files",
    "search_google",
    "search_web",
    "send_file_to_telegram",
    "set_assistant_name",
    "set_avatar_stage",
    "set_brightness",
    "set_clipboard",
    "set_power_plan",
    "set_timer",
    "set_volume",
    "show_in_folder",
    "shutdown_pc",
    "sleep_pc",
    "summarize_clipboard",
    "switch_screen_view",
    "take_screenshot",
    "test_network_ping",
    "toggle_j2_camera",
    "toggle_night_light",
    "toggle_presence_sensor",
    "toggle_sentry_mode",
    "translate_clipboard",
    "trash_file",
    "tv_get_status",
    "tv_list_channels",
    "tv_mute",
    "tv_next_track",
    "tv_open_app",
    "tv_open_onplay",
    "tv_play_pause",
    "tv_power_toggle",
    "tv_prev_track",
    "tv_send_key",
    "tv_set_volume",
    "tv_tune_channel",
    "tv_turn_off",
    "tv_turn_on",
    "tv_type_text",
    "tv_volume_down",
    "tv_volume_up",
    "vigilance_check_j2",
    "vigilance_full_check",
    "volume_down",
    "volume_up",
    "wake_windows_pc",
]


# Implementaciones adaptadas para Function Calling de Gemini

from typing import Dict, List, Callable

from ._common import _clamp, _remember_file, get_last_file_path

from .files import (
    launch_app,
    register_portable_app,
    search_files,
    open_file,
    show_in_folder,
    trash_file,
    move_file,
    copy_file,
    read_file_content,
    create_file,
    append_to_file,
    extract_zip,
    organize_folder,
)

from .media import (
    set_volume,
    volume_up,
    volume_down,
    mute,
    media_play_pause,
    media_next,
    media_prev,
    lock_workstation,
    minimize_all,
    take_screenshot,
    get_system_metrics,
    cool_down_pc,
    set_power_plan,
    switch_screen_view,
    set_avatar_stage,
    flip_camera,
    set_assistant_name,
    shutdown_pc,
    restart_pc,
    sleep_pc,
    wake_windows_pc,
    get_clipboard,
    set_clipboard,
    send_file_to_telegram,
    set_timer,
    cancel_timer,
    list_timers,
)

from .info import (
    get_weather,
    get_soccer_info,
    get_fotmob_team_info,
    search_web,
    get_boca_juniors_info,
    play_youtube,
    play_spotify,
    get_current_song,
    empty_recycle_bin,
    search_google,
    open_web_service,
)

from .capture import (
    analyze_screen,
    capture_j2_photo,
    vigilance_check_j2,
    toggle_j2_camera,
    toggle_presence_sensor,
    get_presence_sensor_status,
    vigilance_full_check,
    toggle_sentry_mode,
    get_brightness,
    set_brightness,
    brightness_up,
    brightness_down,
    toggle_night_light,
    get_top_processes,
    kill_process,
    optimize_pc_gaming,
    test_network_ping,
    flush_dns,
    get_network_info,
    extract_text_from_screen,
)

from .clipboard_ai import (
    summarize_clipboard,
    explain_clipboard,
    translate_clipboard,
    rewrite_clipboard,
)

from .tv import (
    tv_turn_on,
    tv_turn_off,
    tv_power_toggle,
    tv_volume_up,
    tv_volume_down,
    tv_mute,
    tv_set_volume,
    tv_play_pause,
    tv_next_track,
    tv_prev_track,
    tv_open_app,
    tv_open_onplay,
    tv_tune_channel,
    tv_list_channels,
    tv_send_key,
    tv_type_text,
    tv_get_status,
)

from .memory import (
    remember,
    recall,
    list_memories,
    add_note,
    get_notes,
    delete_note,
)


# Lista de funciones para registrar en Gemini

# Lista de herramientas expuestas a Gemini (mismo orden que antes)

AVAILABLE_TOOLS: List[Callable] = [

    launch_app,

    register_portable_app,

    search_files,

    open_file,

    show_in_folder,

    trash_file,

    move_file,

    copy_file,

    read_file_content,

    create_file,

    append_to_file,

    extract_zip,

    organize_folder,

    set_volume,

    volume_up,

    volume_down,

    mute,

    media_play_pause,

    media_next,

    media_prev,

    get_brightness,

    set_brightness,

    brightness_up,

    brightness_down,

    toggle_night_light,

    lock_workstation,

    minimize_all,

    take_screenshot,

    get_system_metrics,

    cool_down_pc,

    set_power_plan,

    get_top_processes,

    kill_process,

    optimize_pc_gaming,

    test_network_ping,

    flush_dns,

    get_network_info,

    switch_screen_view,

    set_avatar_stage,

    flip_camera,

    set_assistant_name,

    get_weather,

    get_soccer_info,

    get_fotmob_team_info,

    search_web,

    get_boca_juniors_info,

    play_youtube,

    play_spotify,

    get_current_song,

    empty_recycle_bin,

    search_google,

    open_web_service,

    shutdown_pc,

    restart_pc,

    sleep_pc,

    wake_windows_pc,

    get_clipboard,

    set_clipboard,

    summarize_clipboard,
    explain_clipboard,
    translate_clipboard,

    rewrite_clipboard,

    extract_text_from_screen,

    send_file_to_telegram,

    analyze_screen,

    remember,

    recall,

    list_memories,

    add_note,

    get_notes,

    delete_note,

    set_timer,

    cancel_timer,

    list_timers,

    capture_j2_photo,

    vigilance_check_j2,

    vigilance_full_check,

    toggle_j2_camera,
    toggle_presence_sensor,
    get_presence_sensor_status,
    toggle_sentry_mode,
    # Herramientas de tele BGH Android TV
    tv_turn_on,
    tv_turn_off,
    tv_power_toggle,
    tv_volume_up,
    tv_volume_down,
    tv_mute,
    tv_set_volume,
    tv_play_pause,
    tv_next_track,
    tv_prev_track,
    tv_open_app,
    tv_open_onplay,
    tv_tune_channel,
    tv_list_channels,
    tv_send_key,
    tv_type_text,
    tv_get_status
]



# Diccionario mapeado por nombre para despacho rápido

TOOLS_MAP: Dict[str, Callable] = {fn.__name__: fn for fn in AVAILABLE_TOOLS}
