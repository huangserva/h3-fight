# 用法：python3 ~/.claude/skills/h3-fight/工具/建库.py
# 从 库/来源/*.txt + 库/来源说明.json + 库/镜头标注.json 生成 库/镜头块.json（每个镜头一块：来源、等级、打法、用途、中文要点、五样、字数、起点秒、时间表、英文原文），
# 时间表 = 这条来源是按几秒排的：“15 秒”是旧的 6 镜时间表（0、1、4、7、10、12 秒），句子照样能搬，时间点要按 SKILL.md 的 5 镜表重排。
# 并给 词句.json 每条数出处（在几条 A 级来源里出现），写 库/词句出处.json；最后生成中文对照页。
import json, os, subprocess, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import *
说明 = json.load(open(os.path.join(库, '来源说明.json'), encoding='utf-8'))
标注 = json.load(open(os.path.join(库, '镜头标注.json'), encoding='utf-8'))
块 = []
for 名, v in 说明.items():
    if 名.startswith('_'): continue
    文 = 读(os.path.join(库, '来源', 名 + '.txt')); shots = 镜头(文); _, 点, 表 = 时间表(文)
    assert len(shots) == len(标注[名]), (名, len(shots), len(标注[名]))
    for (n, s), (用途, 要点), 秒 in zip(shots, 标注[名], 点):
        块.append({'编号': f'{名}-{n}', '来源': 名, '等级': v['等级'], '题材': 题材of(v), '打法': v['打法'], '风格': v['风格'], '用途': 用途,
                  '中文要点': 要点, '五样': 认五样(s), '字数': len(s), '起点秒': 秒, '时间表': 表, '成片': v['成片'], '英文原文': s})
json.dump(块, open(os.path.join(库, '镜头块.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
A = {名: 读(os.path.join(库, '来源', 名 + '.txt')).lower() for 名, v in 说明.items() if not 名.startswith('_') and v['等级'] == 'A'}
出处 = {e['键']: [名 for 名, t in A.items() if e['键'] in t] for e in 词句表()}
json.dump(出处, open(os.path.join(库, '词句出处.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
c = collections.Counter((b['等级'], b['用途']) for b in 块)
print('镜头块', len(块), '条；A 级', sum(b['等级'] == 'A' for b in 块), '条')
for (等级, 用途), k in sorted(c.items()): print(f'  {等级} {用途} {k}')
少 = [k for k, v in 出处.items() if not v]
print('词句', len(出处), '条；A 级来源里一次都没出现的键：', 少 or '无')
subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), '生成对照页.py')], check=True)   # 用当前这个 Python：Windows 上没有 python3 命令
