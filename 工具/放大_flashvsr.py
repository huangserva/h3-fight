# v6 成片放大：FlashVSR+ Turbo（时间压缩 2，适合大动作），默认 1664×928 → 2560×1440，在 4090 上运行。
# 沿用 11-07 对比测试的设置：turbo、TC2、triton_block_sparse、
# 颜色校正开、decode_every 28、CRF 16。FlashVSR 要求输出的宽高都能被 128 整除，所以先给原片补黑边，
# 放大到能整除的尺寸，再裁掉黑边、微调到目标尺寸，最后把原音轨合回去。
# 补多少、裁多少按输入片的实际尺寸算（见 几何()）。1664×928 的片子：补到 1664×998 → 放大到 2560×1536 → 裁成 2560×1428 → 缩到 2560×1440。
# 用法（4090）：.venv/bin/python 放大_flashvsr.py 输入.mp4 输出.mp4 [目标宽 目标高]
#   目标不写：横片 2560×1440，竖片 1440×2560。输入和目标的宽高比差超过 2% 就停（画面会被拉变形），这时请自己写目标宽高。
#   只实测过 1664×928 → 2560×1440；别的尺寸是按同样的算法推出来的，第一次用先拿短片试。
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path


def 偶(x):
    return int(round(x / 2)) * 2


def 几何(w, h, W=None, H=None, 模=128):
    """输入 w×h、目标 W×H，算出四步的尺寸：补边（宽, 高, 左, 上）、放大（宽, 高）、裁（宽, 高, 左, 上）、目标（宽, 高），以及画面被拉伸了多少。"""
    if W is None: W, H = (2560, 1440) if w >= h else (1440, 2560)
    比 = W / w                                                  # 放大倍数按宽算
    放宽, 放高 = -(-W // 模) * 模, -(-round(h * 比) // 模) * 模     # FlashVSR 的输出：装得下放大后的画面，宽高都能被 128 整除
    补宽, 补高 = 偶(放宽 / 比), 偶(放高 / 比)                       # 放大前把原片补到这么大
    左, 上 = (补宽 - w) // 2, (补高 - h) // 2
    裁左, 裁上 = round(左 * 放宽 / 补宽), round(上 * 放高 / 补高)    # 黑边放大后有多宽
    裁宽, 裁高 = 放宽 - 2 * 裁左, 放高 - 2 * 裁上
    return dict(补=(补宽, 补高, 左, 上), 放大=(放宽, 放高), 裁=(裁宽, 裁高, 裁左, 裁上), 目标=(W, H), 拉伸=(H / 裁高) / (W / 裁宽) - 1)


def 主():
    if len(sys.argv) not in (3, 5): sys.exit('用法：python 放大_flashvsr.py 输入.mp4 输出.mp4 [目标宽 目标高]')
    REPO = Path(os.environ.get('FLASHVSR_REPO', 'FlashVSR_Plus')).resolve()   # FlashVSR_Plus 仓库目录，用环境变量 FLASHVSR_REPO 指定
    src, dst = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    流 = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', str(src)]))['streams'][0]
    g = 几何(流['width'], 流['height'], *map(int, sys.argv[3:5]))
    (补宽, 补高, 左, 上), (放宽, 放高), (裁宽, 裁高, 裁左, 裁上), (W, H) = g['补'], g['放大'], g['裁'], g['目标']
    print(f"{流['width']}×{流['height']} → 补到 {补宽}×{补高} → 放大到 {放宽}×{放高} → 裁 {裁宽}×{裁高} → {W}×{H}（拉伸 {g['拉伸']:+.1%}）", flush=True)
    if abs(g['拉伸']) > 0.02:
        sys.exit(f"输入 {流['width']}×{流['height']} 和目标 {W}×{H} 的宽高比差太多，画面会被拉变形 {g['拉伸']:+.1%}。在命令最后写上合适的 目标宽 目标高")

    sys.path[:0] = [str(REPO), str(REPO / 'operators/flashvsr_attn')]
    import torch
    from inference import InferenceRequest, build_inference_pipeline
    from inference.presets import stream_config_for_mode, model_paths_for_mode
    import inference.output as output

    work = dst.parent / (dst.stem + '_work'); work.mkdir(parents=True, exist_ok=True)
    padded, flash = work / 'padded.mp4', work / f'flash_{放宽}x{放高}.mp4'

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

    # 2. 补黑边（1664×928 → 1664×998，上下各 35）
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-vf', f'pad={补宽}:{补高}:{左}:{上}:black', '-c:v', 'libx264',
                    '-crf', '12', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-an', str(padded)], check=True)

    # 3. FlashVSR+ 放大（1664×998 → 2560×1536）
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
    pipe.infer(InferenceRequest(input_path=str(padded), output_path=str(flash), height=放高, width=放宽),
               progress=lambda x: print('进度', x, flush=True), video_preset='fast')
    print(f'放大耗时 {time.perf_counter() - t:.0f} 秒', flush=True)

    # 4. 裁掉黑边（35×1536/998 ≈ 54），缩到目标尺寸，合回原音轨
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(flash), '-i', str(src), '-map', '0:v', '-map', '1:a?',
                    '-vf', f'crop={裁宽}:{裁高}:{裁左}:{裁上},scale={W}:{H}:flags=lanczos,setsar=1', '-c:v', 'libx264', '-crf', '16',
                    '-preset', 'slow', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-shortest', '-movflags', '+faststart', str(dst)], check=True)
    print(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=width,height,nb_frames',
                                   '-of', 'compact', str(dst)]).decode(), flush=True)
    print('完成', dst, flush=True)


if __name__ == '__main__':
    主()
