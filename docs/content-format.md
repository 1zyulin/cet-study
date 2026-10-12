# 内容包格式（schema_version 1）

v0.1 接受 UTF-8 JSON 内容包。支持的题型为选择题、写作与翻译；暂不支持直接将扫描 PDF 自动变成完整题库。导入前应核对原文、选项顺序、答案和来源。

## 内容包与套卷

顶层结构：

```json
{
  "schema_version": 1,
  "exams": []
}
```

`exams` 每次包含 1—300 套填写完整的练习。每套含 1—30 个部分，每部分含 1—100 道题；不接受空题目数组。每套练习包含以下字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定的唯一标识，建议使用英文、数字和连字符 |
| `title` | 展示名称，真题应写清级别、年份、考次、套卷 |
| `level` | `CET4` 或 `CET6` |
| `year` | 整数年份 |
| `session` | 考次文字，例如 `6月·第一套`；演示内容写 `演示` |
| `source_kind` | `past_paper` 表示真题；`demo` 表示演示 |
| `source` | 来源对象，包含 `title`、可选 `url`、`rights` 与布尔值 `verified` |
| `sections` | 按试卷顺序排列的部分数组 |

来源示例：

```json
{
  "title": "个人持有的原卷与答案：请填写具体出版物或来源",
  "rights": "user-import",
  "verified": false
}
```

`verified: true` 表示内容包制作者已校对；系统不会凭这个字段自动确认真题或授权。`rights` 是权利状态说明，不能代替许可证明。自创演示使用 `original-demo`；个人导入使用 `user-import`。如果内容获准再分发，请记录许可名称、范围或说明链接。

完整可导入例子见 [demo-exams.json](../examples/demo-exams.json)。[empty-real-exam-template.json](../examples/empty-real-exam-template.json) 刻意保留占位文字、未校对状态和缺失答案，用来提示补齐资料；它不是可用真题，不应直接导入。

## 部分与题目

每个 section 有 `id`、`title`、`kind` 和 `questions`。`kind` 为 `reading`、`listening`、`writing` 或 `translation`。阅读可加 `passage`；听力可加 `audio_url`、`transcript` 和 `segments`。

选择题：

```json
{
  "id": "cet4-2025-jun-1-reading-q1",
  "type": "choice",
  "prompt": "填写题干",
  "options": [
    {"id": "A", "text": "填写选项 A"},
    {"id": "B", "text": "填写选项 B"},
    {"id": "C", "text": "填写选项 C"},
    {"id": "D", "text": "填写选项 D"}
  ],
  "answer": "B",
  "explanation": "填写经核对的解析，并明确其来源。"
}
```

`answer` 必须对应实际选项 ID。程序据此判分，AI 不决定正确选项。选择题缺失答案时不应入库用于判分。

写作题的 `type` 为 `writing`，`prompt` 填完整要求；可以加 `min_words`、`max_words` 和 `reference`。写作未提供字数范围时，四级默认 120—180 词，六级默认 150—200 词。

翻译题的 `type` 为 `translation`，`prompt` 填待译原文，`reference` 可填参考译文；默认字数边界为 0—5000，不套用作文范围，评估以原文信息传达和译文质量为主。参考译文或范文必须说明来源，不要把非官方内容标为官方答案。

套卷 ID 在内容包内唯一；部分 ID 与题目 ID 在同一套卷内各自唯一。ID 只允许英文字母、数字、点、下划线和连字符。重新整理同一套卷时，尽量保留题目 ID，避免影响历史记录的对应关系。

## 本地音频与逐句时间轴

在网页上传音频后，本地服务返回形如 `/media/<uuid>.mp3` 的 `audio_url`，将它填入听力 section。支持扩展名为 `.mp3`、`.wav`、`.m4a`、`.ogg` 的文件；实际播放能力取决于浏览器支持的编码。不要把电脑磁盘路径写成音频地址。

时间轴的单位为秒：

```json
{
  "id": "listening-part-a",
  "title": "听力 A",
  "kind": "listening",
  "audio_url": "/media/填入上传返回的文件标识.mp3",
  "transcript": "填写核对后的完整听力原文",
  "segments": [
    {"start": 0.0, "end": 4.2, "text": "第一句原文"},
    {"start": 4.2, "end": 8.7, "text": "第二句原文"}
  ],
  "questions": []
}
```

这段代码仅展示听力字段，导入时还需补齐该部分的题目并替换占位音频地址。每个区间满足 `0 <= start < end <= 86400`，按开始时间升序排列，并与真实音频一致。没有时间轴时可以普通播放和手动精听；系统不会自动生成准确字幕或宣称完成音频对齐。

## 词书导入

CSV 推荐使用带表头的 UTF-8 文件，至少提供 `word` 和 `meaning`；`phonetic` 与 `example` 可为空。逗号出现在字段中时，按标准 CSV 规则使用双引号。

```csv
word,meaning,phonetic,example
adapt,适应变化；调整做法,/əˈdæpt/,Students adapt to a new routine.
```

TXT 每行一个单词，用制表符或逗号分隔单词与释义：

```text
adapt	适应；调整
benefit,益处；使受益
```

JSON 词书使用对象数组：

```json
[
  {
    "word": "adapt",
    "meaning": "适应变化；调整做法",
    "phonetic": "/əˈdæpt/",
    "example": "Students adapt to a new routine."
  }
]
```

v0.1 不直接解析 Excel 工作簿。可在 Excel 中另存为 UTF-8 CSV 后导入。内置示例仅为演示学习流程，不是完整四六级词表；个人导入商业词书不代表可以公开分享该文件。
