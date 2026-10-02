"""Apply UUID resolution before vLLM deserializes quantized worker configs."""


def register():
    # Platform discovery runs earlier than general plugins in spawned workers.
    # Keep vLLM's native platform selection and use its version-scoped adapter.
    from .vllm_devices import register as register_devices

    register_devices()
