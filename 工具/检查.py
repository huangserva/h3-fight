# 用法：python3 ~/.claude/skills/h3-fight/工具/检查.py <提示词.txt> [...]  [--排除 来源名]
# 打戏提示词提交前必须过这一关：有“错误”就退出码 1，不准提交。“提醒”要写的人逐条确认。
# 查：六段齐不齐；镜头数和时间点；每镜五样；平均字数；作者 16 个招牌写法数了几个；动态机位；
#     和库里 A 级镜头的原句比例；踩坑表（库/踩坑.json）；道具状态有没有交代。
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import *

# 门槛按好片和 b 版/v5 校准（11-14）：好片招牌 9–16、每镜 500+ 字、动态机位 2–4；b 版后几段招牌 5–8、274–440 字；v5 招牌 3、动态机位 0–1。
门槛 = dict(镜头数=(5, 7), 每镜五样=4, 最多缺样镜头=1, 平均字数=450, 招牌=9, 招牌够=12, 动态机位=2, 侧面最多=2, 原句比例=0.40)
动态 = r"orbit|crane|vertical rapid falling|falling alongside|spiraling|tracking shot circling|circling|push-in|diving"
道具词 = ['bell', 'pillar', 'hall', 'gate', 'bridge', 'tree', 'lantern', 'pendant', 'statue', 'wall', 'stair', 'table']

def 查(path, 排除=None):
    t = 读(path); tl = t.lower(); 错, 醒 = [], []
    for sec in ['subject_definitions', 'summary', 'retention_analysis', 'detailed_description', 'overall_soundscape', 'non_diegetic_music']:
        if sec + ':' not in tl: 错.append(f'缺“{sec}”段（作者六段式）')
    shots = 镜头(t)
    if not 门槛['镜头数'][0] <= len(shots) <= 门槛['镜头数'][1]: 错.append(f'镜头数 {len(shots)}，要 5–7 个（每 2–3 秒一个）')
    没时间 = [n for n, s in shots[1:] if not re.search(r'At \d\d:\d\d', s)]
    if 没时间: 错.append(f'第 {没时间} 镜头没标时间点（At 00:0x.000）')
    缺样 = []
    for n, s in shots:
        有 = 认五样(s)
        if len(有) < 门槛['每镜五样']: 缺样.append((n, [k for k in 五样 if k not in 有]))
    if len(缺样) > 门槛['最多缺样镜头'] or any(len(m) > 2 for _, m in 缺样):
        错.append('五样不齐：' + '；'.join(f'第 {n} 镜头缺 {"、".join(m)}' for n, m in 缺样))
    elif 缺样: 醒.append('五样：' + '；'.join(f'第 {n} 镜头缺 {"、".join(m)}（收尾/特写镜头可以）' for n, m in 缺样))
    均 = sum(len(s) for _, s in shots) / max(1, len(shots))
    if 均 < 门槛['平均字数']: 错.append(f'每镜平均 {均:.0f} 字符，太空（好片每镜 500+，要 ≥ {门槛["平均字数"]}）')
    有, 缺 = 数招牌(t)
    if len(有) < 门槛['招牌']: 错.append(f'作者招牌写法只用了 {len(有)}/16，要 ≥ {门槛["招牌"]}；缺：{", ".join(缺)}')
    elif len(有) < 门槛['招牌够']: 醒.append(f'作者招牌写法 {len(有)}/16，偏少（k3b 12、作者 16）；缺：{", ".join(缺)}')
    动 = sum(bool(re.search(动态, s.lower())) for _, s in shots)
    侧 = sum('side' in s.lower() and ('tracking' in s.lower() or 'profile' in s.lower()) for _, s in shots)
    if 动 < 门槛['动态机位']: 错.append(f'动态机位镜头 {动} 个，要 ≥ {门槛["动态机位"]}（环绕、摇臂、垂直下坠、螺旋推进）')
    if 侧 > 门槛['侧面最多']: 错.append(f'侧面机位 {侧} 个，最多 {门槛["侧面最多"]}')
    比 = 原句比例(t, 排除)
    if 比 < 门槛['原句比例']: 醒.append(f'库原句比例 {比:.0%}，要 ≥ {门槛["原句比例"]:.0%}：镜头要从库里的镜头块整句改，别从头写')
    for 坑 in json.load(open(os.path.join(库, '踩坑.json'), encoding='utf-8'))['坑']:
        if not 坑['检测']: continue
        m = re.search(坑['检测'], tl if 坑['检测'] != '<d>' else t)
        if m:
            (错 if 坑['级别'] == '错误' else 醒).append(f'踩坑“{坑["名"]}”：“{m.group(0)}” → {坑["改法"]}（{坑["改法状态"]}）')
    # 特写没写视线：人物会正对镜头说话，像对着观众，不看对手。
    视线 = r"(eyes|gaze|glar\w*|star\w*|look\w*)\W+(\w+\W+){0,6}?(at|on|toward|towards) (<subject|him\b|her\b|his (opponent|rival|enemy)|the (opponent|rival|enemy))|over (<subject \d>'s|his|her) shoulder|three-quarter|in profile"
    没视线 = [n for n, s in shots if re.search(r'close-up', s.lower()) and re.search(r"face", s.lower()) and not re.search(视线, s.lower())]
    if 没视线: 醒.append(f'第 {没视线} 镜头是脸部特写，没写视线朝谁：会画成正对镜头。写成过肩特写（over <Subject n>\'s shoulder）或三分之四侧脸，眼睛盯着对手（见踩坑“人物正对镜头”）')
    定义 = tl.split('summary:')[0]
    镜文 = ' '.join(s for _, s in shots).lower()
    没交代 = [w for w in 道具词 if re.search(rf'\b{w}', 镜文) and not re.search(rf'\b{w}', 定义)]
    if 没交代: 醒.append(f'镜头里有这些道具，场景定义没交代状态：{", ".join(没交代)}（后面还要用的道具写清状态）')
    return 错, 醒, dict(镜头=len(shots), 平均字数=round(均), 招牌=len(有), 动态机位=动, 原句比例=f'{比:.0%}')

if __name__ == '__main__':
    a = sys.argv[1:]; 排除 = None
    if '--排除' in a: i = a.index('--排除'); 排除 = a[i + 1]; del a[i:i + 2]
    坏 = 0
    for p in a:
        错, 醒, 数 = 查(p, 排除)
        print(f'== {os.path.basename(p)}：{"通过" if not 错 else "不通过"}  {数}')
        for x in 错: print('  错误：' + x)
        for x in 醒: print('  提醒：' + x)
        坏 |= bool(错)
    sys.exit(1 if 坏 else 0)
