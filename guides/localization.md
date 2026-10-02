# Languages

[English](localization.md) · [简体中文](zh-CN/localization.md) · [日本語](ja/localization.md)

The studio and all guides are available in English, Simplified Chinese and Japanese. Use the language selector in the header. The browser language is used initially; your choice is saved. A URL such as `/?lang=ja` opens a particular language. A language change reloads the interface and keeps the selected character, conversation and unsent message.

The interface translates navigation, creation, voice selection, microphone state, conversations, performance controls and operational messages. Character names, personas, imported attribution and conversation text retain their original content.

## Creation and speech

The studio sends `locale` with image creation and Live2D import. The worker uses it for character design, reference text and VoiceDesign's language. The API accepts `en`, `zh-CN` and `ja`, with `zh-CN` as the compatibility default. `/api/agents/character-design` accepts the same field. The actor/director follows the user's requested language or message language during conversation.

Start Whisper with `--language auto` for multilingual microphones, or select one language explicitly. Existing voices retain their original reference recording; create a character in the desired language for a new reference voice.

## Add a language

1. Add a catalog in `web/locales/` with the same source keys and positional placeholders as `en.js`. These keys describe interface text; model output is independent.
2. Register the catalog in `web/i18n.js` and add an option to `web/index.html`. Update `normalizeLocale` for its language tag.
3. For generation in another language, extend `Locale`, `LANGUAGES`, `VOICE_VARIATIONS` and `VOICE_RECORDING` in `languages.py` with a language supported by the selected speech model.
4. Translate every guide into a matching language directory and add README navigation. `scripts/check_docs.py` checks the current three-language page inventory and links.
5. Run `node --test tests/*.test.mjs` and `python scripts/check_localization.py --url http://localhost:18080`. The browser check covers desktop/mobile layout, dialogs, language changes, empty-chat reuse and exports.

Static text is translated without replacing nested elements. Dynamic UI messages call `t()` explicitly; placeholders are inserted as text. Strings belong in the catalogs, while character content and backend error details remain data.

[← All guides](index.md)
