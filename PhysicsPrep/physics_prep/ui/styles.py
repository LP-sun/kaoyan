CSS = '''
.gradio-container {max-width: 1280px !important; font-family: "Microsoft YaHei", "Segoe UI", sans-serif !important;}
.hero {padding:12px 18px;border-radius:12px;background:var(--background-fill-secondary,#f4f6fb);margin-bottom:10px;}
.hero h1 {margin:0 0 3px;font-size:19px;letter-spacing:-.5px;}
.hero p {margin:0;font-size:13px;line-height:1.5;}
.stats-grid {display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:10px 0 18px;}
.stat-card {border:1px solid var(--border-color-primary,#dce3ef);background:var(--block-background-fill,#fff);border-radius:14px;padding:20px;}
.stat-card span {display:block;font-size:13px;opacity:.75}.stat-card strong {display:block;font-size:27px;margin-top:9px;}

/* 答题区：题目与解析分层，字号与行距保证公式可读 */
#question-card {padding:22px;border:1px solid var(--border-color-primary);border-radius:14px;min-height:155px;}
#question-card .prose {font-size:18px;line-height:1.9;}
#quiz-meta {padding:12px 16px;border-radius:12px;background:var(--background-fill-secondary,#f4f6fb);font-size:14px;}
#quiz-options label {padding:14px !important;min-height:50px;font-size:16px;border-radius:10px;}
#quiz-options .wrap {gap:10px;}
#feedback-card {border-left:4px solid #5979ed;padding:14px 16px;border-radius:0 12px 12px 0;background:var(--background-fill-secondary,#f7f9fd);}
#solution-card {border-left:4px solid #8a94a6;padding:14px 16px;border-radius:0 12px 12px 0;}
#practice-card {padding:26px 28px;border:2px solid #6366f1 !important;border-left-width:6px !important;border-radius:16px;background:var(--block-background-fill,#fff);min-height:135px;box-shadow:0 5px 18px rgba(45,65,105,.08);}
#practice-card .prose {font-size:21px;line-height:1.85;font-weight:500;color:var(--body-text-color,#172c52);}
#practice-card .prose p {margin:0 0 12px;}
#practice-card .katex {font-size:1.12em;}
#practice-meta .prose, #practice-sidebar .prose, #practice-summary .prose {font-size:13px;line-height:1.6;color:var(--body-text-color-subdued,#64748b);}
#practice-radio label, #practice-many label {padding:13px 16px !important;font-size:17px;min-height:48px;border-radius:10px;}
#practice-radio .wrap, #practice-many .wrap {gap:10px;}
#practice-feedback:not(:empty), #practice-hint:not(:empty) {font-size:15px;}
#wrong-table table, #tree-table table, #bank-table table {font-size:13px;}

/* 长公式不裁剪、不溢出容器 */
.katex-display {overflow-x:auto;overflow-y:hidden;padding:8px 0;max-width:100%;}
.katex {font-size:1.06em;}
#question-card .katex-display > .katex {white-space:normal;}

/* 结果区分不依赖颜色，始终有文字标签 */
.status-pill {display:inline-block;padding:3px 10px;border-radius:999px;font-size:13px;border:1px solid currentColor;}

@media(max-width:680px){
  .hero{padding:10px 14px}.hero h1{font-size:18px}
  .stats-grid{grid-template-columns:repeat(2,1fr)}.stat-card{padding:15px}
  #question-card{padding:14px}#question-card .prose{font-size:16px}
  #practice-card{padding:18px 16px}#practice-card .prose{font-size:18px}
  .gradio-container{padding:6px !important}
}
@media(prefers-color-scheme:dark){
  #quiz-meta{background:#1f2430;}
  #feedback-card{background:#1c2130;}
}
'''
