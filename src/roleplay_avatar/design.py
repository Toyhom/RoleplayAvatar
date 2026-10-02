"""Character-design agent for imported resources and integrator-authored briefs."""

from pydantic import Field

from .agents import ModelGateway
from .contracts import Contract
from .languages import Locale, creation_language


class CharacterDesign(Contract):
    display_name: str = Field(min_length=1, max_length=50)
    tagline: str = Field(min_length=1, max_length=80)
    persona: str = Field(min_length=30, max_length=2400)
    voice_design: str = Field(min_length=20, max_length=700)
    voice_text: str = Field(min_length=20, max_length=180)
    voice_reason: str = Field(default="", max_length=300)


async def design_character(description, gateway=None, locale: Locale = "zh-CN"):
    return await (gateway or ModelGateway("character_design")).structured(
        "Design a fictional character and voice from the user's brief. "
        "Use natural speech with breathing pauses. Ground visual observations in supplied evidence. "
        + creation_language(locale),
        {"description": description, "language": creation_language(locale)},
        CharacterDesign,
        max_tokens=1200,
    )
