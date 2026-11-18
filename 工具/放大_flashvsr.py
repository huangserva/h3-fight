# v6 成片放大：FlashVSR+ Turbo（时间压缩 2，适合大动作），1664×928 → 2560×1440，在 4090 上运行。
# 沿用 11-07 对比测试的设置：turbo、TC2、triton_block_sparse、
# 颜色校正开、decode_every 28、CRF 16。FlashVSR 要求宽高都能被 128 整除，所以先上下补黑边到 1664×998，
# 放大到 2560×1536，再裁掉黑边、微调到 2560×1440，最后把原音轨合回去。
# 用法（4090）：.venv/bin/python 放大_flashvsr.py 输入.mp4 输出.mp4
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

REPO = Path(os.environ.get('FLASHVSR_REPO', 'FlashVSR_Plus')).resolve()   # FlashVSR_Plus 仓库目录，用环境变量 FLASHVSR_REPO 指定
sys.path[:0] = [str(REPO), str(REPO / 'operators/flashvsr_attn')]
import torch
from inference import InferenceRequest, build_inference_pipeline
from inference.presets import stream_config_for_mode, model_paths_for_mode
import inference.output as output

src, dst = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
work = dst.parent / (dst.stem + '_work'); work.mkdir(parents=True, exist_ok=True)
padded, flash = work / 'padded.mp4', work / 'flash_2560x1536.mp4'

# 1. 等 ComfyUI 队列（环境变量 COMFY_PORTS，默认 8188，逗号分隔）都空，再让它们释放显存（不打断任何任务）
def idle():
    for port in [int(x) for x in os.environ.get('COMFY_PORTS', '8188').split(',')]:
        try:
            q = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/queue', timeout=15))
        except Exception:
            continue
        if q['queue_running'] or q['queue_pending']:
            return False
    return True
while not idle():
    print('等 ComfyUI 队列空', flush=True); time.sleep(20)
for port in [int(x) for x in os.environ.get('COMFY_PORTS', '8188').split(',')]:
    try:
        urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/free', data=json.dumps(
            dict(unload_models=True, free_memory=True)).encode(), headers={'Content-Type': 'application/json'}), timeout=15).read()
    except Exception:
        pass
time.sleep(5)

# 2. 补黑边：1664×928 → 1664×998（上下各 35）
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-vf', 'pad=1664:998:0:35:black', '-c:v', 'libx264',
                '-crf', '12', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-an', str(padded)], check=True)

# 3. FlashVSR+ 放大到 2560×1536
os.chdir(REPO)
orig = output.imageio.get_writer
def writer(*a, **k):
    if k.get('codec') == 'libx264':
        k['quality'] = None; k['output_params'] = k.get('output_params', []) + ['-crf', '16']
    return orig(*a, **k)
output.imageio.get_writer = writer
cfg = stream_config_for_mode('turbo', device='cuda:0', seed=2026110701, decode_every=28, temporal_compression=2,
                             attn_kernel='triton_block_sparse', color_correction=True)
t = time.perf_counter()
pipe = build_inference_pipeline(cfg, model_paths_for_mode(REPO, 'turbo'))
print(f'模型加载 {time.perf_counter() - t:.0f} 秒', flush=True)
t = time.perf_counter()
pipe.infer(InferenceRequest(input_path=str(padded), output_path=str(flash), height=1536, width=2560),
           progress=lambda x: print('进度', x, flush=True), video_preset='fast')
print(f'放大耗时 {time.perf_counter() - t:.0f} 秒', flush=True)

# 4. 裁掉黑边（35×1536/998 ≈ 54），缩到 2560×1440，合回原音轨
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(flash), '-i', str(src), '-map', '0:v', '-map', '1:a?',
                '-vf', 'crop=2560:1428:0:54,scale=2560:1440:flags=lanczos,setsar=1', '-c:v', 'libx264', '-crf', '16',
                '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-shortest', '-movflags', '+faststart', str(dst)], check=True)
print(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=width,height,nb_frames',
                               '-of', 'compact', str(dst)]).decode(), flush=True)
print('完成', dst, flush=True)
