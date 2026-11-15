# 多段打戏查“动作单一”：数每段每个镜头用了哪几类打法（库/招式表.json），看整片有多少类、哪类用太多、各段节拍是不是一样。
# 用法：python3 查重复.py s1.txt s2.txt s3.txt ...   只提醒，不拦。
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import 读, 镜头, 库
表 = json.load(open(os.path.join(库, '招式表.json'), encoding='utf-8'))
类 = 表['类']; 细分 = 表.get('近身细分', [])
笼统 = r"trade[sd]? (punches|blows)|exchange[sd]? (punches|blows)|flurry of (punches|blows)|punches and kicks at|(furious|fast|rapid) (close-range )?combo|barrage of (punches|blows)|rain(s)? (of )?(punches|blows)"
细总 = collections.Counter(); 笼统镜 = []
总 = collections.Counter(); 段主 = []; 段类 = []; 段拍 = []
标志 = [('冲', 'supersonic charge|burst forward'), ('三连', 'three ultra-high-speed'), ('特写', 'orbits 360'), ('下坠', 'vertical rapid falling'), ('拉远', 'pull-back')]
for f in sys.argv[1:]:
    c = collections.Counter(); 拍 = []
    for n, s in 镜头(读(f)):
        拍.append('/'.join(a for a, r in 标志 if re.search(r, s.lower())) or '-')
        for k in 类:
            if re.search(k['认'], s.lower()): c[k['名']] += 1
        细 = [k['名'] for k in 细分 if re.search(k['认'], s.lower())]
        细总.update(细)
        if re.search(笼统, s.lower()) and len(细) < 2: 笼统镜.append(f'{os.path.basename(f)} 第 {n} 镜')
    段拍.append(tuple(拍)); 总.update(c); 段类.append(set(c)); 段主.append([k for k, _ in c.most_common(3)])
    print(f'{os.path.basename(f)}：{len(c)} 类  ' + '、'.join(f'{k}×{v}' for k, v in c.most_common()))
醒 = []
全 = sum(总.values()) or 1
if len(总) < 6: 醒.append(f'整片只用了 {len(总)} 类打法，要 ≥ 6')
for k, v in 总.most_common(2):
    if v / 全 > 0.25: 醒.append(f'“{k}”占 {v * 100 // 全}%，太多（≤ 25%）')
for i in range(1, len(段主)):
    if 段主[i][:2] == 段主[i - 1][:2]: 醒.append(f'第 {i} 段和第 {i + 1} 段主打法一样：{"、".join(段主[i][:2])}')
位 = collections.Counter((i, a) for 拍 in 段拍 for i, x in enumerate(拍) for a in x.split('/') if a not in ('-', '特写', '拉远'))
for (i, a), v in sorted(位.items()):
    if len(段拍) >= 3 and v / len(段拍) >= 0.6: 醒.append(f'{v}/{len(段拍)} 段的第 {i + 1} 镜都是“{a}”，节拍重复：这个位置在各段之间换打法（见 招式表.json）')
if 细分:
    print('近身细分：', '、'.join(f'{k}×{v}' for k, v in 细总.most_common()) or '无')
    if len(细总) < 6: 醒.append(f'近身手部对打只用了 {len(细总)} 种细分，要 ≥ 6（见 招式表.json 近身细分）')
    for k, v in 细总.items():
        if k == '对拳互抵' and v > 1: 醒.append(f'“对拳互抵”用了 {v} 次，最容易用烂，整片最多 1 次')
        elif v > 2: 醒.append(f'近身细分“{k}”用了 {v} 次，同一种最多 2 次')
    if 笼统镜: 醒.append('这些镜头只写了笼统的对打（trade punches / flurry / combo），没写具体回合：' + '、'.join(笼统镜) + '。每个近身镜头写 ≥ 3 个“谁出什么招 → 对方怎么接/怎么挨”')
没用 = [k['名'] for k in 类 if k['名'] not in 总]
print('整片：', len(总), '类；没用到：', '、'.join(没用))
for m in 醒: print('  提醒：' + m)
if not 醒: print('  没发现单一问题')
