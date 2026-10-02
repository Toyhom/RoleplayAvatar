"""Map bounded delivery intent to CosyVoice3's supported instruction format."""

from .contracts import Delivery


def synthesis_direction(style, intensity, delivery):
    delivery = Delivery.model_validate(delivery or {})
    # Reference-conditioned generation best preserves conversational identity.
    # Reserve instruction mode for deliberate delivery, not every small smile.
    expressive = (
        (intensity >= 0.7 and style in {"happy", "sad", "angry"})
        or delivery.tone != "conversational"
        or delivery.pace != "natural"
    )
    if not expressive:
        return None
    tone = {
        "conversational": "自然地聊天",
        "warm": "温和亲切地聊天",
        "playful": "轻松俏皮地聊天",
        "serious": "认真平稳地聊天",
    }[delivery.tone]
    pace = {"natural": "语速自然", "relaxed": "语速稍舒缓，停顿自然", "brisk": "语速稍轻快，吐字清楚"}[
        delivery.pace
    ]
    emotion = {
        "happy": "带着轻松的笑意",
        "sad": "带一点低落但保持清晰",
        "angry": "语气坚定克制",
        "soft": "温柔而清楚",
    }.get(style, "自然表达")
    return f"You are a helpful assistant. {tone}，{pace}，{emotion}，像面对面交谈。<|endofprompt|>"
