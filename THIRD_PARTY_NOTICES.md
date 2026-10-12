# 第三方来源与许可

## CET6-Full-Process-Learning

- 原项目：[HCLEMINI/CET6-Full-Process-Learning](https://github.com/HCLEMINI/CET6-Full-Process-Learning)
- 参考与改造版本：`5e7d7c9f8772aeb248afcadd2111709ffbc1cfd7`
- 许可：MIT，原版权声明为 `Copyright (c) 2025 Kecoya`。
- 本项目在 `app/ai.py` 中改造上游的 `.env` 读取、模型响应 JSON 提取与服务端模型请求处理逻辑。原项目的独立模块被重构为统一的本地应用，新增内容包导入、确定性选择题判分、学习记录及统一模型设置。
- 原版权声明与 MIT 全文保留在根目录 [LICENSE](LICENSE)。新增代码的版权声明为 `Copyright (c) 2026 1zyulin`。

## 其他研究材料

`Drhm1224/cet6-all-in-one` 仅用于前期功能与数据组织研究。本项目没有复制该仓库的代码、真题数据或音频。研究快照不属于本项目发布内容。

## 内容与运行依赖

- `examples/demo-exams.json`、`examples/demo-words.csv` 为本项目自创的演示内容，随项目采用 MIT 许可；它们不是考试真题，也不是商业词书的节选。
- `examples/empty-real-exam-template.json` 只展示数据格式，尚未填写完整，不含实际真题。
- 用户导入的试卷、答案、解析、词书与音频不因使用本软件而自动获得 MIT 许可；内容权利由原始来源决定。导入数据默认留在本地 `data/`，不提交到代码仓库。
- 运行依赖以 `requirements.txt` 为准。依赖仍遵循各自许可证；本项目许可证不会替代其条款。
- 大模型 API 和浏览器语音功能遵循各自服务与平台条款；本项目不附带模型密钥或商业服务额度。
