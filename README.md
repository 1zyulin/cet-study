# CET Study · 四六级学习室

在自己的电脑上运行，用 Edge 或 Chrome 学习四级、六级。题库、词书和学习记录保存在本地；配置自己的大模型 API 后，可以围绕题目提问，并获得写作、翻译的参考评分。

本项目基于 [CET6-Full-Process-Learning](https://github.com/HCLEMINI/CET6-Full-Process-Learning) 的部分服务端逻辑改造，采用 MIT 许可，保留原作者署名。复用范围见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## v0.1 的学习流程

- 导入四级、六级 JSON 内容包，按套卷练习阅读、听力、写作和翻译。
- 选择题依照题库答案判分，并查看解析与错题记录。
- 配置兼容 Chat Completions 的模型 API，结合当前题目答疑，批改写作与翻译。
- 导入个人词书，练习单词并记录复习进度。
- 上传本地听力音频，通过题库中的音频地址练习；逐句精听需要提供对应时间轴。
- 将本地学习数据导出为备份，或从备份恢复。

仓库仅内置 **两套自创演示练习和 20 个演示单词**，不含近十年完整真题、真实考试音频或红宝书等商业词书。演示练习始终标记为演示；完整真题建设进度见 [路线图](docs/ROADMAP.md)。

## 在 Windows 上启动

需要 Python 3.10 或更新版本，以及 Edge / Chrome。详细的下载安装、首次使用和常见问题步骤见 [Windows 上手指南](docs/Windows上手指南.md)。下载并解压仓库后，在项目文件夹打开终端，运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

脚本首次创建项目 `.venv` 并安装依赖，之后启动应用；不会安装项目之外的 Python 包。上面的执行策略参数只作用于本次进程，不修改系统策略。也可以右键 `start.ps1` 选择“使用 PowerShell 运行”。

浏览器自动打开；也可手动访问 [http://127.0.0.1:8765](http://127.0.0.1:8765)。服务运行期间保持启动终端打开；按 `Ctrl+C` 停止。

如果希望手动操作，无需激活环境，直接运行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

没有 `py` 命令但 `python --version` 正常时，将第一行的 `py -3` 换为 `python`。

在 macOS / Linux 上，也可以使用 Python 环境运行相同的应用：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

默认服务只监听 `127.0.0.1`，供本机使用。v0.1 按单人本地应用设计，没有多人账户或公网部署流程。

### Docker 备用部署方式

仓库提供 Docker 配置，可以在项目根目录执行：

```sh
docker build -t cet-study .
docker run --rm -p 127.0.0.1:8765:8765 -v cet-study-data:/app/data cet-study
```

随后访问同一个本地网页地址。学习数据保存在 `cet-study-data` 卷中；删除容器不会自动删除该卷。**Docker 部署尚未实测**，当前优先使用上面的 Python 启动方式。

## 第一次使用

1. 打开网页，选择演示练习，先完成两道选择题，查看判分。
2. 在“模型设置”填写 API 服务地址、模型名和自己的密钥，点击“保存设置”，再试用 AI 答疑与批改。
3. 在“题库与数据”选择“导入题库”或“上传音频”；在“单词复习”选择“导入词书”。示例与字段说明见 [内容格式](docs/content-format.md)。
4. 在“题库与数据”使用“导出备份”保存题库、单词和作答记录。更换电脑时安装应用并选择“恢复备份”；音频与模型设置需另外处理，详见下文。

没有云端 API 密钥时，题库导入、客观题判分、单词练习和本地音频播放仍可使用。云端 AI 调用需要网络与服务商额度；本机模型按其实际配置运行。调用时，相关题目、作答或聊天内容会发送到所配置的模型接口。

## 配置 AI

填写能够接受 `POST /chat/completions` 的兼容接口。**Base URL 填接口根地址，不包含 `/chat/completions`**；例如接口要求版本前缀时填写 `https://api.example.com/v1`。服务端会追加 `/chat/completions`。

模型名使用服务商提供的准确标识，例如 DeepSeek 服务中的 `deepseek-chat`。使用其他兼容服务时替换 Base URL、模型名和密钥即可；不同服务的兼容性仍需实际验证。

外部服务地址须使用 HTTPS 并提供 API Key；本机模型可以使用 `http://localhost:端口/v1` 或 `http://127.0.0.1:端口/v1`，支持不填写密钥的接口。这里的端口和模型名应按本机模型服务的实际配置填写。

API 密钥由本地服务保存在本地设置中，不写入网页源码，也不随代码仓库提交。保存设置并不表示已经成功调用模型。AI 评分标注为 **15 分制参考评分**，不是官方评分，更不是四六级 710 分制成绩。AI 输出可能有误，应结合题库原始答案和人工判断。

## 题库与词书

- [演示内容包](examples/demo-exams.json)：可作为阅读、写作、翻译数据格式的完整例子。
- [演示词书](examples/demo-words.csv)：CSV 列名为 `word,meaning,phonetic,example`。
- [空白真题模板](examples/empty-real-exam-template.json)：未填写完整，缺少选择题答案；**不能直接导入**。补齐原文、答案、来源与校对状态后再使用。

用户导入内容默认留在 `data/`。标记为真题并不代表平台已替用户核验真实性；`source.verified` 记录提供者的校对声明。发布内容包前，应核实原题、音频、解析和词书的使用权。软件 MIT 许可不自动覆盖第三方内容。

## 数据与备份

本地 `data/` 保存学习数据库、导入内容、音频和设置；该目录已被 `.gitignore` 排除。卸载、迁移或清理项目目录前，请先备份。

网页导出的 JSON 备份包含 `exams`（题库）、`attempts`（作答记录）和 `words`（单词与复习数据），**不包含模型设置、API Key 或音频文件**。迁移电脑时，除 JSON 备份外，还需单独备份并复制 `data/audio/`，保留音频文件名，然后重新填写模型设置。

恢复操作会替换当前题库、作答记录与单词。恢复前，服务自动在 `data/recovery/` 保存当前学习数据快照；如需撤销，可将对应快照作为备份再次导入。快照同样不包含模型密钥和音频。备份与快照应作为个人资料妥善保存。

本地数据并非云端同步，API 密钥也不由 GitHub 托管。不要把自己的 `data/`、`.env`、音频或备份文件加入公开仓库。

## 开发与许可

```sh
python -m unittest discover -s tests
```

贡献说明见 [CONTRIBUTING](docs/CONTRIBUTING.md)，后续计划见 [ROADMAP](docs/ROADMAP.md)。代码与自创演示内容采用 [MIT](LICENSE)；第三方原始内容遵循其各自许可。
