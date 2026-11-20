# 用法：python3 工具/量速度.py <片1.mp4> <片2.mp4> ...   （和参考片比快慢：先量，再决定是补角度还是后期剪）
# 比两条片的“快”：都按 24 帧/秒取帧、缩到 320×180 灰度、去掉顶部 12%（水印），
#   切镜：相邻两帧颜色直方图相关 < 0.6 记一次切（白闪也算）。同一拍换机位、颜色差不多的切认不出来，会少算（长版快剪 82 刀只量到 25），以中位镜长为准；
#   动作速度：Farneback 光流平均位移（像素/帧，按 320 宽算），切镜帧和全白帧不算；另算“快动作帧占比”（位移 > 4 像素/帧）。
import sys, cv2, numpy as np
def 量(f):
    cap = cv2.VideoCapture(f); fps = cap.get(cv2.CAP_PROP_FPS); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    帧 = []
    for i in range(n):
        ok, im = cap.read()
        if not ok: break
        帧.append(im)
    长 = len(帧) / fps; 取 = [帧[min(int(k / 24 * fps), len(帧) - 1)] for k in range(int(长 * 24))]
    灰, 直 = [], []
    for im in 取:
        im = cv2.resize(im, (320, 180))[22:]
        灰.append(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY))
        h = cv2.calcHist([cv2.cvtColor(im, cv2.COLOR_BGR2HSV)], [0, 1], None, [16, 8], [0, 180, 0, 256]); 直.append(cv2.normalize(h, h).flatten())
    切, 动 = [], []
    for k in range(1, len(灰)):
        if cv2.compareHist(直[k - 1], 直[k], cv2.HISTCMP_CORREL) < 0.6: 切.append(k / 24); 动.append(np.nan); continue
        if 灰[k].mean() > 225 or 灰[k - 1].mean() > 225: 动.append(np.nan); continue
        fl = cv2.calcOpticalFlowFarneback(灰[k - 1], 灰[k], None, 0.5, 3, 15, 3, 5, 1.2, 0)
        动.append(float(np.linalg.norm(fl, axis=2).mean()))
    # 连续几帧都判成切的只算一次
    合 = [t for i, t in enumerate(切) if i == 0 or t - 切[i - 1] > 0.15]
    return 长, 合, np.array(动)
结果 = {}
for f in sys.argv[1:]:
    长, 切, 动 = 量(f); 结果[f] = (长, 切, 动)
    镜长 = np.diff([0] + 切 + [长])
    print(f'== {f}  {长:.1f} 秒  切镜 {len(切)} 次（{len(切)/长*10:.1f} 次/10 秒）  平均镜长 {镜长.mean():.2f} 秒  中位 {np.median(镜长):.2f} 秒')
    print(f'   动作速度：平均 {np.nanmean(动):.2f} 像素/帧，中位 {np.nanmedian(动):.2f}，快动作帧（>4）占 {np.nanmean(动 > 4)*100:.0f}%')
print('\n每秒动作速度（像素/帧）：')
print('秒   ' + '  '.join(f'{f.split("/")[-1][:14]:>14}' for f in 结果))
for s in range(31):
    行 = []
    for f, (长, 切, 动) in 结果.items():
        seg = 动[s * 24:(s + 1) * 24]; c = sum(1 for t in 切 if s <= t < s + 1)
        行.append(f'{np.nanmean(seg) if len(seg) and not np.all(np.isnan(seg)) else float("nan"):10.2f} 切{c}' if len(seg) else ' ' * 14)
    print(f'{s:>2}   ' + '  '.join(f'{x:>14}' for x in 行))
