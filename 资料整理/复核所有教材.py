from pathlib import Path
import json
import 提取章末习题 as E
for f in sorted(E.O.glob('*计划.json')):
 E.run(json.loads(f.read_text(encoding='utf-8')))
