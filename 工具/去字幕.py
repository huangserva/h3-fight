# 用法：python3 去字幕.py 输入.mp4 输出.mp4 起帧 止帧 样板帧 x0 x1 y0 y1 [加粗像素=5]
# 字幕位置不动时用：从“样板帧”（字幕压在暗底上的一帧）框里取白色笔画当固定形状，加粗盖住黑描边，
# 只在 起帧–止帧 内用这个固定形状做 Telea 修补。比逐帧找白色更稳：不会把白衣服当字幕，也不留描边灰印。
# k3b 用：7 56 36 620 1080 820 915（字幕“因为他把剑传给了你”在第 7–56 帧）。
import cv2, numpy as np, subprocess, sys
src, dst = sys.argv[1:3]; a, b, ref, x0, x1, y0, y1 = map(int, sys.argv[3:10]); grow = int(sys.argv[10]) if len(sys.argv) > 10 else 5
cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS); w, h = int(cap.get(3)), int(cap.get(4))
frames = []
while True:
    ok, f = cap.read()
    if not ok: break
    frames.append(f)
g = cv2.cvtColor(frames[ref], cv2.COLOR_BGR2GRAY)
m = np.zeros((h, w), np.uint8); m[y0:y1, x0:x1] = (g[y0:y1, x0:x1] > 215) * 255
m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))
enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-',
                        '-i', src, '-map', '0:v', '-map', '1:a?', '-c:v', 'libx264',   # 1:a? = 原片有音轨就带上，没有也不报错 '-crf', '12', '-preset', 'slow', '-pix_fmt', 'yuv420p',
                        '-c:a', 'copy', dst], stdin=subprocess.PIPE)
for i, f in enumerate(frames):
    if a <= i <= b: f = cv2.inpaint(f, m, 7, cv2.INPAINT_TELEA)
    enc.stdin.write(f.tobytes())
enc.stdin.close(); enc.wait(); print('帧数', len(frames), '修补', a, '–', b, '→', dst)
