# 找配乐里的“重拍”和“抽空”，用来把歌剪到画面的关键点上（起跳、最高点、落地、品牌浮现）。
# 用法：python3 配乐能量.py 歌.wav [--步长 0.25] [--从 0 --到 60]
# 输出每一格的低频（150 Hz 以下，鼓和贝斯）和高频（2 kHz 以上，镲和空气声）能量（dB），并标出：
#   ▲ 重拍：低频比前 1 秒平均高 6 dB 以上（适合对落地、品牌浮现）
#   ▽ 抽空：低频比前 1 秒平均低 10 dB 以上（适合对最高点的滞空）
# 滑雪广告配乐示例：原曲第 20 秒的重拍对落地（片中 12.6 秒），原曲 116 秒最后一记重音对渐黑（片中 22.6 秒）。
import argparse, subprocess, numpy as np

a = argparse.ArgumentParser(); a.add_argument('歌')
a.add_argument('--步长', type=float, default=0.25); a.add_argument('--从', type=float, default=0); a.add_argument('--到', type=float, default=1e9)
o = a.parse_args()
sr = 22050
def 读(滤):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', o.歌, '-af', 滤, '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)
低, 高 = 读('lowpass=f=150,lowpass=f=150'), 读('highpass=f=2000,highpass=f=2000')
n = int(sr * o.步长); 格 = min(len(低), len(高)) // n
def db(x): return 10 * np.log10(np.mean(x.reshape(-1, n)[:格] ** 2, axis=1) + 1e-10)
L, Hh = db(低[:格 * n]), db(高[:格 * n]); 窗 = max(1, int(1 / o.步长))
print(f'{"秒":>7} {"低频dB":>7} {"高频dB":>7}')
for i in range(格):
    t = i * o.步长
    if t < o.从 or t > o.到: continue
    前 = L[max(0, i - 窗):i].mean() if i else L[i]
    标 = '▲ 重拍' if L[i] - 前 > 6 else ('▽ 抽空' if 前 - L[i] > 10 else '')
    print(f'{t:7.2f} {L[i]:7.1f} {Hh[i]:7.1f}  {"█" * max(0, int((L[i] + 60) / 3))} {标}')
