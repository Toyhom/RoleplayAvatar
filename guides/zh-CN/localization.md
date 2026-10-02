# 多语言

[English](../localization.md) · [简体中文](localization.md) · [日本語](../ja/localization.md)

界面与全部指南提供英文、简体中文、日文。顶部可切换语言，首次按浏览器语言选择，之后保存用户偏好；`/?lang=ja` 可直接打开日文。切换会重新载入界面，保留选中角色、会话和未发送的消息。

导航、创建、声线选择、录音状态、会话、表演控制和运行提示使用统一语言表。角色名字、人设、导入来源信息和会话原文保持原有内容。

## 创建与语音

图片创建和 Live2D 导入随请求发送 `locale`，用于人设、参考台词、VoiceDesign 语言。API 支持 `en`、`zh-CN`、`ja`，兼容默认值是 `zh-CN`；`/api/agents/character-design` 也接收该字段。对话中的角色/导演遵循用户指定语言或消息语言。

多语言麦克风使用 Whisper `--language auto`，也可固定语言。已有角色保留原始参考声音，需要新语言的参考声线时按该语言创建角色。

## 增加一种语言

1. 在 `web/locales/` 加入语言表，键和位置占位符与 `en.js` 一致。界面键与模型生成内容相互独立。
2. 在 `web/i18n.js` 注册，在 `web/index.html` 加选项，并更新 `normalizeLocale`。
3. 新生成语言还须扩展 `languages.py` 的 `Locale`、`LANGUAGES`、`VOICE_VARIATIONS` 和 `VOICE_RECORDING`，选用语音模型支持的语言。
4. 翻译每篇指南和 README 导航；`scripts/check_docs.py` 检查当前三语页面集合和链接。
5. 执行 `node --test tests/*.test.mjs` 与 `python scripts/check_localization.py --url http://localhost:18080`。浏览器检查包含桌面/移动布局、对话框、语言切换、空会话复用及导出。

静态翻译保留嵌套控件，动态提示显式调用 `t()`，占位符按纯文本插入。文案放在语言表，角色文本和后端错误详情作为数据处理。

[← 全部指南](index.md)
