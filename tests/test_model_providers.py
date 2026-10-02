import asyncio
import json

import httpx
import pytest

from roleplay_avatar.agents import ModelGateway
from roleplay_avatar.models import agent_config, prompt_text


def test_provider_switch_resets_endpoint_key_model_and_extensions(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "default": {
                        "provider": "qwen",
                        "model": "qwen-plus",
                        "extra_body": {"enable_thinking": False},
                    },
                    "roleplay": {"provider": "anthropic", "model": "claude-example"},
                    "initiative": {"generation": {"temperature": 0.1}},
                }
            }
        )
    )
    monkeypatch.setenv("AVATAR_MODELS_CONFIG", str(path))
    claude = agent_config("roleplay")
    assert claude["url"] == "https://api.anthropic.com/v1"
    assert claude["api_key_env"] == "ANTHROPIC_API_KEY"
    assert claude["extra_body"] == {}
    assert agent_config("initiative")["model"] == "qwen-plus"
    assert agent_config("initiative")["generation"]["temperature"] == 0.1


@pytest.mark.parametrize(
    "backend,path,events,expected",
    [
        (
            "anthropic",
            "/v1/messages",
            [
                {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "private"}},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
            ],
            "Hello",
        ),
        (
            "openai-responses",
            "/v1/responses",
            [
                {"type": "response.reasoning_summary_text.delta", "delta": "private"},
                {"type": "response.output_text.delta", "delta": "Hello"},
            ],
            "Hello",
        ),
        (
            "openai",
            "/v1/chat/completions",
            [
                {"choices": [{"delta": {"reasoning_content": "private"}}]},
                {"choices": [{"delta": {"content": "Hello"}}]},
            ],
            "Hello",
        ),
    ],
)
def test_provider_wire_formats_and_reasoning_filter(backend, path, events, expected, monkeypatch):
    monkeypatch.setenv("TEST_PROVIDER_KEY", "test-token")
    calls = []

    def respond(request):
        calls.append(request)
        body = ": heartbeat\n\n" + "".join("data: " + json.dumps(e) + "\n\n" for e in events)
        return httpx.Response(200, text=body + "data: [DONE]\n\n")

    gateway = ModelGateway(
        config={
            "backend": backend,
            "url": "https://provider/v1",
            "model": "custom",
            "api_key_env": "TEST_PROVIDER_KEY",
            "generation": {"temperature": None},
        },
        transport=httpx.MockTransport(respond),
    )

    async def run():
        return "".join([p async for p in gateway.stream("persona", [{"role": "user", "content": "hi"}])])

    assert asyncio.run(run()) == expected
    assert calls[0].url.path == path
    payload = json.loads(calls[0].content)
    assert "temperature" not in payload
    if backend == "anthropic":
        assert calls[0].headers["x-api-key"] == "test-token"
        assert "authorization" not in calls[0].headers
        assert payload["system"] == "persona"
        assert payload["messages"][0]["role"] == "user"
    else:
        assert calls[0].headers["authorization"] == "Bearer test-token"
    if backend == "openai-responses":
        assert payload["max_output_tokens"] == 1024 and "max_tokens" not in payload


def test_provider_error_is_not_an_empty_success():
    def respond(request):
        return httpx.Response(200, text='data: {"type":"error","error":{"message":"failed"}}\n\n')

    gateway = ModelGateway(
        config={"backend": "anthropic", "url": "https://provider/v1", "model": "m"},
        transport=httpx.MockTransport(respond),
    )

    async def run():
        return [x async for x in gateway.stream("s", [{"role": "user", "content": "q"}])]

    with pytest.raises(RuntimeError, match="provider failed"):
        asyncio.run(run())


def test_anthropic_multimodal_conversion():
    gateway = ModelGateway(config={"backend": "anthropic", "url": "https://a/v1", "model": "m"})
    _, _, payload = gateway.request(
        "system",
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}},
                ],
            }
        ],
        300,
        0.2,
    )
    assert payload["messages"][0]["content"][1]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": "YWJj",
    }


def test_prompt_override_resolves_relative_to_configuration(tmp_path, monkeypatch):
    (tmp_path / "persona.txt").write_text("My research prompt")
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"prompts": {"actor": {"file": "persona.txt"}}}))
    monkeypatch.setenv("AVATAR_MODELS_CONFIG", str(path))
    assert prompt_text("actor") == "My research prompt"


def test_responses_multimodal_conversion():
    gateway = ModelGateway(config={"backend": "openai-responses", "url": "https://a/v1", "model": "m"})
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "describe"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj", "detail": "high"}},
    ]}]
    _, _, payload = gateway.request("system", messages, 300, 0.2)
    assert payload["input"][0]["content"] == [
        {"type": "input_text", "text": "describe"},
        {"type": "input_image", "image_url": "data:image/png;base64,YWJj", "detail": "high"},
    ]
    assert messages[0]["content"][0]["type"] == "text"


def test_same_provider_inherits_and_custom_switch_clears_options(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "providers": {"lab": {"backend": "openai", "url": "https://lab/v1"}},
        "agents": {
            "default": {"provider": "openai", "model": "main", "max_tokens_field": "max_completion_tokens",
                        "generation": {"temperature": 0.4}, "api_key_env": "MAIN_KEY"},
            "roleplay": {"provider": "openai", "generation": {"top_p": 0.8}},
            "initiative": {"provider": "lab", "model": "control"},
        },
    }))
    monkeypatch.setenv("AVATAR_MODELS_CONFIG", str(path))
    actor = agent_config("roleplay")
    assert actor["model"] == "main"
    assert actor["generation"] == {"temperature": 0.4, "top_p": 0.8}
    controller = agent_config("initiative")
    assert controller["api_key_env"] == "AVATAR_LLM_API_KEY"
    assert "max_tokens_field" not in controller
    assert controller["generation"] == {}


def test_actor_and_director_use_separate_providers(monkeypatch, characters):
    from roleplay_avatar import live

    calls = []

    class Gateway:
        def __init__(self, role, url=None):
            self.role = role
            self.config = {"output_mode": "actor_director"}

        async def stream(self, system, messages, **kwargs):
            calls.append((self.role, messages))
            if self.role == "roleplay":
                yield "[Glad to see you] (nods) Hello again!"
            else:
                yield json.dumps(
                    {
                        "text": "Hello again!",
                        "emotion": "happy",
                        "actions": [{"name": "nod", "start_s": 0, "duration_s": 1.6, "strength": 0.5}],
                    }
                )

    monkeypatch.setattr(live, "ModelGateway", Gateway)
    llm = live.RemoteLLM()

    async def run():
        return [
            s
            async for s in llm.stream(
                "actor",
                "Hi",
                characters["dragon_demo"],
                history=[
                    {"role": "assistant", "content": '{"text":"Welcome"}'},
                ],
            )
        ]

    result = asyncio.run(run())
    assert [c[0] for c in calls] == ["roleplay", "performance_director"]
    assert calls[0][1][0]["content"] == "Welcome"
    assert "[Glad to see you]" in calls[1][1][0]["content"]
    assert result[0].text == "Hello again!" and result[0].actions[0].name == "nod"
