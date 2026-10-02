"""Text-stream boundaries shared by local generation adapters."""


def generation_eos_ids(model_eos, tokenizer_eos, override=None):
    """Honor both the model and chat tokenizer's end-of-turn tokens."""
    selected = override if override is not None else model_eos
    values = list(selected) if isinstance(selected, (list, tuple)) else [selected]
    if override is None:
        values.append(tokenizer_eos)
    return list(dict.fromkeys(value for value in values if value is not None)) or None


class StopTextFilter:
    """Withhold possible stop prefixes and omit a matched stop and its suffix."""

    def __init__(self, stops):
        self.stops = tuple(s for s in stops if s)
        self.pending = ""
        self.stopped = False

    def feed(self, text):
        if self.stopped:
            return ""
        self.pending += text
        matches = [self.pending.find(s) for s in self.stops if s in self.pending]
        if matches:
            result = self.pending[: min(matches)]
            self.pending = ""
            self.stopped = True
            return result
        keep = max(
            (size for stop in self.stops for size in range(1, len(stop))
             if self.pending.endswith(stop[:size])),
            default=0,
        )
        if keep:
            result, self.pending = self.pending[:-keep], self.pending[-keep:]
        else:
            result, self.pending = self.pending, ""
        return result

    def finish(self):
        result, self.pending = self.pending, ""
        return result
