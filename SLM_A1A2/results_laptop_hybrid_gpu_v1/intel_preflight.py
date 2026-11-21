"""Initialize the pinned Vulkan plugin on the Intel adapter in an isolated process."""
import ctypes as C
import json
import os
from pathlib import Path

native = Path(__file__).resolve().parent.parent / "cross_demo/native/artifacts/b12359/win-x64"
os.environ["GGML_VK_VISIBLE_DEVICES"] = "0"


def bind(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


with os.add_dll_directory(str(native)):
    registry = C.CDLL(str(native / "ggml.dll"))
    base = C.CDLL(str(native / "ggml-base.dll"))
    ptr, size = C.c_void_p, C.c_size_t
    bind(registry, "ggml_backend_load_all_from_path", None, C.c_char_p)(str(native).encode("utf-8"))
    module = bind(registry, "ggml_backend_reg_by_name", ptr, C.c_char_p)(b"Vulkan")
    if not module or bind(base, "ggml_backend_reg_dev_count", size, ptr)(module) != 1:
        raise RuntimeError("The Vulkan plugin did not enumerate the selected adapter.")
    dev = bind(base, "ggml_backend_reg_dev_get", ptr, ptr, size)(module, 0)
    description = bind(base, "ggml_backend_dev_description", C.c_char_p, ptr)(dev).decode("utf-8")
    if description != "Intel(R) UHD Graphics 630":
        raise RuntimeError(f"Unexpected Vulkan adapter: {description}")
    available, capacity = size(), size()
    bind(base, "ggml_backend_dev_memory", None, ptr, C.POINTER(size), C.POINTER(size))(
        dev, C.byref(available), C.byref(capacity))
    backend = bind(base, "ggml_backend_dev_init", ptr, ptr, C.c_char_p)(dev, None)
    if not backend:
        raise RuntimeError("GGML could not initialize the Intel Vulkan backend.")
    bind(base, "ggml_backend_free", None, ptr)(backend)
    print(json.dumps({"adapter": description, "GGML_VK_VISIBLE_DEVICES": 0, "initialized": True,
                      "ggml_available_bytes": available.value, "ggml_capacity_bytes": capacity.value}))
