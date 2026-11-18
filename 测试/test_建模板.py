# 建模板.py 的测试：生成的两个工作流模板结构对不对、出片.py 认不认、文件名怎么挑、和文档写的是不是同一套。
# 不需要显卡，也不需要 ComfyUI。用法：python3 -m unittest discover -s 测试 -v
import json, os, subprocess, sys, tempfile, unittest, warnings

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(根, '工具'))
from 共用 import 读
from 建模板 import 建, 挑文件, 文件位

def setUpModule(): warnings.simplefilter('ignore', ResourceWarning)

默认名, _ = 挑文件(None)


class 结构(unittest.TestCase):
    def 各一个(self, j):
        """出片.py 按作用找节点：条件节点（有 prompt 和 clip）只能有一个，采样、保存节点要有。"""
        找 = lambda f: [k for k, v in j.items() if f(v)]
        条 = 找(lambda v: 'prompt' in v['inputs'] and 'clip' in v['inputs'])
        self.assertEqual(len(条), 1); self.assertEqual(len(找(lambda v: 'seed' in v['inputs'])), 1); self.assertEqual(len(找(lambda v: 'filename_prefix' in v['inputs'])), 1)
        return j[条[0]]

    def test_连线都接得上(self):
        for 参考图 in (True, False):
            with self.subTest(参考图=参考图):
                j = 建(默认名, 参考图)
                for k, v in j.items():
                    for 字, 值 in v['inputs'].items():
                        if isinstance(值, list): self.assertIn(值[0], j, f'节点 {k} 的 {字} 接到不存在的节点 {值[0]}')
                用到 = {值[0] for v in j.values() for 值 in v['inputs'].values() if isinstance(值, list)}
                self.assertEqual([k for k, v in j.items() if k not in 用到 and v['class_type'] != 'SaveVideo'], [], '有节点没接到任何地方')

    def test_三参考图版(self):
        条 = self.各一个(建(默认名, True))
        self.assertEqual(条['class_type'], 'MiniMaxH3ReferenceToVideo'); self.assertEqual(条['inputs']['length'], 243)
        self.assertEqual(sorted(k for k in 条['inputs'] if k.startswith('ref_images.')), [f'ref_images.ref_image_{i}' for i in range(3)])

    def test_无参考图版(self):
        j = 建(默认名, False); 条 = self.各一个(j)
        self.assertEqual(条['class_type'], 'MiniMaxH3AudioConditioningT8'); self.assertEqual(条['inputs']['length'], 243)
        self.assertEqual(条['inputs']['audio_mode'], 'native'); self.assertFalse(any(v['class_type'] == 'LoadImage' for v in j.values()))

    def test_两版只差条件节点和参考图(self):
        甲, 乙 = 建(默认名, True), 建(默认名, False)
        同 = [k for k in 乙 if k != '11']
        self.assertEqual({k: 甲[k] for k in 同}, {k: 乙[k] for k in 同})


class 挑文件名(unittest.TestCase):
    信息 = {'LoraLoaderModelOnly': {'input': {'required': {'lora_name': [['bunny_Fight_Flow_V1.safetensors', 'sub\\bunny_H3_Combat_V2.safetensors', 'bunny_Weapon_Combat_V1.safetensors',
                                                                 'bunny_Motion_Repair_V1.safetensors', 'bunny_Motion_Repair_V2.safetensors'], {}]}}},
          'UNETLoader': {'input': {'required': {'unet_name': ['COMBO', {'options': ['other.safetensors']}]}}}}

    def test_按关键词认出改过名的文件(self):
        名, 话 = 挑文件(self.信息)
        self.assertEqual(名['打斗交互'], 'bunny_Fight_Flow_V1.safetensors')
        self.assertEqual(名['武打基础'], 'sub\\bunny_H3_Combat_V2.safetensors', '兵器版 Weapon_Combat 不是武打基础；子目录里的要原样写回')
        self.assertEqual(名['动作修复'], 'bunny_Motion_Repair_V1.safetensors', '出过好片的是 V1')

    def test_找不到就用默认名并说清楚(self):
        名, 话 = 挑文件(self.信息)
        self.assertEqual(名['主模型'], 默认名['主模型']); self.assertTrue(any('✗ 主模型' in x for x in 话))
        self.assertTrue(any('没有节点 CLIPLoader' in x for x in 话))

    def test_离线全用默认名(self):
        self.assertEqual(默认名, {x[0]: x[3] for x in 文件位})


class 命令(unittest.TestCase):
    def 跑(self, *参):
        return subprocess.run([sys.executable, os.path.join(根, '工具', '建模板.py'), '--离线', *参], capture_output=True, text=True)

    def test_写两个文件_已有的不动_覆盖才重写(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.跑('--输出', d); self.assertEqual(r.returncode, 0, r.stderr)
            for 文件, 参考图 in (('三参考图.json', True), ('无参考图.json', False)):
                self.assertEqual(json.load(open(os.path.join(d, 文件), encoding='utf-8')), 建(默认名, 参考图))
            p = os.path.join(d, '无参考图.json'); open(p, 'w', encoding='utf-8').write('{"我自己搭的": 1}')
            self.assertIn('没动', self.跑('--输出', d).stdout); self.assertEqual(读(p), '{"我自己搭的": 1}')
            self.跑('--输出', d, '--覆盖'); self.assertEqual(json.load(open(p, encoding='utf-8')), 建(默认名, False))


class 和文档一致(unittest.TestCase):
    """模板就是 docs/工作流怎么搭.md 那张表：节点、默认文件名、关键参数要在文档里找得到。"""

    def test_节点和文件名都在文档里(self):
        搭 = 读(os.path.join(根, 'docs', '工作流怎么搭.md')); 清单 = 读(os.path.join(根, 'README.md'))
        for 参考图 in (True, False):
            for v in 建(默认名, 参考图).values(): self.assertIn(v['class_type'], 搭)
        for _, _, _, 文件, _, _ in 文件位:
            with self.subTest(文件=文件):
                self.assertIn(文件, 搭); self.assertIn(文件, 清单)


if __name__ == '__main__':
    unittest.main()
