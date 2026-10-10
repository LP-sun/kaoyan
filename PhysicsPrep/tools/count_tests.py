"""统计每个测试文件的用例数与总数，用于生成 TEST_REPORT.md 的准确数据。"""
import subprocess
import sys

out = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '--co', '-q'],
                     capture_output=True, text=True).stdout
rows = []
for line in out.splitlines():
    if line.startswith('tests/') and ':' in line:
        name, _, count = line.rpartition(':')
        try:
            rows.append((name.strip(), int(count)))
        except ValueError:
            continue
total = sum(c for _, c in rows)
for name, count in rows:
    print('{:<34}{:>4}'.format(name, count))
print('{:<34}{:>4}'.format('TOTAL', total))
