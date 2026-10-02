"""vLLM 0.21 plugin for NVML queries under UUID-based CUDA allocations."""

import os


def register():
    import vllm
    from vllm.platforms.interface import Platform

    # Version-scoped to the engine distributed by the environment installer.
    if not vllm.__version__.startswith("0.21.") or getattr(Platform, "_avatar_uuid_devices", False):
        return
    original = Platform.device_id_to_physical_device_id.__func__

    @classmethod
    def resolve(cls, device_id):
        variable = cls.device_control_env_var
        visible = os.environ.get(variable, "") if variable else ""
        if variable == "CUDA_VISIBLE_DEVICES" and visible:
            device = visible.split(",")[device_id].strip()
            if device.startswith("GPU-"):
                import pynvml

                pynvml.nvmlInit()
                try:
                    return pynvml.nvmlDeviceGetIndex(pynvml.nvmlDeviceGetHandleByUUID(device))
                finally:
                    pynvml.nvmlShutdown()
        return original(cls, device_id)

    Platform.device_id_to_physical_device_id = resolve
    Platform._avatar_uuid_devices = True
