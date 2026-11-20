# 把 cb1–cb6 拼成约 60 秒的长版。
#   钉了首帧的段（cb3、cb4、cb5）去掉第 1 帧，和上一段直接接上；
#   换地点的硬切（cb1→cb2、cb5→cb6）放白闪：2 帧白 + 下一段前 3 帧从白里出来；
#   声音整段接，每个接缝 0.06 秒交叉淡化，最后响度 -16 LUFS。
# 用法：python3 拼长版.py [输出.mp4]
import os, subprocess, sys
d = os.path.dirname(os.path.abspath(__file__))
输出 = sys.argv[1] if len(sys.argv) > 1 else os.path.join(d, '长版成片.mp4')
段 = [('cb1', 0, 0), ('cb2', 0, 1), ('cb3', 1, 0), ('cb4', 1, 0), ('cb5', 1, 0), ('cb6', 0, 1)]   # 名、去首帧、前面白闪
w, h, fps = 1664, 928, 24
入, 滤, 视, 声 = [], [], [], []
for i, (名, 去, 闪) in enumerate(段):
    入 += ['-i', os.path.join(d, 名 + '.mp4')]
    起 = 1 / fps if 去 else 0
    if 闪:
        滤.append(f'color=white:s={w}x{h}:r={fps}:d={2/fps:.4f},format=yuv420p,setsar=1[w{i}]'); 视.append(f'[w{i}]')
        滤.append(f'anullsrc=r=48000:cl=stereo,atrim=0:{2/fps:.4f}[s{i}]'); 声.append(f'[s{i}]')
    淡 = ',fade=t=in:s=0:n=3:color=white' if 闪 else ''
    滤.append(f'[{i}:v]trim=start={起:.4f},setpts=PTS-STARTPTS,fps={fps},scale={w}:{h}{淡},format=yuv420p,setsar=1[v{i}]'); 视.append(f'[v{i}]')
    滤.append(f'[{i}:a]atrim=start={起:.4f},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,'
              f'afade=t=in:d=0.03,areverse,afade=t=in:d=0.06,areverse[a{i}]'); 声.append(f'[a{i}]')
滤.append(''.join(视) + f'concat=n={len(视)}:v=1:a=0[v]')
滤.append(''.join(声) + f'concat=n={len(声)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a]')
subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *入, '-filter_complex', ';'.join(滤), '-map', '[v]', '-map', '[a]',
                '-c:v', 'libx264', '-crf', '16', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '256k',
                '-movflags', '+faststart', 输出], check=True)
print('写好', 输出)
