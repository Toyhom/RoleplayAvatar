"""Install rembg's pinned BiRefNet general foreground model."""
import hashlib
import os
import urllib.request
from pathlib import Path

url = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-epoch_244.onnx"
expected_md5 = "7a35a0141cbbc80de11d9c9a28f52697"  # Published by rembg's BiRefNetGeneralSession.
target = Path(os.environ["AVATAR_MODEL_ROOT"]) / "rembg/birefnet-general.onnx"
target.parent.mkdir(parents=True, exist_ok=True)


def valid(path):
    if not path.is_file():
        return False
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest() == expected_md5


if valid(target):
    print("Foreground model already verified")
else:
    temporary = target.with_suffix(".partial")
    urllib.request.urlretrieve(url, temporary)
    if not valid(temporary):
        raise ValueError("Foreground model integrity check failed")
    temporary.replace(target)
    print("Foreground model downloaded and verified")
