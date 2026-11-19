# 用法：python3 工具/拆0.25秒.py <片.mp4> <标签> <输出.png>
# 每 0.25 秒取一帧，标上“标签-秒 光流速度”（> 6 标黄 = 动作猛），拼成 8×5。混剪挑镜头用：每拍挑标黄、构图清楚的那几格。
import sys, cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
f, 标, 出 = sys.argv[1:4]
字 = None
for 路 in ('/System/Library/Fonts/STHeiti Medium.ttc', '/System/Library/Fonts/PingFang.ttc', 'C:/Windows/Fonts/msyh.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'):
    try: 字 = ImageFont.truetype(路, 22); break
    except OSError: pass
字 = 字 or ImageFont.load_default()
cap = cv2.VideoCapture(f); 帧 = []
while True:
    ok, im = cap.read()
    if not ok: break
    帧.append(im)
灰 = [cv2.cvtColor(cv2.resize(x, (320, 180)), cv2.COLOR_BGR2GRAY) for x in 帧]
动 = [0] + [float(np.linalg.norm(cv2.calcOpticalFlowFarneback(灰[k-1], 灰[k], None, .5, 3, 15, 3, 5, 1.2, 0), axis=2).mean()) for k in range(1, len(灰))]
图 = Image.new('RGB', (384 * 8, 214 * 5))
for j in range(40):
    k = min(j * 6, len(帧) - 1); im = Image.fromarray(cv2.cvtColor(cv2.resize(帧[k], (384, 214)), cv2.COLOR_BGR2RGB)); d = ImageDraw.Draw(im)
    v = np.mean(动[k:k+6]); d.rectangle((0, 0, 170, 28), fill=(0, 0, 0)); d.text((4, 2), f'{标}-{j*0.25:.2f}s {v:.1f}', font=字, fill=(255, 255, 0) if v > 6 else (255, 255, 255))
    图.paste(im, ((j % 8) * 384, (j // 8) * 214))
图.save(出)
