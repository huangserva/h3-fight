# 用法：python3 工具/混剪.py <剪辑表.json>
# 快节奏混剪（0.4 秒一切的特效大场面，照一条 30 秒的特效参考片验证过）：正片段 + 补角度段按表剪成一条，声音不跟着画面剪。
#
# 剪辑表.json（路径相对剪辑表所在目录）：
# {
#   "源":  {"d1": "dz1.mp4", "b1": "补素材/bz1.mp4", ...},
#   "表":  [["d1", 0.00, 0.40, 1, 0], ["b1", 0.45, 1.05, 1, 0], ...],   每段：素材、起秒、止秒、加速倍数、前面加白闪(0/1)
#   "整体": 1.12,                    可选：除最后一段外整体再加速，用来对齐总长
#   "底音": ["d1", "d2", "d3"],      每一大段铺哪条素材的整条原声；大段从表里第一次用到它的那一镜开始
#   "重击": [["d1", 0.50], ...],     在这些镜（素材, 起秒，要和表里一致）叠上那一镜自己的原声
#   "输出": "快版/成片.mp4"
# }
# 画面：每段裁出来、按倍数加速，白闪 = 2 帧白 + 下一镜 3 帧从白里出来。
# 声音：底音整条不剪（按大段长度微调速度、音高不变），压低 8 dB、滤掉 4 kHz 以上，大段之间交叉淡化 0.15 秒；
#       重击叠原声带 0.35 秒尾音，淡入 0.03、淡出 0.15 秒；限幅后响度 -16 LUFS。
#       不要把每一镜的原声跟着剪：75 段硬切的声音每 0.4 秒断一次，量到 196 次突跳（整段接的只有 8 次）。
import json, os, subprocess, sys
表文件 = os.path.abspath(sys.argv[1]); 目录 = os.path.dirname(表文件); 配 = json.load(open(表文件, encoding='utf-8'))
源 = {k: os.path.join(目录, v) for k, v in 配['源'].items()}
整体 = 配.get('整体', 1)
表 = [(s, a, b, v if i == len(配['表']) - 1 else v * 整体, f) for i, (s, a, b, v, f) in enumerate(配['表'])]
输出 = os.path.join(目录, 配['输出']); 中间 = 输出[:-4] + '_无声.mp4'
for s, *_ in 表: assert s in 源, f'表里的 {s} 不在 源 里'
def 跑(*a): subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *a], check=True)
def 长(f): return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]))
w, h = map(int, subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', 源[表[0][0]]]).decode().strip().split(','))

# 时间线：每段在成片里的 (起点, 时长)，白闪算进去
线 = []; t = 0
for s, a, b, v, 闪 in 表:
    t += 2 / 24 if 闪 else 0; d = (b - a) / v; 线.append((t, d)); t += d
总 = t

# 1. 画面
名 = list(源); 滤 = []; 链 = []
for i, (s, a, b, v, 闪) in enumerate(表):
    if 闪:
        滤.append(f'color=white:s={w}x{h}:r=24:d={2/24:.4f},format=yuv420p,setsar=1[w{i}]'); 链.append(f'[w{i}]')
    淡 = ',fade=t=in:s=0:n=3:color=white' if 闪 else ''
    滤.append(f'[{名.index(s)}:v]trim={a}:{b},setpts=(PTS-STARTPTS)/{v},fps=24,scale={w}:{h}{淡},format=yuv420p,setsar=1[v{i}]'); 链.append(f'[v{i}]')
滤.append(''.join(链) + f'concat=n={len(链)}:v=1:a=0[v]')
跑(*sum((['-i', 源[k]] for k in 名), []), '-filter_complex', ';'.join(滤), '-map', '[v]', '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', 中间)

# 2. 声音
起 = []
for s in 配['底音']:
    i = next(i for i, x in enumerate(表) if x[0] == s); 起.append(max(线[i][0] - (2 / 24 if 表[i][4] else 0), 0))
止 = 起[1:] + [总]; 入 = []; 滤 = []; 混 = []
for j, s in enumerate(配['底音']):
    要 = 止[j] - 起[j] + 0.15; 速 = min(max(长(源[s]) / 要, 0.5), 2.0)
    入 += ['-i', 源[s]]
    滤.append(f'[{j}:a]atempo={速:.4f},atrim=0:{要:.3f},asetpts=PTS-STARTPTS,lowpass=f=4000,volume=-8dB,aformat=sample_rates=48000:channel_layouts=stereo,'
              f'afade=t=in:d=0.15,afade=t=out:st={要 - 0.15:.3f}:d=0.15,adelay={int(起[j] * 1000)}:all=1[底{j}]'); 混.append(f'[底{j}]')
号 = {(s, round(a, 3)): i for i, (s, a, *_) in enumerate(表)}
for k, (s, a) in enumerate(配.get('重击', [])):
    i = 号.get((s, round(a, 3)));
    if i is None: sys.exit(f'重击 {s} {a} 在表里找不到同样起秒的那一镜')
    t0, _ = 线[i]; b = 表[i][2]; 长度 = (b - a) + (0.35 if i < len(表) - 1 else 0)
    入 += ['-i', 源[s]]; n = len(配['底音']) + k
    滤.append(f'[{n}:a]atrim={a}:{a + 长度:.3f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,'
              f'afade=t=in:d=0.03,afade=t=out:st={max(长度 - 0.15, 0):.3f}:d=0.15,adelay={int(t0 * 1000)}:all=1[击{k}]'); 混.append(f'[击{k}]')
滤.append(''.join(混) + f'amix=inputs={len(混)}:normalize=0:duration=longest,atrim=0:{总:.3f},alimiter=limit=0.89,loudnorm=I=-16:TP=-1.5:LRA=11[a]')
v = len(入) // 2
跑(*入, '-i', 中间, '-filter_complex', ';'.join(滤), '-map', f'{v}:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', 输出)
os.remove(中间)
print(f'{len(表)} 段，白闪 {sum(x[4] for x in 表)} 处，底音 {len(配["底音"])} 段（从 {", ".join(f"{x:.2f}" for x in 起)} 秒起），重击 {len(配.get("重击", []))} 处，总长 {总:.2f} 秒 → {输出}')
print(f'下一步：python3 {os.path.dirname(os.path.abspath(__file__))}/量速度.py <参考片> {输出}')
