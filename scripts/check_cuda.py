import json

import torch

torch.manual_seed(0)
x = torch.randn(32, 32, device="cuda")
y = x @ x.T
torch.cuda.synchronize()
assert torch.isfinite(y).all() and y.shape == (32, 32)
print(
    "WITNESS",
    json.dumps(
        {
            "shape": list(y.shape),
            "device": torch.cuda.get_device_name(),
            "torch": torch.__version__,
            "checksum": float(y.sum()),
        }
    ),
    flush=True,
)
