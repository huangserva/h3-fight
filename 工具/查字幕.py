# 用法：python3 ~/.claude/skills/h3-fight/工具/查字幕.py <视频.mp4>
# 粗查画面下方有没有烧进白字幕（打戏段写了台词时常见）。报的是疑似帧号，要截图确认（白衣服、白鞋会误报）。
# 确认是字幕后：python3 去字幕.py 输入 输出 起帧 止帧 样板帧 x0 x1 y0 y1 12
import subprocess, sys, numpy as np
p = sys.argv[1]
w, h = map(int, subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', p], capture_output=True, text=True).stdout.split(','))
y0, y1, x0, x1 = int(h * .88), int(h * .985), int(w * .34), int(w * .66)
pr = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', p, '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)
i, hit = 0, []
while True:
    b = pr.stdout.read(w * h)
    if len(b) < w * h: break
    f = np.frombuffer(b, np.uint8).reshape(h, w)[y0:y1, x0:x1]
    wp = f > 225
    if wp.sum() > 1500 and (wp.sum(1) > 0).sum() < 70: hit.append(i)
    i += 1
if not hit: print('查字幕：没发现')
else:
    段 = []; s = hit[0]; q = s
    for x in hit[1:]:
        if x > q + 3: 段.append((s, q)); s = x
        q = x
    段.append((s, q))
    print('查字幕：疑似帧段', 段, f'框 x{x0}-{x1} y{y0}-{y1}（截图确认）')
