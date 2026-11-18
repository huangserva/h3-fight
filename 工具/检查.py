# 用法：python3 ~/.claude/skills/h3-fight/工具/检查.py <提示词.txt> [...]  [--排除 来源名] [--题材 运动] [--旧时间表]
#   --题材 运动：滑雪等大动作运动。不要求作者的打戏招牌写法（只提醒），五样另认运动词，原句比例只和运动来源比，踩坑表按题材挑；其余门槛和打戏一样。
#   --旧时间表：库里照 15 秒片排的旧 6 镜来源（0、1、4、7、10、12 秒）。新写的提示词按 15 秒排是错误；核对、重出旧来源时加这个参数，降成提醒。
# 打戏提示词提交前必须过这一关：有“错误”就退出码 1，不准提交。“提醒”要写的人逐条确认。
# 查：六段齐不齐；镜头数和时间点；每镜五样；平均字数；作者 16 个招牌写法数了几个；动态机位；
#     和库里 A 级镜头的原句比例；踩坑表（库/踩坑.json）；道具状态有没有交代；
#     10 秒 5 镜的时间表（0 / 2 / 4.5 / 6.5 / 7.5）：镜头数、收尾够不够长、交手镜头会不会太短、1 秒特写里有没有塞动作。
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import *

# 门槛按好片和 b 版/v5 校准（11-14）：好片招牌 9–16、每镜 500+ 字、动态机位 2–4；b 版后几段招牌 5–8、274–440 字；v5 招牌 3、动态机位 0–1。
门槛 = dict(镜头数=(5, 7), 每镜五样=4, 最多缺样镜头=1, 平均字数=450, 招牌=9, 招牌够=12, 动态机位=2, 侧面最多=2, 原句比例=0.40)
动态 = r"orbit|crane|vertical rapid falling|falling alongside|spiraling|tracking shot circling|circling|push-in|diving"
旧时间表坑 = '10 秒片写成 15 秒的镜头时间'
片长 = 10.0   # H3 一段 243 帧，约 10 秒
# 1 秒特写里只放得下一张脸。写了这些动作，H3 要么把特写画成别的画面，要么只画出半招（浮桥追逐1f 第 4 镜、r20 起手仪式）。
特写动作 = r"\b(slash(es)?|swings?|swipes?|sweeps?|strikes?|kicks?|punch(es)?|leaps?|lunges?|dodges?|blocks?|deflects?|parr(y|ies)|pivots?|dives?|drops?|charges?|throws?|fires?|looses?|shoots?|swats?|lash(es)?|rush(es)?|grabs?|catch(es)?|ducks?|rolls?|jumps?|vaults?|thrusts?|chops?|slams?|hurls?|knocks?|smash(es)?)\b"
道具词 = ['bell', 'pillar', 'hall', 'gate', 'bridge', 'tree', 'lantern', 'pendant', 'statue', 'wall', 'stair', 'table']

def 查(path, 排除=None, 题材='打戏', 旧时间表=False):
    t = 读(path); tl = t.lower(); 错, 醒 = [], []
    运动 = 题材 == '运动'
    for sec in ['subject_definitions', 'summary', 'retention_analysis', 'detailed_description', 'overall_soundscape', 'non_diegetic_music']:
        if sec + ':' not in tl: 错.append(f'缺“{sec}”段（作者六段式）')
    shots = 镜头(t)
    if not 门槛['镜头数'][0] <= len(shots) <= 门槛['镜头数'][1]: 错.append(f'镜头数 {len(shots)}，要 5–7 个（每 2–3 秒一个）')
    没时间 = [n for n, s in shots[1:] if not re.search(r'At \d\d:\d\d', s)]
    if 没时间: 错.append(f'第 {没时间} 镜头没标时间点（At 00:0x.000）')
    _, 点, 表 = 时间表(t)
    if not 没时间 and any(a >= b for a, b in zip(点, 点[1:])): 错.append(f'镜头时间点要一个比一个晚：{点}')
    elif not 没时间 and 表 == '10 秒' and not 运动:
        # 10 秒 5 镜：0 / 2 / 4.5 / 6.5（特写）/ 7.5（制胜 + 收尾）。只提醒：时间点可以挪，但这几样挪过头片子就坏。
        长 = [b - a for a, b in zip(点, 点[1:] + [片长])]
        if len(shots) > 5: 醒.append(f'{len(shots)} 个镜头排在 10 秒里：H3 一段放得下 5 镜（0 / 2 / 4.5 / 6.5 / 7.5 秒），多出来的镜头会被挤到 1 秒以内，招只画一半')
        if 长[-1] < 2: 醒.append(f'最后一镜从 {点[-1]:g} 秒开始，只剩 {长[-1]:g} 秒：制胜一招加稳定收尾要 2.5 秒左右（7.5 秒开始），不然收尾全景站不住')
        特写镜 = [n for (n, s), l in zip(shots, 长) if l <= 1.25 and 'close-up' in s.lower()]
        短 = [f'第 {n} 镜 {l:g} 秒' for (n, s), l in zip(shots[:-1], 长[:-1]) if l < 1.5 and n not in 特写镜]
        if 短: 醒.append(f'交手镜头太短：{"、".join(短)}。一个完整回合（起手→接挡→反应）约 1 秒，交手镜头留 2 秒以上；只有脸部特写可以 1 秒')
        for (n, s), l in zip(shots, 长):
            动作 = sorted({m.group(0) for m in re.finditer(特写动作, s.lower())})
            if n in 特写镜 and len(动作) >= 2:
                醒.append(f'第 {n} 镜是 {l:g} 秒的特写，却写了动作（{"、".join(动作)}）：1 秒只放得下一张脸，动作挪到前后的交手镜头里（见踩坑“1 秒特写里写了别的东西”）')
    缺样 = []
    for n, s in shots:
        有 = 认五样(s, 题材)
        if len(有) < 门槛['每镜五样']: 缺样.append((n, [k for k in 五样 if k not in 有]))
    if len(缺样) > 门槛['最多缺样镜头'] or any(len(m) > 2 for _, m in 缺样):
        错.append('五样不齐：' + '；'.join(f'第 {n} 镜头缺 {"、".join(m)}' for n, m in 缺样))
    elif 缺样: 醒.append('五样：' + '；'.join(f'第 {n} 镜头缺 {"、".join(m)}（收尾/特写镜头可以）' for n, m in 缺样))
    均 = sum(len(s) for _, s in shots) / max(1, len(shots))
    if 均 < 门槛['平均字数']: 错.append(f'每镜平均 {均:.0f} 字符，太空（好片每镜 500+，要 ≥ {门槛["平均字数"]}）')
    有, 缺 = 数招牌(t)
    if 运动:
        if len(有) < 5: 醒.append(f'运动题材：招牌写法 {len(有)}/16。不硬凑打戏词，但 rhythm instantly doubles、zero lag、slow-motion、in one fluid motion 这类节奏词放进去，镜头更有劲')
    elif len(有) < 门槛['招牌']: 错.append(f'作者招牌写法只用了 {len(有)}/16，要 ≥ {门槛["招牌"]}；缺：{", ".join(缺)}')
    elif len(有) < 门槛['招牌够']: 醒.append(f'作者招牌写法 {len(有)}/16，偏少（k3b 12、作者 16）；缺：{", ".join(缺)}')
    动 = sum(bool(re.search(动态, s.lower())) for _, s in shots)
    侧 = sum('side' in s.lower() and ('tracking' in s.lower() or 'profile' in s.lower()) for _, s in shots)
    if 动 < 门槛['动态机位']: 错.append(f'动态机位镜头 {动} 个，要 ≥ {门槛["动态机位"]}（环绕、摇臂、垂直下坠、螺旋推进）')
    if 侧 > 门槛['侧面最多']: 错.append(f'侧面机位 {侧} 个，最多 {门槛["侧面最多"]}')
    比 = 原句比例(t, 排除, 题材)
    if 运动 and 比 < 门槛['原句比例']: 醒.append(f'运动库原句比例 {比:.0%}：先从运动来源（库/来源说明.json 里 题材=运动）的镜头整句改，换项目再改名词')
    elif 比 < 门槛['原句比例']: 醒.append(f'库原句比例 {比:.0%}，要 ≥ {门槛["原句比例"]:.0%}：镜头要从库里的镜头块整句改，别从头写')
    for 坑 in json.load(open(os.path.join(库, '踩坑.json'), encoding='utf-8'))['坑']:
        if not 坑['检测'] or 坑.get('题材', '通用') not in ('通用', 题材): continue
        m = re.search(坑['检测'], tl if 坑['检测'] != '<d>' else t)
        if m:
            降 = 旧时间表 and 坑['名'] == 旧时间表坑
            (错 if 坑['级别'] == '错误' and not 降 else 醒).append(f'踩坑“{坑["名"]}”：“{m.group(0)}” → {坑["改法"]}（{坑["改法状态"]}）')
    # 特写没写视线：人物会正对镜头说话，像对着观众，不看对手。
    视线 = r"(eyes|gaze|glar\w*|star\w*|look\w*)\W+(\w+\W+){0,6}?(at|on|toward|towards) (<subject|him\b|her\b|his (opponent|rival|enemy)|the (opponent|rival|enemy))|over (<subject \d>'s|his|her) shoulder|three-quarter|in profile"
    没视线 = [n for n, s in shots if re.search(r'close-up', s.lower()) and re.search(r"face", s.lower()) and not re.search(视线, s.lower())]
    if 没视线: 醒.append(f'第 {没视线} 镜头是脸部特写，没写视线朝谁：会画成正对镜头。写成过肩特写（over <Subject n>\'s shoulder）或三分之四侧脸，眼睛盯着对手（见踩坑“人物正对镜头”）')
    定义 = tl.split('summary:')[0]
    镜文 = ' '.join(s for _, s in shots).lower()
    没交代 = [w for w in 道具词 if re.search(rf'\b{w}', 镜文) and not re.search(rf'\b{w}', 定义)]
    if 没交代: 醒.append(f'镜头里有这些道具，场景定义没交代状态：{", ".join(没交代)}（后面还要用的道具写清状态）')
    if 运动:
        # 靠冲力的动作：首帧是静止画面，H3 不知道人原来的速度（滑雪第 3 版原地起跳）
        第一 = shots[0][1].lower() if shots else ''
        if 'first frame' in 第一 and not re.search(r'already (moving|racing|skiing|riding|flying)|keeps? the momentum|at full speed|(skis|races|rides|charges) fast|racing', 第一):
            醒.append('第 1 镜接首帧，但没写他已经在高速运动（already racing … keeps the momentum）：H3 会让人从静止重新起步，冲力断掉（见踩坑“首帧静止丢速度”）')
        # 方向性很强的动作（空翻、转体）光靠文字压不住：要挂关键帧/姿势图，并写“这一刻就是 <Picture n>”
        if re.search(r'flip|somersault|\b(360|540|720)\b|cork', 镜文) and not re.search(r'exactly like <subject \d+> in <picture \d+>', tl):
            错.append('有空翻/转体，但没有“exactly like <Subject n> in <Picture n>”：方向性动作光靠文字压不住（滑雪第 3–5 版写了后空翻都画成前空翻），要挂关键帧或姿势图钉住（见 运动.md“关键帧”）')
    return 错, 醒, dict(镜头=len(shots), 平均字数=round(均), 招牌=len(有), 动态机位=动, 原句比例=f'{比:.0%}')

if __name__ == '__main__':
    a = sys.argv[1:]; 排除 = None; 题材 = '打戏'; 旧 = '--旧时间表' in a
    if 旧: a.remove('--旧时间表')
    if '--排除' in a: i = a.index('--排除'); 排除 = a[i + 1]; del a[i:i + 2]
    if '--题材' in a: i = a.index('--题材'); 题材 = a[i + 1]; del a[i:i + 2]
    坏 = 0
    for p in a:
        错, 醒, 数 = 查(p, 排除, 题材, 旧)
        print(f'== {os.path.basename(p)}（{题材}）：{"通过" if not 错 else "不通过"}  {数}')
        for x in 错: print('  错误：' + x)
        for x in 醒: print('  提醒：' + x)
        坏 |= bool(错)
    sys.exit(1 if 坏 else 0)
