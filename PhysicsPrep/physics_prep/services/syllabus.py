"""大纲文件本地版本归档，不上传或自动认定为官方年度大纲。"""
import hashlib
import json
import shutil
from pathlib import Path

class SyllabusArchive:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.index=self.root/'versions.json'

    def list_versions(self):
        return json.loads(self.index.read_text(encoding='utf-8')) if self.index.exists() else []

    def import_version(self,path,label,subject):
        path=Path(path)
        if path.suffix.lower() not in ('.pdf','.json','.txt','.csv'):raise ValueError('大纲仅支持PDF/JSON/TXT/CSV归档')
        if path.stat().st_size>20*1024*1024:raise ValueError('大纲文件超过20MB')
        if not label.strip():raise ValueError('请填写大纲版本说明，无法确认年份时标为待核')
        digest=hashlib.sha256(path.read_bytes()).hexdigest();name=digest[:24]+path.suffix.lower()
        dest=self.root/name
        if not dest.exists():shutil.copyfile(path,dest)
        rows=self.list_versions()
        if any(r['sha256']==digest and r['subject']==subject and r['label']==label.strip() for r in rows):return rows
        rows.append({'label':label.strip(),'subject':subject,'sha256':digest,'file':name,'official_status':'用户导入，年份与官方有效性待核'})
        tmp=self.index.with_suffix('.tmp');tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(self.index)
        return rows
