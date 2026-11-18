# 用法：python3 工具/自检.py            第一次用、换机器、出片报错时先跑一遍。
# 查：Python 版本、Pillow、ffmpeg/ffprobe；config.json 读到什么；ComfyUI 连不连得上；
#     两个工作流模板要用的节点装没装；模板里写的模型、LoRA 文件 ComfyUI 认不认得。缺什么直接列出来。
# 只写提示词、不出片的话，前两项过了就够了。
import json, os, shutil, subprocess, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import 库, 根, 配置

好, 坏 = '  ✓', '  ✗'
问题 = []
def 报(ok, 话, 修=None):
    print((好 if ok else 坏), 话)
    if not ok and 修: 问题.append(修)

print('一、写提示词要的（检查.py、建库.py）')
报(sys.version_info >= (3, 9), f'Python {sys.version.split()[0]}', 'Python 要 3.9 以上')
try:
    import PIL; 报(True, f'Pillow {PIL.__version__}（加字幕.py、去字幕.py 用）')
except ImportError:
    报(False, '没装 Pillow（只影响 加字幕.py、去字幕.py）', 'pip install -r requirements.txt')
for 名 in ('ffmpeg', 'ffprobe'):
    报(bool(shutil.which(名)), f'{名}（出片后的拼图、拼片、字幕用）', f'装 ffmpeg：macOS `brew install ffmpeg`，Ubuntu `sudo apt install ffmpeg`，Windows 从 ffmpeg.org 下载并加进 PATH')

print('\n二、出片要的（出片.py）')
C = 配置(); 模式 = C.get('mode', 'local'); 地址 = C.get('comfy_url', 'http://127.0.0.1:8188').rstrip('/')
有配置 = os.path.exists(os.path.join(根, 'config.json'))
print(f'  配置：{"config.json" if 有配置 else "没有 config.json，用 config.example.json 的默认值"}；mode={模式}，comfy_url={地址}' + (f'，ssh_host={C.get("ssh_host")}' if 模式 == 'ssh' else ''))

def 取(path):
    if 模式 == 'ssh':
        r = subprocess.run(['ssh', '-o', 'ConnectTimeout=20', C.get('ssh_host', ''), f'curl -s --max-time 60 {地址}{path}'], capture_output=True, text=True)
        if r.returncode or not r.stdout.strip(): raise OSError(r.stderr.strip() or '没有返回')
        return json.loads(r.stdout)
    return json.loads(urllib.request.urlopen(地址 + path, timeout=60).read())

try:
    st = 取('/system_stats'); 版 = st.get('system', {}).get('comfyui_version', '?')
    卡 = '；'.join(f"{d.get('name')} {d.get('vram_total', 0) / 2**30:.0f}GB" for d in st.get('devices', []))
    报(True, f'ComfyUI 连上了（版本 {版}；{卡}）')
    for d in st.get('devices', []):
        if d.get('vram_total', 0) < 40 * 2**30 and d.get('type') != 'cpu':
            print('  ! 显存不到 40GB：这套部件只在 48GB 卡上实测过，24GB 卡未验证（见 README“显卡”）')
except Exception as e:
    报(False, f'连不上 ComfyUI：{e}', f'先启动 ComfyUI，再把 config.json 的 comfy_url 改成它的地址（复制 config.example.json 改名为 config.json）')
    print('\n' + ('缺：\n' + '\n'.join(f'  - {x}' for x in 问题)))
    sys.exit(1)

信息 = 取('/object_info')
节点 = {'MiniMaxH3AddGuide'}  # 用 --首帧 时加的节点
文件 = []
模板 = [m for m in ('三参考图.json', '无参考图.json') if os.path.exists(os.path.join(库, '模板', m))]
if not 模板:
    报(False, '库/模板/ 里还没有工作流（三参考图.json / 无参考图.json）', '跑 python3 工具/建模板.py 生成两个工作流模板（想自己搭就照 docs/工作流怎么搭.md，用“导出（API）”存进 库/模板/）')
    print('  先核对插件；模型文件等模板有了再查')
    节点 |= {'MiniMaxH3ReferenceToVideo', 'MiniMaxH3AudioConditioningT8', 'MiniMaxH3AVDecodeT8', 'SelfLiftAvatarH3TST', 'SelfLiftAvatarH3Sampler',
           'H3SigmaRefiner', 'ResolutionSelector', 'LoraLoaderBypassModelOnly', 'LoraLoaderModelOnly', 'UNETLoader', 'CLIPLoader', 'VAELoader',
           'KSamplerSelect', 'BasicScheduler', 'ConditioningZeroOut', 'CreateVideo', 'SaveVideo', 'LoadImage'}
for 模 in 模板:
    j = json.load(open(os.path.join(库, '模板', 模), encoding='utf-8'))
    for k, v in j.items():
        if k.startswith('_'): continue
        节点.add(v['class_type'])
        for 字, 值 in v['inputs'].items():
            if isinstance(值, str) and 值.endswith('.safetensors'): 文件.append((v['class_type'], 字, 值))
插件 = {'SelfLiftAvatarH3TST': 'selflift-Avatar（https://github.com/slmonker/selflift-Avatar）', 'SelfLiftAvatarH3Sampler': 'selflift-Avatar（https://github.com/slmonker/selflift-Avatar）',
        'H3SigmaRefiner': 'ComfyUI-YCNodes-MiniMax-H3（https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3）',
        'MiniMaxH3AVDecodeT8': 'comfyui-minimax-h3-audio-T8（https://github.com/T8mars/comfyui-minimax-h3-audio-T8）',
        'MiniMaxH3AudioConditioningT8': 'comfyui-minimax-h3-audio-T8（https://github.com/T8mars/comfyui-minimax-h3-audio-T8）'}
缺节点 = sorted(n for n in 节点 if n not in 信息)
报(not 缺节点, f'节点 {len(节点) - len(缺节点)}/{len(节点)} 个都在' if not 缺节点 else f'缺节点：{", ".join(缺节点)}')
for n in 缺节点:
    问题.append(f'装插件 {插件[n]}' if n in 插件 else f'节点 {n} 是 ComfyUI 自带的：把 ComfyUI 更新到带 MiniMax H3 支持的版本（实测 0.34.0）')

def 选项(cls, 字):
    i = 信息.get(cls, {}).get('input', {}); x = (i.get('required', {}) | i.get('optional', {})).get(字)
    if not x: return None
    if isinstance(x[0], list): return x[0]
    if len(x) > 1 and isinstance(x[1], dict): return x[1].get('options')
    return None
for cls, 字, 名 in dict.fromkeys(文件):
    opts = 选项(cls, 字)
    if opts is None: continue  # 节点没装，上面已经报了
    ok = 名 in opts or any(o.replace('\\', '/').split('/')[-1] == 名 for o in opts)
    报(ok, f'{名}（{cls}.{字}）', f'下载 {名} 放进 ComfyUI 对应的 models 目录（见 README“模型清单”）；文件名要一字不差，或者改 库/模板/*.json 里的名字')

print('\n' + ('全部就绪，可以出片。' if not 问题 else '缺：\n' + '\n'.join(f'  - {x}' for x in dict.fromkeys(问题))))
sys.exit(1 if 问题 else 0)
