# 🌐 谷歌通用语言代码（ISO 639-1 / BCP 47）全整合对照表

| 语言代码 (Code) | 中文名称 | 英文名称 (English) | 备注说明 |
| :--- | :--- | :--- | :--- |
| **`zh-CN`** / `zh-Hans`| **中文（简体）** | Chinese (Simplified) | 大陆简体。`zh-CN` 最常用 |
| **`zh-TW`** / `zh-Hant`| **中文（繁体）** | Chinese (Traditional) | 台湾繁体。`zh-TW` 最常用 |
| **`zh-HK`** | **中文（香港）** | Chinese (Hong Kong) | 香港地区繁体习惯 |
| **`en`** | **英语（通用）** | English | 泛指英语 |
| **`en-US`** | **英语（美国）** | English (US) | 谷歌生态默认的美式英语 |
| **`en-GB`** | **英语（英国）** | English (UK) | 英式英语 |
| **`en-AU`** | **英语（澳大利亚）**| English (Australia) | 澳式英语 |
| --- | --- | --- | --- |
| **`ar`** | 阿拉伯语 | Arabic | 中东及北非地区通用 |
| **`de`** | 德语 | German | 德国、奥地利等 |
| **`es`** | 西班牙语 | Spanish | 可加后缀如 `es-MX` (墨西哥) |
| **`fr`** | 法语 | French | 可加后缀如 `fr-CA` (加拿大) |
| **`hi`** | 印地语 | Hindi | 印度主要语言之一 |
| **`id`** | 印尼语 | Indonesian | |
| **`it`** | 意大利语 | Italian | |
| **`ja`** | 日语 | Japanese | |
| **`ko`** | 韩语 | Korean | |
| **`nl`** | 荷兰语 | Dutch | |
| **`pl`** | 波兰语 | Polish | |
| **`pt`** | 葡萄牙语 | Portuguese | 巴西通常用 `pt-BR` |
| **`ru`** | 俄语 | Russian | |
| **`th`** | 泰语 | Thai | |
| **`tr`** | 土耳其语 | Turkish | |
| **`vi`** | 越南语 | Vietnamese | |

> **💡 开发者小贴士：**
> * 在调用 Google Maps API 或 SerpAPI 时，通常只需传入 `hl=zh-CN` (Host Language) 或 `gl=us` (Geographic Location) 即可精准控制返回结果的语言和地域偏好。
> * 对于小语种，如果不涉及特定国家的口音或词汇差异，直接使用 **两位小写字母**（如 `es`, `fr`）兼容性最好。