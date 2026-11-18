# 给成片加中文字幕（不依赖 ffmpeg 的 subtitles/drawtext 滤镜：用 PIL 画字幕图，ffmpeg overlay 叠上去）。
# 字体：config.json 的 subtitle_font；没写就自动找常见中文字体（macOS / Windows / Linux）。
# 用法：python3 加字幕.py 输入.mp4 字幕表.txt 输出.mp4
# 字幕表每行：开始秒 结束秒 字幕文字（例：6.5 8.2 就这点本事吗？）；# 开头是注释。
import os, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import 配置

入, 表, 出 = sys.argv[1:4]
宽, 高 = map(int, subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                                  '-of', 'csv=p=0', 入], capture_output=True, text=True).stdout.strip().split(','))
候选 = [配置().get('subtitle_font') or '', '/System/Library/Fonts/Hiragino Sans GB.ttc', '/System/Library/Fonts/PingFang.ttc',
      'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
      '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc', '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc']
字体文件 = next((f for f in 候选 if f and os.path.exists(os.path.expanduser(f))), None)
if not 字体文件: sys.exit('找不到中文字体：在 config.json 里写 subtitle_font（字体文件路径）')
字体 = ImageFont.truetype(os.path.expanduser(字体文件), round(高 * 0.052)); 描边 = max(2, round(高 * 0.0045))   # 928 高时 4 像素
条 = []
for 行 in open(表, encoding='utf-8'):
    行 = 行.strip()
    if not 行 or 行.startswith('#'): continue
    a, b, 字 = 行.split(maxsplit=2); 条.append((float(a), float(b), 字))

临 = tempfile.mkdtemp(); 输入 = ['-i', 入]; 链 = []; 上 = '0:v'
for i, (a, b, 字) in enumerate(条):
    图 = Image.new('RGBA', (宽, 高), (0, 0, 0, 0)); 画 = ImageDraw.Draw(图)
    框 = 画.textbbox((0, 0), 字, font=字体, stroke_width=描边)
    x = (宽 - (框[2] - 框[0])) // 2; y = int(高 * 0.88) - (框[3] - 框[1])
    画.text((x, y), 字, font=字体, fill=(255, 255, 255, 255), stroke_width=描边, stroke_fill=(0, 0, 0, 255))
    p = os.path.join(临, f'{i}.png'); 图.save(p); 输入 += ['-i', p]
    链.append(f"[{上}][{i + 1}:v]overlay=0:0:enable='between(t,{a},{b})'[s{i}]"); 上 = f's{i}'
subprocess.run(['ffmpeg', '-v', 'error', '-y', *输入, '-filter_complex', ';'.join(链), '-map', f'[{上}]', '-map', '0:a?',
                '-c:v', 'libx264', '-crf', '16', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'copy', 出], check=True)
print('加好字幕：', 出, f'{len(条)} 条')
