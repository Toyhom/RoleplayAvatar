"""Bounded reference conditioning cache for local speech models."""

import hashlib
from collections import OrderedDict
from pathlib import Path


class VoicePromptCache:
    """Call under the model's inference lock; voice edits invalidate previous conditioning."""

    def __init__(self, capacity=8):
        if capacity < 0:
            raise ValueError("Voice cache capacity must be nonnegative")
        self.capacity = capacity
        self.entries = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, audio, transcript, build):
        digest = hashlib.sha256(Path(audio).read_bytes()).hexdigest()
        key = (digest, transcript)
        if key in self.entries:
            self.hits += 1
            self.entries.move_to_end(key)
            return self.entries[key]
        self.misses += 1
        value = build()
        if self.capacity:
            self.entries[key] = value
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
        return value

    def stats(self):
        return {"capacity": self.capacity, "entries": len(self.entries), "hits": self.hits, "misses": self.misses}
