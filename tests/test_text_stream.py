import pytest

from roleplay_avatar.text_stream import StopTextFilter, generation_eos_ids


def test_chat_tokenizer_eos_is_preserved_with_base_generation_config():
    # CoSER's model config ends a document; its tokenizer also ends each turn.
    assert generation_eos_ids(128001, 128009) == [128001, 128009]
    assert generation_eos_ids([151643, 151645], 151645) == [151643, 151645]
    assert generation_eos_ids(128001, 128009, override=7) == [7]
    assert generation_eos_ids(None, None) is None


@pytest.mark.parametrize("chunks,stops,expected,stopped", [
    (["Hello <", "EN", "D> hidden"], ["<END>"], "Hello ", True),
    (["你好。下一位：", "用户的发言"], ["下一位："], "你好。", True),
    (["oneSTOPtwoENDthree"], ["END", "STOP"], "one", True),
    (["Hello <EN"], ["<END>"], "Hello <EN", False),
    (["abc", "xyz"], ["", "zEND"], "abcxyz", False),
    (["a", "b", "c"], [], "abc", False),
    (["aab", "ab hidden"], ["abab"], "a", True),
])
def test_stream_stop_boundaries(chunks, stops, expected, stopped):
    stream = StopTextFilter(stops)
    result = "".join(stream.feed(chunk) for chunk in chunks) + stream.finish()
    assert result == expected
    assert stream.stopped == stopped


def test_all_chunk_boundaries_hide_stop():
    source = "A reply\n<END>unspoken"
    for split in range(len(source) + 1):
        stream = StopTextFilter(["\n<END>"])
        assert stream.feed(source[:split]) + stream.feed(source[split:]) + stream.finish() == "A reply"
