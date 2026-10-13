# 第三方来源与许可

## CET6-Full-Process-Learning

- 原项目：[HCLEMINI/CET6-Full-Process-Learning](https://github.com/HCLEMINI/CET6-Full-Process-Learning)
- 参考与改造版本：`5e7d7c9f8772aeb248afcadd2111709ffbc1cfd7`
- 许可：MIT，原版权声明为 `Copyright (c) 2025 Kecoya`。
- 本项目在 `app/ai.py` 中改造上游的 `.env` 读取、模型响应 JSON 提取与服务端模型请求处理逻辑。原项目的独立模块被重构为统一的本地应用，新增内容包导入、确定性选择题判分、学习记录及统一模型设置。
- 原版权声明与 MIT 全文保留在根目录 [LICENSE](LICENSE)。新增代码的版权声明为 `Copyright (c) 2026 1zyulin`。

## 社区题目来源与本地转换

本项目提供读取社区资料的本地转换工具。公开代码仓库不包含这些来源的第三方原题正文或音频；来源文件、转换后的内容包和个人数据库保存在已被 `.gitignore` 排除的 `data/`。本地转换不改变资料本身的权利归属，代码 MIT 许可不会将来源内容重新许可为 MIT。

公开的 `web/cet6-reading-answer-index.json` 只记录题号、答案字母、出处、页码、指纹及核对方法；`web/cet6-reading-correction-index.json` 只记录少量提取标签校正与来源依据。它们不包含完整文章、题干或解析。转换器据此读取用户本地取得的对应文件，不将社区答案声明为官方核验结果。

| 来源 | 本项目中的用途与许可说明 |
| --- | --- |
| [Drhm1224/cet6-all-in-one](https://github.com/Drhm1224/cet6-all-in-one) | `tools/import_sources.py` 读取其六级写作与翻译数据，转换为本地内容包；公开代码没有附带其题目或音频。原来源 README 声明 MIT，第三方题目、参考译文和音频的权利仍需按实际来源核实。转换仅解析 JavaScript 数据字面量，不执行来源代码。 |
| [zzz-sc-tech/cet6-writing-translation](https://github.com/zzz-sc-tech/cet6-writing-translation) | 本地转换四级写作、翻译文本；来源采用 CC BY-NC-SA 4.0。使用与再分发内容时按该来源适用的许可及署名要求处理。参考译文是社区整理，未核验为官方答案。 |
| [0609x/CET46-Resources](https://github.com/0609x/CET46-Resources) | 原卷、答案与部分音频的来源索引；阅读转换器可获取和解析支持的 PDF，用于本地学习。该来源的 [RIGHTS.md](https://github.com/0609x/CET46-Resources/blob/main/RIGHTS.md) 没有提供覆盖所有第三方内容的统一再分发许可。公开仓库仅保留来源元数据和转换工具。 |
| [wamich/english-exem-md](https://github.com/wamich/english-exem-md) | 部分资料来源与格式研究，来源索引保留链接；本次公开代码不附带其原题正文。原仓库标明 GPLv2，内容使用按其适用的许可范围处理。 |
| [AndrewYuZhenYu/cet6_exam_questions_txt_collection](https://github.com/AndrewYuZhenYu/cet6_exam_questions_txt_collection) | 作为六级阅读备用文本来源，结合原卷与对应答案进行本地转换。公开仓库只含下载、转换工具和源文件指纹，不附带该来源原题正文；原题权利仍按实际来源核实。 |
| [Gatsby666-jay/CET6-2025-2026](https://github.com/Gatsby666-jay/CET6-2025-2026) | 六级阅读备用原卷及答案来源。源 PDF 仅下载至本地 `data/`，公开仓库仅记录来源路径、指纹与转换流程，不重新许可第三方题目或解析。 |
| [LoveItsukaKotori/cet6-training-app](https://github.com/LoveItsukaKotori/cet6-training-app) | 固定版本 `b3fb51a75607ab29e595be955816699d8a5ba0e4` 中的六级文字层原卷及末页答案键，用于本地阅读转换、文章与题号核对。只公开文件路径和指纹，不附带原题正文；源项目代码许可不自动覆盖考试正文。 |

所有社区转换内容保持 `source.verified: false`。标题不再显示“待校对”字样，并不将其变为已核验的官方题库。来源身份、题目提取、答案对应和使用范围需要分别核查；研究快照也不属于本项目发布内容。

## ECDICT 词库

- 来源：[skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)，固定版本 `bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b`。
- 文件：`ecdict.csv`，Git blob SHA 为 `c4ade63ea08cf39d9c3475e96929036d64d94c94`。
- 许可：[上游 MIT](https://github.com/skywind3000/ECDICT/blob/bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b/LICENSE)，版权为 `Copyright (c) 2025 Linwei`。
- 本项目 `tools/import_wordbooks.py` 按 `cet4` 标签生成四级词表，按 `cet4` / `cet6` 标签并集生成含四级基础的六级词表，保留中文释义、音标及来源指纹。未把它称为红宝书等出版社词书，也没有补写上游未提供的例句。
- 原 CSV、导出词书和本地数据库不提交至公开仓库。转换工具在导出目录写入 `ECDICT-LICENSE.txt`，并保留下面的上游声明。

```text
MIT License

Copyright (c) 2025 Linwei

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 内容与运行依赖

- `examples/demo-exams.json`、`examples/demo-words.csv` 为本项目原创格式参考，随项目采用 MIT 许可；它们不是考试真题，也不是商业词书的节选。新安装不自动导入这些文件。
- `examples/empty-real-exam-template.json` 只展示数据格式，尚未填写完整，不含实际真题。
- 用户导入的试卷、答案、解析、词书与音频不因使用本软件而自动获得 MIT 许可；内容权利由原始来源决定。导入数据默认留在本地 `data/`，不提交到代码仓库。
- 基础运行依赖以 `requirements.txt` 为准。PDF 转换使用可选的 `pdfplumber` / `pypdf`，六级 Word 转换还使用 `python-docx`，另行安装在项目独立环境。依赖仍遵循各自许可证；本项目许可证不会替代其条款。
- 大模型 API 和浏览器语音功能遵循各自服务与平台条款；本项目不附带模型密钥或商业服务额度。
