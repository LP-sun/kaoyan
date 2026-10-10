# 考研专业课物理刷题工作区

本仓库保存题库处理脚本、刷题页面和 AI 改编流程。教材 PDF、真题 PDF、个人资料、API 密钥和本地学习记录不纳入 Git。

## 入口

- `资料整理/题库/index.html`：单题刷题工作台（使用本地静态服务器打开）
- `资料整理/题库/batch_adapt_mcq.py`：调用 DeepSeek 批量生成选择题改编草稿
- `资料整理/题库/exam_adaptations.json`：人工编写的改编题草稿

## 本地运行

```powershell
cd 资料整理/题库
python -m http.server 8765 --bind 127.0.0.1
```

浏览器访问 `http://127.0.0.1:8765/index.html`。

## AI 配置

页面可粘贴 OpenAI 兼容的 Base URL、模型和 API Key。批处理脚本只从 `DEEPSEEK_API_KEY` 或 `GENAI_API_KEY` 读取密钥；不要把密钥写入仓库。

## 数据状态

教材题面、OCR、相关性分析、人工核验和解析完成度是不同状态。真题默认冻结，不进入自动推荐；AI 改编结果在人工复核前保持 `draft`，不进入推荐器。
