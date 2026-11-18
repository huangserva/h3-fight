# 打戏 skill 共用：读提示词、切镜头、认五样、数招牌、算库原句比例。建库.py 和 检查.py 都用它。
import json, re, os
根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
库 = os.path.join(根, '库')

def 配置():
    """读 skill 根目录的 config.json（不进仓库）；没有就用 config.example.json 的默认值。"""
    for 名 in ('config.json', 'config.example.json'):
        p = os.path.join(根, 名)
        if os.path.exists(p):
            return {k: v for k, v in json.load(open(p, encoding='utf-8')).items() if not k.startswith('_')}
    return {}

# 五样：每个镜头都该写齐（收尾、特写镜头可以少招式）
五样 = {
 '运镜': r"camera|close-up|tracking|orbit|crane|pull-back|push-in|tilts?\b|wide shot|wide-angle|low-angle|high-angle|falling shot|establishing shot|two-shot|medium shot",
 '招式': r"slash|thrust|strike|\bcuts?\b|block|parr|deflect|dodg|\bkick|punch|leap|dash|charge|\bspin|counter|chop|lunge|\bflip|sweep|swing|dive|bursts? forward|pushes off|vault|draws?\b",
 '后果': r"crack|shatter|collaps|crater|debris|dust|explod|explosion|torn|tear|split|slice|toppl|goug|sliding|crash|blast|break|smash|fragment|groove|ring of|scatter|eject",
 '特效': r"sword qi|energy|glow|flame|rune|shockwave|impact wave|spark|\barc\b|afterimage|light\b|sword-light|embers?",
 '节奏': r"slow-motion|slow motion|rhythm|instantly|without drag|zero lag|freez|blinding speed|supersonic|in one fluid motion|camera shake|ultra-high-speed|at the same instant|within the first|in one flash|in one motion",
}

def 读(path):
    return open(path, encoding='utf-8').read()

def 镜头(text):
    """返回 [(镜头号, 文字)]，文字不含 [Shot n] 标签。"""
    return [(int(m.group(1)), m.group(2).strip()) for m in re.finditer(r'^\[Shot (\d+)\]\s*(.*)$', text, re.M)]

def 时间表(text):
    """这条提示词的镜头是按几秒排的：返回（镜头数, 每镜从第几秒开始, '10 秒' 或 '15 秒'）。
    有镜头 9 秒以后才开始，就是照 15 秒片排的旧时间表（0、1、4、7、10、12 秒）：H3 只出 10 秒，最后两镜会被挤成各 1 秒
    （见踩坑“10 秒片写成 15 秒的镜头时间”，它的检测正则认的是同一件事）。第 1 镜总是从 0 秒开始（它里面写的时间点是镜头中途的）。"""
    点 = []
    for i, (_, s) in enumerate(镜头(text)):
        m = re.search(r'At (\d\d):(\d\d(?:\.\d+)?)', s)
        点.append(0.0 if i == 0 else int(m.group(1)) * 60 + float(m.group(2)) if m else None)
    return len(点), 点, '15 秒' if any(t is not None and t >= 9 for t in 点) else '10 秒'

# 运动题材（滑雪等）补充的五样词：只在 题材=运动 时加进去，打戏的认法不变。
运动五样 = {
 '招式': r"tuck|carv|turn|takeoff|takes off|pops?\b|backflip|front ?flip|rotat|lands?\b|touches down|slams down|straight-lines|accelerat|rides? (up|away|out)|hockey stop",
 '后果': r"spray|plume|rooster tail|powder (bursts?|explodes?)|snow (bursts?|explodes?|streams?)|sinks?\b|crater|tracks?\b",
 '特效': r"glitter|sparkl|sun ?flare|sunlight|golden light|snow crystals|rim light",
}

def 认五样(s, 题材='打戏'):
    t = s.lower()
    return [k for k, p in 五样.items() if re.search(p, t) or (题材 == '运动' and k in 运动五样 and re.search(运动五样[k], t))]

def 题材of(v):
    """来源说明里没写题材的，都是打戏。"""
    return v.get('题材', '打戏')

def 词句表():
    d = json.load(open(os.path.join(库, '词句.json'), encoding='utf-8'))
    return [dict(e, 要素=k) for k, v in d.items() if not k.startswith('_') for e in v]

def 数招牌(text):
    t = text.lower()
    招牌 = [e for e in 词句表() if e['招牌']]
    有 = [e['键'] for e in 招牌 if e['键'] in t]
    return 有, [e['键'] for e in 招牌 if e['键'] not in t]

def 词(s): return re.findall(r"[a-z0-9']+", s.lower())
def 五元(w, n=5): return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}

def 库原文(排除=None, 等级=('A',), 题材='打戏'):
    """A 级来源全部镜头文字的 5 词片段集合；排除 = 来源名（自测时去掉自己）；只算同题材（打戏 / 运动）的来源。"""
    说明 = json.load(open(os.path.join(库, '来源说明.json'), encoding='utf-8'))
    池 = set()
    for 名, v in 说明.items():
        if 名.startswith('_') or v['等级'] not in 等级 or 名 == 排除 or 题材of(v) != 题材: continue
        for _, s in 镜头(读(os.path.join(库, '来源', 名 + '.txt'))):
            池 |= 五元(词(s))
    return 池

def 原句比例(text, 排除=None, 题材='打戏'):
    g = 五元(词(' '.join(s for _, s in 镜头(text))))
    return len(g & 库原文(排除, 题材=题材)) / max(1, len(g))
