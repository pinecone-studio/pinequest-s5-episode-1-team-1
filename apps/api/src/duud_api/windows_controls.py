"""Windows controls for desktop actions: volume (Core Audio), lock screen, standard folders.

Raw COM through ctypes, so the API needs no extra packages. Windows only; import it lazily.
"""

from __future__ import annotations

import ctypes
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_ulong, c_void_p
from ctypes.wintypes import BOOL
from typing import TypeVar

T = TypeVar("T")

CLSID_MM_DEVICE_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMM_DEVICE_ENUMERATOR = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAUDIO_ENDPOINT_VOLUME = "{5CDF2C82-841E-4546-9722-0CF74078229A}"
CLSCTX_ALL = 23
E_RENDER = 0  # speakers, not the microphone
E_CONSOLE = 0
COINIT_MULTITHREADED = 0

# vtable slots (IUnknown takes 0-2)
RELEASE = 2
ENUM_GET_DEFAULT_ENDPOINT = 4
DEVICE_ACTIVATE = 3
VOL_SET_LEVEL_SCALAR = 7
VOL_GET_LEVEL_SCALAR = 9
VOL_SET_MUTE = 14
VOL_GET_MUTE = 15

KNOWN_FOLDERS = {
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}


class _GUID(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


def _guid(text: str) -> _GUID:
    return _GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


def _method(obj: c_void_p, slot: int, *argtypes, restype=ctypes.HRESULT) -> Callable:
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtable[slot])
    return lambda *args: fn(obj, *args)


# COM calls run on one worker thread that owns its apartment, away from the event loop.
_com = ThreadPoolExecutor(max_workers=1, thread_name_prefix="duud-com")


def _with_speaker_volume(work: Callable[[c_void_p], T]) -> T:
    """Runs `work` with the default speaker's IAudioEndpointVolume. Raises OSError without one."""

    def call() -> T:
        ole32 = ctypes.windll.ole32
        initialized = ole32.CoInitializeEx(None, COINIT_MULTITHREADED) in (0, 1)
        enum, device, volume = c_void_p(), c_void_p(), c_void_p()
        try:
            hr = ole32.CoCreateInstance(
                byref(_guid(CLSID_MM_DEVICE_ENUMERATOR)), None, CLSCTX_ALL, byref(_guid(IID_IMM_DEVICE_ENUMERATOR)), byref(enum)
            )
            if hr != 0:
                raise OSError(hr, "CoCreateInstance(MMDeviceEnumerator) failed")
            _method(enum, ENUM_GET_DEFAULT_ENDPOINT, c_int, c_int, POINTER(c_void_p))(E_RENDER, E_CONSOLE, byref(device))
            _method(device, DEVICE_ACTIVATE, POINTER(_GUID), c_uint, c_void_p, POINTER(c_void_p))(
                byref(_guid(IID_IAUDIO_ENDPOINT_VOLUME)), CLSCTX_ALL, None, byref(volume)
            )
            return work(volume)
        finally:
            for obj in (volume, device, enum):
                if obj.value:
                    _method(obj, RELEASE, restype=c_ulong)()
            if initialized:
                ole32.CoUninitialize()

    return _com.submit(call).result(timeout=10)


def get_volume() -> tuple[int, bool]:
    """(level 0-100, muted)."""

    def work(vol: c_void_p) -> tuple[int, bool]:
        level, muted = c_float(), BOOL()
        _method(vol, VOL_GET_LEVEL_SCALAR, POINTER(c_float))(byref(level))
        _method(vol, VOL_GET_MUTE, POINTER(BOOL))(byref(muted))
        return round(level.value * 100), bool(muted.value)

    return _with_speaker_volume(work)


def change_volume(*, delta: int | None = None, level: int | None = None, mute: bool | None = None) -> int:
    """Set the level (0-100) or move it by `delta` points, and/or (un)mute. Returns the new level.
    Turning the volume up also unmutes, as the volume keys do."""

    def work(vol: c_void_p) -> int:
        current = c_float()
        _method(vol, VOL_GET_LEVEL_SCALAR, POINTER(c_float))(byref(current))
        target = current.value
        if level is not None:
            target = level / 100
        elif delta is not None:
            target = current.value + delta / 100
        target = min(1.0, max(0.0, target))
        if level is not None or delta is not None:
            _method(vol, VOL_SET_LEVEL_SCALAR, c_float, c_void_p)(target, None)
        unmute = (delta or 0) > 0 or (level or 0) > 0
        if mute is not None or unmute:
            _method(vol, VOL_SET_MUTE, BOOL, c_void_p)(bool(mute) if mute is not None else False, None)
        return round(target * 100)

    return _with_speaker_volume(work)


def lock_screen() -> bool:
    return bool(ctypes.windll.user32.LockWorkStation())


def known_folder(name: str) -> str:
    """The user's real Downloads/Documents/... path (these are often moved, e.g. into OneDrive)."""
    path = ctypes.c_wchar_p()
    hr = ctypes.windll.shell32.SHGetKnownFolderPath(byref(_guid(KNOWN_FOLDERS[name])), 0, None, byref(path))
    try:
        if hr != 0:
            raise OSError(hr, f"SHGetKnownFolderPath({name}) failed")
        return str(path.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path)
