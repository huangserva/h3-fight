# 用法：python3 工具/生成对照页.py   （建库.py 最后会自动调）
# 把库生成一页中文对照（默认写到 skill 根目录的 库对照.md；config.json 的 library_page 可改位置）。库本身给 AI 用，这页给人看。
import json, os, sys, collections, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import *
C = 配置()
页 = os.path.expanduser(C.get('library_page') or os.path.join(根, '库对照.md')); os.makedirs(os.path.dirname(页), exist_ok=True)
片根 = os.path.expanduser(C.get('video_root') or '')
块 = json.load(open(os.path.join(库, '镜头块.json'), encoding='utf-8'))
出处 = json.load(open(os.path.join(库, '词句出处.json'), encoding='utf-8'))
坑 = json.load(open(os.path.join(库, '踩坑.json'), encoding='utf-8'))['坑']
说明 = json.load(open(os.path.join(库, '来源说明.json'), encoding='utf-8'))
链 = lambda p: (f'[{os.path.basename(p)}]({urllib.parse.quote(片根 + p)})' if 片根 else os.path.basename(p)) if p else '—'
L = ['# 打戏 H3 提示词库（中文对照）', '',
     f'自动生成，别手改；改库请改 `库/` 再跑 `工具/建库.py`。镜头块 {len(块)} 条，词句 {len(出处)} 条，踩坑 {len(坑)} 条。', '',
     '## 怎么用', '',
     '- 打戏镜头要交给 H3 时，先调 `h3-fight` skill：按每个节拍的“用途”和“打法”挑 A 级镜头块，整句搬过来，只换人物、武器、颜色、场景物件，拼成 6 个镜头。',
     '- 写完跑 `检查.py`，有“错误”不准提交。门槛按好片校准：库里的好片全部通过，已知写得差的全部不通过。',
     '- 看片发现新问题 → 加进踩坑表；新写法出了好片 → 加进来源和镜头块。', '',
     '## 来源', '', '| 来源 | 等级 | 打法 | 风格 | 成片 | 为什么收 |', '|---|---|---|---|---|---|']
for 名, v in 说明.items():
    if not 名.startswith('_'): L.append(f'| {名} | {v["等级"]} | {v["打法"]} | {v["风格"]} | {链(v["成片"])} | {v["为什么收"]} |')
L += ['', '等级：A = 出片后人工看过、认为好；B = 写法偏短，只当打法参考；衔接 = 好片里的非打斗镜头。', '', '## 镜头块（按用途）', '']
by = collections.defaultdict(list)
for b in 块: by[b['用途']].append(b)
顺序 = ['开场爆发', '对冲交锋', '近身快打', '三连反击', '闪避', '腾空剑气', '空中对决', '大招对撞', '特写蓄力', '硬接反击', '锁刀相抵', '制胜缴械', '落地对峙', '收尾', '登场', '对峙', '收刀离去']
for 用 in 顺序 + [k for k in by if k not in 顺序]:
    if 用 not in by: continue
    L += [f'### {用}（{len(by[用])} 条）', '']
    for b in sorted(by[用], key=lambda b: ('A', 'B', '衔接').index(b['等级'])):
        L.append(f'- **{b["编号"]}**（{b["等级"]}，{b["打法"]}，{len(b["五样"])}/5 样，{b["字数"]} 字）：{b["中文要点"]}')
        L.append(f'  <details><summary>英文原文</summary>\n\n  {b["英文原文"]}\n\n  </details>')
    L.append('')
L += ['## 词句零件', '', '★ = 作者 16 个招牌写法，检查时要数够。出处 = 在几条 A 级来源里出现过。', '']
for 要, es in json.load(open(os.path.join(库, '词句.json'), encoding='utf-8')).items():
    if 要.startswith('_'): continue
    L += [f'### {要}', '', '| 中文 | 适合描述什么 | 出处 | 英文 |', '|---|---|---|---|']
    for e in es:
        L.append(f'| {"★ " if e["招牌"] else ""}{e["中文"]} | {e["适合"]} | {len(出处.get(e["键"], []))} | {e["词句"]} |')
    L.append('')
L += ['## 踩坑表', '', '| 坑 | 现象 | 出处 | 级别 | 改法 | 改法状态 |', '|---|---|---|---|---|---|']
for k in 坑: L.append(f'| {k["名"]} | {k["现象"]} | {k["出处"]} | {k["级别"]} | {k["改法"]} | {k["改法状态"]} |')
open(页, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('对照页：', 页)
