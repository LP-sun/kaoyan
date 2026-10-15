# 考研专业课物理刷题工作区

本仓库保存题库处理脚本、刷题页面、AI 改编流程及备考资料。教材、讲义、试卷和考纲保留原文件名纳入版本管理；API 密钥、本地学习记录及运行环境仍不纳入 Git。

## 下载教材与试卷

PDF 使用 Git LFS 保存。克隆仓库前安装 Git LFS，然后运行：

```powershell
git lfs install
git clone https://github.com/LP-sun/kaoyan.git
cd kaoyan
git lfs pull
```

已有克隆只需更新代码后运行 `git lfs pull`。未安装或未拉取 LFS 时，PDF 可能只是文本指针，无法作为课本打开。

- `教材/`：教材及对应版本的习题答案。
- `允文君数学物理资料分享/`：物理与数学讲义、笔记、图片版及勘误。
- `资料整理/教程/`：Tong 教程、北师大量子力学习题及本地补充讲义。
- 根目录：2022年651试卷的四张 PNG、2023/2024/2025年普物试卷、2024年量子试卷，以及普物、量子考纲 PDF。

上传资料不改变内容核验状态；所有真题（包括新加入的2022年、2025年651试卷）均默认冻结为模拟卷，不进入自动推荐。

## 入口

- **主学习应用**：`PhysicsPrep/app.py`，默认「连续刷题」，无需事先维护教材解析。
  启动：`PhysicsPrep\.venv\Scripts\python.exe PhysicsPrep\app.py`，访问`http://127.0.0.1:7860`。
  功能与质量边界见 [连续刷题说明](PhysicsPrep/docs/CONTINUOUS_PRACTICE.md)。

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
