# 用法：python3 工具/建模板.py [--覆盖] [--离线] [--输出 目录]
# 生成出片用的两个工作流模板（ComfyUI 的 API 格式），省得自己在 ComfyUI 里一个节点一个节点地搭：
#   库/模板/三参考图.json   有参考图（人物、场景、对手），出片.py --参考图 … 用它
#   库/模板/无参考图.json   只靠提示词
# 节点、连线、参数就是 docs/工作流怎么搭.md 那张表（出过好片的那一套），这里只是把表写成 JSON。
# 模型和 LoRA 的文件名每个人下载的都不一样：连得上 ComfyUI（config.json）就去问它实际有哪些文件，按关键词挑；
# 连不上或加 --离线，就用 README“模型清单”里的文件名，之后跑 工具/自检.py 会告诉你哪个对不上。
# 已有的模板不动（那可能是你自己搭的），要重建加 --覆盖。
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 共用 import 库, 配置

# 每个要选文件的地方：(代号, 节点, 输入名, README 模型清单里的文件名, 认这个文件的关键词（全部都要出现在文件名里，小写）, 有几个像的时候不要哪个)
文件位 = [
    ('主模型',   'UNETLoader',                'unet_name',      'minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors',      ['h3', 'hybrid'], None),
    ('加速',     'LoraLoaderBypassModelOnly', 'lora_name',      'minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors',  ['h3', 'turbo'], None),
    ('打斗交互', 'LoraLoaderModelOnly',       'lora_name',      'H3_Fight_Flow_V1.safetensors',                                ['fight_flow'], None),
    ('武打基础', 'LoraLoaderModelOnly',       'lora_name',      'H3_Combat_V2.safetensors',                                    ['h3_combat'], None),
    ('动作修复', 'LoraLoaderModelOnly',       'lora_name',      'Motion_Repair.safetensors',                                   ['motion_repair'], 'v2'),
    ('文本编码', 'CLIPLoader',                'clip_name',      'qwen3vl_32b_minimax_h3_int8_convrot.safetensors',             ['qwen3vl', 'h3'], None),
    ('视频VAE',  'VAELoader',                 'vae_name',       'minimax_h3_video_vae_fp16.safetensors',                       ['h3', 'video_vae'], None),
    ('音频VAE',  'VAELoader',                 'vae_name',       'minimax_h3_audio_vae_fp32.safetensors',                       ['h3', 'audio_vae'], None),
    ('放大器',   'SelfLiftAvatarH3Sampler',   'upscaler_model', 'minimax_h3_latent_upscaler_3d_conv_v1_fp16.safetensors',      ['h3', 'latent_upscaler'], None),
]

def 选项(信息, 节点, 输入):
    """ComfyUI 的 /object_info 里，这个节点这个输入能选哪些文件。节点没装或不是下拉框，返回 None。"""
    i = 信息.get(节点, {}).get('input', {}); x = {**i.get('required', {}), **i.get('optional', {})}.get(输入)
    if not x: return None
    if isinstance(x[0], list): return x[0]
    if len(x) > 1 and isinstance(x[1], dict): return x[1].get('options')
    return None

def 挑文件(信息=None):
    """返回 ({代号: 文件名}, [说明])。信息 = /object_info 的结果；None = 离线，全用默认名。"""
    名, 话 = {}, []
    for 代号, 节点, 输入, 默认, 词, 不要 in 文件位:
        名[代号] = 默认
        可选 = 选项(信息, 节点, 输入) if 信息 else None
        if 可选 is None:
            if 信息 is not None: 话.append(f'  ! {代号}：ComfyUI 里没有节点 {节点}，先用默认名 {默认}（跑 工具/自检.py 看缺哪个插件）')
            continue
        基 = lambda o: o.replace('\\', '/').split('/')[-1]
        中 = [o for o in 可选 if 基(o) == 默认] or [o for o in 可选 if all(w in 基(o).lower() for w in 词)]
        if len(中) > 1 and 不要: 中 = [o for o in 中 if 不要 not in 基(o).lower()] or 中
        if len(中) == 1: 名[代号] = 中[0]; 话.append(f'  ✓ {代号}：{中[0]}')
        elif not 中: 话.append(f'  ✗ {代号}：ComfyUI 里没找到（文件名里要有 {"、".join(词)}）。先写默认名 {默认}，下载后放进 models 目录（见 README“模型清单”）')
        else: 名[代号] = 中[0]; 话.append(f'  ! {代号}：有 {len(中)} 个像的（{"、".join(中)}），先用第一个，不对就改模板里的名字')
    return 名, 话

def 建(名, 参考图=True):
    """照 docs/工作流怎么搭.md 的表拼一个 API 格式的工作流。参考图=False 是只靠提示词的版本。"""
    j = {
        '1': {'class_type': 'VAELoader', 'inputs': {'vae_name': 名['视频VAE']}},
        '2': {'class_type': 'VAELoader', 'inputs': {'vae_name': 名['音频VAE']}},
        '3': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 名['文本编码'], 'type': 'minimax', 'device': 'default'}},
        '4': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 名['主模型'], 'weight_dtype': 'default'}},
        '5': {'class_type': 'LoraLoaderBypassModelOnly', 'inputs': {'model': ['4', 0], 'lora_name': 名['加速'], 'strength_model': 0.7}},
        '6': {'class_type': 'SelfLiftAvatarH3TST', 'inputs': {'model': ['5', 0], 'tau': 0.2, 'log_diagnostics': False}},
        '7': {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['6', 0], 'lora_name': 名['打斗交互'], 'strength_model': 0.65}},
        '8': {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['7', 0], 'lora_name': 名['武打基础'], 'strength_model': 0.5}},
        '9': {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['8', 0], 'lora_name': 名['动作修复'], 'strength_model': 0.25}},
        '10': {'class_type': 'ResolutionSelector', 'inputs': {'aspect_ratio': '16:9 (Widescreen)', 'megapixels': 1.5, 'multiple': 32}},
        '12': {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['11', 0]}},
        '13': {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}},
        '14': {'class_type': 'BasicScheduler', 'inputs': {'model': ['9', 0], 'scheduler': 'simple', 'steps': 8, 'denoise': 1.0}},
        '15': {'class_type': 'H3SigmaRefiner', 'inputs': {'sigmas': ['14', 0], 'extra_steps': 1, 'start_at_sigma': 0.7, 'end_at_sigma': 0.0, 'spacing': 'cosine'}},
        '16': {'class_type': 'SelfLiftAvatarH3Sampler', 'inputs': {
            'low_res_model': ['9', 0], 'positive': ['11', 0], 'negative': ['12', 0], 'vae': ['1', 0], 'latent_image': ['11', 1], 'sampler': ['13', 0], 'sigmas': ['15', 0],
            'seed': 1, 'cfg': 1.0, 'transition_step': 6, 'lowres_scale': 0.5, 'rho': 0.0, 'w_min': 0.5, 'w_max': 1.0, 'upscaler_model': 名['放大器'],
            'highres_tiling': False, 'tiling_mode': 'auto', 'tiling_tiles': 2, 'tiling_axis': 'auto'}},
        '17': {'class_type': 'MiniMaxH3AVDecodeT8', 'inputs': {'av_latent': ['16', 0], 'video_vae': ['1', 0], 'audio_vae': ['2', 0]}},
        '18': {'class_type': 'CreateVideo', 'inputs': {'images': ['17', 0], 'audio': ['17', 1], 'fps': 24.0}},
        '19': {'class_type': 'SaveVideo', 'inputs': {'video': ['18', 0], 'format': 'mp4', 'codec': 'h264', 'filename_prefix': 'h3_fight/test'}},
    }
    if 参考图:
        # 三张占位图：出片.py 会换成 --参考图 给的图，并按张数增减（最多 9 张）
        for i, 图 in enumerate(('人物.png', '场景.png', '对手.png')):
            j[str(20 + i)] = {'class_type': 'LoadImage', 'inputs': {'image': 图}}
        j['11'] = {'class_type': 'MiniMaxH3ReferenceToVideo', 'inputs': {
            'clip': ['3', 0], 'vae': ['1', 0], 'audio_vae': ['2', 0], 'prompt': '', 'width': ['10', 0], 'height': ['10', 1], 'length': 243, 'ref_image_size': 'match',
            'ref_images.ref_image_0': ['20', 0], 'ref_images.ref_image_1': ['21', 0], 'ref_images.ref_image_2': ['22', 0]}}
    else:
        j['11'] = {'class_type': 'MiniMaxH3AudioConditioningT8', 'inputs': {
            'clip': ['3', 0], 'video_vae': ['1', 0], 'audio_vae': ['2', 0], 'prompt': '', 'width': ['10', 0], 'height': ['10', 1], 'length': 243,
            'task_type': 'auto', 'audio_mode': 'native', 'audio_denoise_strength': 1.0, 'add_source_as_reference': False, 'prompt_primary_audio_ordinal': 1,
            'strict_prompt_tags': True, 'ref_image_size': 'match', 'reference_video_policy': 'official_2_to_15s'}}
    return dict(sorted(j.items(), key=lambda kv: int(kv[0])))

if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--覆盖', action='store_true'); a.add_argument('--离线', action='store_true'); a.add_argument('--输出', default=os.path.join(库, '模板'))
    o = a.parse_args()
    信息 = None
    if not o.离线:
        from 连接 import Comfy, 连不上, 出错
        try:
            连 = Comfy(配置()); 信息 = {}
            for 节点 in dict.fromkeys(x[1] for x in 文件位):
                try: 信息.update(json.loads(连.一次(f'/object_info/{节点}', timeout=60)))
                except 出错: pass   # 这个节点没装：挑文件() 里会说
            print(f'问了 ComfyUI（{连.地址}）实际有哪些模型文件：')
        except 连不上 as e:
            print(f'连不上 ComfyUI（{e}），用 README“模型清单”里的默认文件名。以后连上了可以加 --覆盖 重建。')
    名, 话 = 挑文件(信息)
    print('\n'.join(话))
    os.makedirs(o.输出, exist_ok=True); 写了 = 0
    for 文件, 参考图 in (('三参考图.json', True), ('无参考图.json', False)):
        路 = os.path.join(o.输出, 文件)
        if os.path.exists(路) and not o.覆盖:
            print(f'已有 {文件}，没动（要重建加 --覆盖）'); continue
        json.dump(建(名, 参考图), open(路, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); 写了 += 1
        print(f'写好 {路}')
    if 写了: print('下一步：python3 工具/自检.py   核对节点和模型文件；没问题就能用 工具/出片.py 出片。')
