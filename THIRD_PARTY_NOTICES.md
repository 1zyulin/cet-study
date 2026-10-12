# 第三方来源与许可

## CET6-Full-Process-Learning

- 原项目：[HCLEMINI/CET6-Full-Process-Learning](https://github.com/HCLEMINI/CET6-Full-Process-Learning)
- 参考与改造版本：`5e7d7c9f8772aeb248afcadd2111709ffbc1cfd7`
- 许可：MIT，原版权声明为 `Copyright (c) 2025 Kecoya`。
- 本项目在 `app/ai.py` 中改造上游的 `.env` 读取、模型响应 JSON 提取与服务端模型请求处理逻辑。原项目的独立模块被重构为统一的本地应用，新增内容包导入、确定性选择题判分、学习记录及统一模型设置。
- 原版权声明与 MIT 全文保留在根目录 [LICENSE](LICENSE)。新增代码的版权声明为 `Copyright (c) 2026 1zyulin`。

## 社区题目来源与本地转换

本项目提供读取社区资料的本地转换工具。公开代码仓库不包含这些来源的第三方原题正文或音频；来源文件、转换后的内容包和个人数据库保存在已被 `.gitignore` 排除的 `data/`。本地转换不改变资料本身的权利归属，代码 MIT 许可不会将来源内容重新许可为 MIT。

| 来源 | 本项目中的用途与许可说明 |
| --- | --- |
| [Drhm1224/cet6-all-in-one](https://github.com/Drhm1224/cet6-all-in-one) | `tools/import_sources.py` 读取其六级写作与翻译数据，转换为本地内容包；公开代码没有附带其题目或音频。原来源 README 声明 MIT，第三方题目、参考译文和音频的权利仍需按实际来源核实。转换仅解析 JavaScript 数据字面量，不执行来源代码。 |
| [zzz-sc-tech/cet6-writing-translation](https://github.com/zzz-sc-tech/cet6-writing-translation) | 本地转换四级写作、翻译文本；来源采用 CC BY-NC-SA 4.0。使用与再分发内容时按该来源适用的许可及署名要求处理。参考译文是社区整理，未核验为官方答案。 |
| [0609x/CET46-Resources](https://github.com/0609x/CET46-Resources) | 原卷、答案与部分音频的来源索引；阅读转换器可获取和解析支持的 PDF，用于本地学习。该来源的 [RIGHTS.md](https://github.com/0609x/CET46-Resources/blob/main/RIGHTS.md) 没有提供覆盖所有第三方内容的统一再分发许可。公开仓库仅保留来源元数据和转换工具。 |
| [wamich/english-exem-md](https://github.com/wamich/english-exem-md) | 部分资料来源与格式研究，来源索引保留链接；本次公开代码不附带其原题正文。原仓库标明 GPLv2，内容使用按其适用的许可范围处理。 |

所有社区转换内容保持 `source.verified: false`。来源身份、题目提取、答案对应和使用范围需要分别核查；未经人工校对，不标注为已经核验的官方题库。研究快照也不属于本项目发布内容。

## 内容与运行依赖

- `examples/demo-exams.json`、`examples/demo-words.csv` 为本项目自创的演示内容，随项目采用 MIT 许可；它们不是考试真题，也不是商业词书的节选。
- `examples/empty-real-exam-template.json` 只展示数据格式，尚未填写完整，不含实际真题。
- 用户导入的试卷、答案、解析、词书与音频不因使用本软件而自动获得 MIT 许可；内容权利由原始来源决定。导入数据默认留在本地 `data/`，不提交到代码仓库。
- 基础运行依赖以 `requirements.txt` 为准。PDF 转换使用可选的 `pdfplumber` / `pypdf`，另行安装在项目独立环境。依赖仍遵循各自许可证；本项目许可证不会替代其条款。
- 大模型 API 和浏览器语音功能遵循各自服务与平台条款；本项目不附带模型密钥或商业服务额度。
