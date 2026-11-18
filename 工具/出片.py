# 用法：
#   python3 工具/出片.py <提示词.txt> --名字 k4c --输出 <本地目录>
#        [--参考图 人物.png 场景.png 对手.png] [--加参考图 第4张.png ...] [--首帧 上一段最后一帧.png] [--种子 1] [--不等]
#        [--题材 运动]     滑雪等大动作运动：检查按运动门槛（不要求打戏招牌写法），不通过照样不提交。部件不换（打戏 LoRA 对滑雪也稳人和器材）。
#        [--非打斗 "理由"]  变身、登场、收刀这类不是打斗的衔接段：检查只打印不拦，理由记进提交记录。部件照旧不换。
#        [--只导出]        只生成 ComfyUI 工作流 JSON（API 格式），不提交；可以自己拖进 ComfyUI 或用别的方式跑。
# 先跑 检查.py，不通过就停（不提交）。有参考图用 库/模板/三参考图.json，没有用 库/模板/无参考图.json。
# 部件一律照模板（2549 int8、turbo 0.7、SelfLift TST τ0.2、Fight_Flow 0.65 / Combat_V2 0.5 / Motion_Repair 0.25、
# euler 8 步 + SigmaRefiner、1664×928、243 帧），这里只换：提示词、参考图、首帧引导、种子、输出名。不钉尾帧（会把打法压死）。
# 提交到哪由 skill 根目录的 config.json 决定（见 config.example.json）：
#   mode=local：ComfyUI 在本机或局域网，走 HTTP（上传图、提交、轮询、下载）；
#   mode=ssh  ：ComfyUI 在远程机器上，经 ssh/scp 上传、提交、下载。
# 出完下载到 --输出，出每半秒拼图，跑一遍查字幕。
import argparse, json, os, subprocess, sys, time, uuid, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import 库, 配置
from 检查 import 查

C = 配置()
模式 = C.get('mode', 'local'); 地址 = C.get('comfy_url', 'http://127.0.0.1:8188').rstrip('/')
主机 = C.get('ssh_host', ''); 远 = C.get('remote_comfy_dir', ''); 子目录 = C.get('output_subfolder', 'h3_fight')

a = argparse.ArgumentParser(); a.add_argument('提示词'); a.add_argument('--名字', required=True); a.add_argument('--输出', required=True)
a.add_argument('--参考图', nargs='+'); a.add_argument('--首帧'); a.add_argument('--种子', type=int, default=1); a.add_argument('--不等', action='store_true')
a.add_argument('--加参考图', nargs='+', default=[]); a.add_argument('--非打斗'); a.add_argument('--题材', default='打戏', choices=['打戏', '运动']); a.add_argument('--只导出', action='store_true')
o = a.parse_args(); os.makedirs(o.输出, exist_ok=True)

错, 醒, 数 = 查(o.提示词, 题材=o.题材)
print(f'检查（{o.题材}）：', '通过' if not 错 else '不通过', 数)
for x in 错 + 醒: print('  ', x)
if 错 and not o.非打斗: sys.exit('检查不通过，没有提交。先改提示词。')
if 错: print('非打斗段，检查不拦：', o.非打斗)

# ---------- 两种连接方式 ----------
def ssh(cmd):
    while True:
        r = subprocess.run(['ssh', '-o', 'ConnectTimeout=20', 主机, cmd], capture_output=True, text=True)
        if r.returncode == 0: return r.stdout
        time.sleep(10)

def http(path, data=None, headers=None):
    req = urllib.request.Request(地址 + path, data=data, headers=headers or {})
    for _ in range(30):
        try: return urllib.request.urlopen(req, timeout=60).read()
        except OSError: time.sleep(10)
    sys.exit(f'连不上 ComfyUI：{地址}（检查 config.json 的 comfy_url，或先跑 工具/自检.py）')

def 上传(本地):
    """把图传到 ComfyUI 的 input 目录，返回 ComfyUI 里的文件名。"""
    if 模式 == 'ssh':
        while subprocess.run(['scp', '-q', 本地, f'{主机}:{远}/input/']).returncode: time.sleep(10)
        return os.path.basename(本地)
    边界 = uuid.uuid4().hex; 名 = os.path.basename(本地)
    体 = (f'--{边界}\r\nContent-Disposition: form-data; name="image"; filename="{名}"\r\nContent-Type: image/png\r\n\r\n').encode() \
        + open(本地, 'rb').read() + f'\r\n--{边界}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{边界}--\r\n'.encode()
    return json.loads(http('/upload/image', 体, {'Content-Type': f'multipart/form-data; boundary={边界}'}))['name']

def 提交(工作流):
    if 模式 == 'ssh':
        任务 = os.path.join(o.输出, f'{o.名字}.json')
        ssh('mkdir -p /tmp/h3_fight')
        while subprocess.run(['scp', '-q', 任务, f'{主机}:/tmp/h3_fight/']).returncode: time.sleep(10)
        r = ssh(f"""cd /tmp/h3_fight && python3 -c "
import json,urllib.request
g=json.load(open('{o.名字}.json'))
print(urllib.request.urlopen(urllib.request.Request('{地址}/prompt',data=json.dumps({{'prompt':g}}).encode(),headers={{'Content-Type':'application/json'}})).read().decode())" """)
        return json.loads(r)['prompt_id']
    return json.loads(http('/prompt', json.dumps({'prompt': 工作流}).encode(), {'Content-Type': 'application/json'}))['prompt_id']

def 历史(pid):
    raw = ssh(f'curl -s {地址}/history/{pid}') if 模式 == 'ssh' else http(f'/history/{pid}').decode()
    return json.loads(raw or '{}').get(pid, {})

# ---------- 拼工作流 ----------
# 模板是 ComfyUI 的 API 格式工作流。不认节点编号，按作用找节点，所以自己搭的工作流也能用（搭法见 docs/工作流怎么搭.md）：
#   条件节点 = 有 prompt 和 clip 输入的节点（MiniMaxH3ReferenceToVideo / MiniMaxH3AudioConditioningT8）；
#   采样节点 = 有 seed 输入的节点；保存节点 = 有 filename_prefix 的节点；参考图 = 接在条件节点 ref_images.ref_image_N 上的 LoadImage。
模名 = '三参考图.json' if o.参考图 else '无参考图.json'; 模路 = os.path.join(库, '模板', 模名)
if not os.path.exists(模路):
    sys.exit(f'没有工作流模板 库/模板/{模名}。照 docs/工作流怎么搭.md 在 ComfyUI 里搭好，用“导出（API）”存成这个文件名。')
j = json.load(open(模路, encoding='utf-8'))
j = {k: v for k, v in j.items() if not k.startswith('_')}
找 = lambda f: [k for k, v in j.items() if f(v)]
条 = 找(lambda v: 'prompt' in v['inputs'] and 'clip' in v['inputs']); 采 = 找(lambda v: 'seed' in v['inputs']); 存 = 找(lambda v: 'filename_prefix' in v['inputs'])
if len(条) != 1 or not 采 or not 存: sys.exit(f'{模名} 里找不到唯一的条件节点 / 采样节点 / 保存节点（条件 {条}、采样 {采}、保存 {存}）')
条 = 条[0]; 条入 = j[条]['inputs']
条入['prompt'] = open(o.提示词, encoding='utf-8').read()
新号 = lambda: str(max(int(k) for k in j if k.isdigit()) + 1)
传 = (lambda p: os.path.basename(p)) if o.只导出 else 上传
if o.参考图:
    槽 = sorted(((int(k.rsplit('_', 1)[1]), v[0]) for k, v in 条入.items() if k.startswith('ref_images.ref_image_') and isinstance(v, list)))
    for i, p in enumerate(o.参考图 + o.加参考图):
        assert i < 9, 'H3 参考图最多 9 张'
        名 = 传(p) if os.path.exists(p) else p  # 不存在的当成 ComfyUI input 里已有的文件名
        if i < len(槽): j[槽[i][1]]['inputs']['image'] = 名
        else:
            k = 新号(); j[k] = {'class_type': 'LoadImage', 'inputs': {'image': 名}}; 条入[f'ref_images.ref_image_{i}'] = [k, 0]
    for n, k in 槽[len(o.参考图 + o.加参考图):]:   # 模板里多出来、这次没用上的参考图槽去掉
        del 条入[f'ref_images.ref_image_{n}']
        if not any(x == [k, 0] for v in j.values() for x in v['inputs'].values()): del j[k]
elif o.加参考图: sys.exit('--加参考图 要和 --参考图 一起用')
if o.首帧:
    视频vae = 条入.get('vae') or 条入.get('video_vae')
    k1 = 新号(); j[k1] = {'class_type': 'LoadImage', 'inputs': {'image': 传(o.首帧)}}
    k2 = 新号(); j[k2] = {'class_type': 'MiniMaxH3AddGuide', 'inputs': {'positive': [条, 0], 'vae': 视频vae, 'latent': [条, 1], 'image': [k1, 0], 'frame_idx': 0}}
    for k, v in j.items():   # 原来接条件输出（正向）的地方，改接加了首帧引导的条件
        if k == k2: continue
        for n, x in v['inputs'].items():
            if x == [条, 0]: v['inputs'][n] = [k2, 0]
for k in 采: j[k]['inputs']['seed'] = o.种子
for k in 存: j[k]['inputs']['filename_prefix'] = f'{子目录}/{o.名字}'
坏 = [(k, n) for k, v in j.items() for n, x in v['inputs'].items() if isinstance(x, list) and len(x) == 2 and isinstance(x[0], str) and x[0] not in j]
assert not 坏, 坏
任务 = os.path.join(o.输出, f'{o.名字}.json'); json.dump(j, open(任务, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if o.只导出:
    sys.exit(f'只导出：{任务}（参考图和首帧要先放进 ComfyUI 的 input 目录，文件名和上面一致）')

pid = 提交(j)
print('已提交', o.名字, pid)
with open(os.path.join(o.输出, '提交记录.txt'), 'a', encoding='utf-8') as f:
    f.write(f'{time.strftime("%F %T")} {o.名字} {pid} 首帧={o.首帧} 参考图={o.参考图}+{o.加参考图} 种子={o.种子}{" 非打斗="+o.非打斗 if o.非打斗 else ""}\n')
if o.不等: sys.exit(0)

# ---------- 等出片、下载 ----------
本 = os.path.join(o.输出, f'{o.名字}.mp4')
while True:
    h = 历史(pid); st = h.get('status', {})
    if st.get('status_str') == 'error':
        e = [m for m in st.get('messages', []) if m[0] == 'execution_error']
        sys.exit('出错：' + (e[0][1].get('exception_message', '')[:500] if e else '未知'))
    if st.get('completed'):
        文件 = [x for v in h.get('outputs', {}).values() for k in ('images', 'videos', 'gifs') for x in v.get(k, []) if str(x.get('filename', '')).endswith('.mp4')]
        if 文件: break
    time.sleep(30)
x = 文件[-1]
if 模式 == 'ssh':
    远文件 = f"{远}/output/{x.get('subfolder', '')}/{x['filename']}".replace('//', '/')
    while subprocess.run(['scp', '-q', f'{主机}:{远文件}', 本]).returncode: time.sleep(20)
else:
    q = urllib.parse.urlencode({'filename': x['filename'], 'subfolder': x.get('subfolder', ''), 'type': x.get('type', 'output')})
    open(本, 'wb').write(http(f'/view?{q}'))
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 本, '-vf', 'fps=2,scale=400:-2,tile=5x4', '-frames:v', '1', os.path.join(o.输出, f'{o.名字}_每半秒.png')])
subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), '查字幕.py'), 本])
print('下载完成', 本)
