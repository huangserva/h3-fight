# 把出好的片子做成广告：画面 + 黑底白字品牌结尾 + 英文旁白（广告声后期）+ 原片环境声 + 对好点的配乐，最后响度调到 -14 LUFS。
# 用法：
#   python3 广告合成.py --画面 成片_2560x1440.mp4 --输出 广告.mp4 --品牌 BRAND --口号 "FIND YOUR LINE" \
#       --旁白 l1.wav@0.6 l2.wav@7.55 l3.wav@19.3 l4.wav@尾+1.45 --配乐 配乐_对点.wav
#   旁白时间是成片里的秒数；“尾+1.45”= 结尾黑场开始后 1.45 秒（口号浮现时）。配乐要先剪好、从 0 秒对齐画面（见 广告后期.md）。
# 结尾：画面最后 --叠 秒渐黑接黑场，品牌大字 0.4 秒起浮现、口号 1.4 秒起浮现，共 --结尾秒 秒。
# 旁白后期（默认开）：去头尾静音 → 降 2 个半音（时长不变）→ 低频加厚 → 压缩 → 一点空间感；配乐在旁白时自动压低。
import argparse, json, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

a = argparse.ArgumentParser()
a.add_argument('--画面', required=True); a.add_argument('--输出', required=True)
a.add_argument('--品牌', required=True); a.add_argument('--口号', default='')
a.add_argument('--旁白', nargs='*', default=[]); a.add_argument('--配乐')
a.add_argument('--配乐音量', type=float, default=-5); a.add_argument('--环境声', type=float, default=-12, help='原片声音压低多少 dB；写 -99 就不要')
a.add_argument('--结尾秒', type=float, default=4.5); a.add_argument('--叠', type=float, default=0.6)
a.add_argument('--字体', default='/System/Library/Fonts/HelveticaNeue.ttc'); a.add_argument('--字重', type=int, default=7, help='ttc 里的序号，HelveticaNeue 7 = Light')
a.add_argument('--降调', type=float, default=2, help='旁白降几个半音，0 = 不处理')
a.add_argument('--响度', type=float, default=-14)
o = a.parse_args()

探 = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate:format=duration', '-of', 'json', o.画面]))
W, H = 探['streams'][0]['width'], 探['streams'][0]['height']; fps = round(eval(探['streams'][0]['r_frame_rate']))
片长 = float(探['format']['duration']); 尾起 = 片长 - o.叠; 总长 = 尾起 + o.结尾秒
有声 = bool(json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'json', o.画面])).get('streams'))
临 = tempfile.mkdtemp(prefix='广告合成_')

# 1. 结尾字（透明图层），字距拉宽，居中
def 字层(文字, 字号, 字距, 颜色, 中心y, 名):
    f = ImageFont.truetype(o.字体, 字号, index=o.字重); im = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    宽 = [d.textlength(c, font=f) for c in 文字]; 总 = sum(宽) + 字距 * 字号 * (len(文字) - 1)
    升, 降 = f.getmetrics(); x = (W - 总) / 2; y = 中心y - (升 + 降) / 2
    for c, w in zip(文字, 宽): d.text((x, y), c, font=f, fill=颜色); x += w + 字距 * 字号
    p = os.path.join(临, 名); im.save(p); return p
k = H / 1440
大 = 字层(o.品牌, int(190 * k), 0.42, (255, 255, 255, 255), H / 2 - 40 * k, 'brand.png')
小 = 字层(o.口号 or ' ', int(40 * k), 0.62, (205, 205, 205, 255), H / 2 + 120 * k, 'slogan.png')

# 2. 拼画面 + 混音
入 = ['-i', o.画面, '-f', 'lavfi', '-i', f'color=black:s={W}x{H}:r={fps}:d={o.结尾秒}', '-loop', '1', '-t', str(o.结尾秒), '-i', 大, '-loop', '1', '-t', str(o.结尾秒), '-i', 小]
声 = []
for x in o.旁白:
    f, t = x.rsplit('@', 1); t = 尾起 + float(t[2:]) if t.startswith('尾+') else float(t)
    入 += ['-i', f]; 声.append(t)
if o.配乐: 入 += ['-i', o.配乐]
fc = [f"[2:v]format=rgba,fade=in:st=0.4:d=1.0:alpha=1[t1];[3:v]format=rgba,fade=in:st=1.4:d=0.8:alpha=1[t2]",
      f"[1:v][t1]overlay=format=auto[c1];[c1][t2]overlay=format=auto,format=yuv420p,setsar=1,fps={fps}[card]",
      f"[0:v]setsar=1,fps={fps},format=yuv420p[film];[film][card]xfade=transition=fadeblack:duration={o.叠}:offset={尾起}[v]"]
混 = []
if 有声 and o.环境声 > -90:
    fc.append(f"[0:a]volume={o.环境声}dB,afade=t=out:st={尾起}:d={o.叠},apad=whole_dur={总长}[amb]"); 混.append('[amb]')
r = 2 ** (-o.降调 / 12)
for i, t in enumerate(声):
    ms = int(t * 1000); 调 = f"asetrate=48000*{r:.4f},aresample=48000,atempo={1 / r:.4f}," if o.降调 else ''
    fc.append(f"[{4 + i}:a]aresample=48000,silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
              f"{调}equalizer=f=120:t=q:w=1:g=3,equalizer=f=3500:t=q:w=1:g=2,acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=4,"
              f"aecho=0.8:0.5:40:0.12,aformat=channel_layouts=stereo,adelay={ms}|{ms}[vo{i}]")
if 声:
    fc.append(f"{''.join(f'[vo{i}]' for i in range(len(声)))}amix=inputs={len(声)}:normalize=0:duration=longest,apad=whole_dur={总长},asplit=2[vo][key]"); 混.append('[vo]')
if o.配乐:
    fc.append(f"[{4 + len(声)}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{总长},volume={o.配乐音量}dB,afade=t=out:st={总长 - 2}:d=2[m0]")
    fc.append("[m0][key]sidechaincompress=threshold=0.03:ratio=4:attack=20:release=400[m]" if 声 else "[m0]anull[m]"); 混.append('[m]')
if not 混: fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{总长}[a]")
else: fc.append(f"{''.join(混)}amix=inputs={len(混)}:normalize=0:duration=longest,atrim=0:{总长},alimiter=limit=0.89[a]")
草 = os.path.join(临, '草.mp4')
subprocess.run(['ffmpeg', '-v', 'error', '-y', *入, '-filter_complex', ';'.join(fc), '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '16', '-preset', 'slow',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '256k', '-t', str(总长), '-movflags', '+faststart', 草], check=True)

# 3. 响度两遍法调到 -14 LUFS（网络平台广告常用），峰值 -1 dBTP，画面不重编码
量 = subprocess.run(['ffmpeg', '-hide_banner', '-i', 草, '-af', f'loudnorm=I={o.响度}:TP=-1:LRA=11:print_format=json', '-f', 'null', '-'], capture_output=True, text=True).stderr
d = json.loads(量[量.rindex('{'):量.rindex('}') + 1])
ln = (f"loudnorm=I={o.响度}:TP=-1:LRA=11:measured_I={d['input_i']}:measured_TP={d['input_tp']}:measured_LRA={d['input_lra']}:"
      f"measured_thresh={d['input_thresh']}:offset={d['target_offset']}:linear=true,aresample=48000")
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 草, '-map', '0:v', '-map', '0:a', '-c:v', 'copy', '-af', ln, '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', o.输出], check=True)
终 = subprocess.run(['ffmpeg', '-hide_banner', '-i', o.输出, '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
print(f'完成 {o.输出}：{W}x{H}，{总长:.2f} 秒；' + ' '.join(x.strip() for x in 终.splitlines() if x.strip().startswith(('I:', 'Peak:')))[-60:])
