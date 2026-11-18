# 后期脚本的测试：放大的尺寸算法、去字幕遇到没音轨的片子、广告合成找字体。
# 尺寸算法只用标准库；另外两项要 ffmpeg、Pillow、opencv，缺了就跳过。
# 用法：python3 -m unittest discover -s 测试 -v
import importlib.util, os, shutil, subprocess, sys, tempfile, unittest

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
工具 = os.path.join(根, '工具')
sys.path.insert(0, 工具)
from 放大_flashvsr import 几何

有ffmpeg = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))
有 = lambda 模块: importlib.util.find_spec(模块) is not None


def 跑(*参):
    return subprocess.run([sys.executable, *参], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})


def 做片(路径, 带声音, 尺寸='320x180'):
    声 = ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-shortest', '-c:a', 'aac'] if 带声音 else []
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc=s={尺寸}:r=24:d=1', *声, '-pix_fmt', 'yuv420p', 路径], check=True)


def 流(路径):
    return subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', 路径], text=True).split()


class 放大尺寸(unittest.TestCase):
    def test_实测过的尺寸和原来写死的数字一样(self):
        """1664×928 → 2560×1440 是唯一在 4090 上实测过的。原脚本写死：pad=1664:998:0:35，放大到 2560×1536，crop=2560:1428:0:54。"""
        g = 几何(1664, 928)
        self.assertEqual(g['补'], (1664, 998, 0, 35))
        self.assertEqual(g['放大'], (2560, 1536))
        self.assertEqual(g['裁'], (2560, 1428, 0, 54))
        self.assertEqual(g['目标'], (2560, 1440))
        self.assertLess(abs(g['拉伸']), 0.01)

    def test_正好16比9不拉伸(self):
        g = 几何(1280, 720)
        self.assertEqual((g['补'], g['放大'], g['裁']), ((1280, 768, 0, 24), (2560, 1536), (2560, 1440, 0, 48)))
        self.assertEqual(g['拉伸'], 0)

    def test_竖片默认放大到1440x2560(self):
        g = 几何(928, 1664)
        self.assertEqual(g['目标'], (1440, 2560)); self.assertLess(abs(g['拉伸']), 0.01)

    def test_各种尺寸都守规矩(self):
        for w, h, 目标 in ((1664, 928, ()), (1280, 720, ()), (928, 1664, ()), (1024, 768, (2048, 1536)), (1248, 704, ()), (832, 480, (1920, 1080))):
            with self.subTest(输入=(w, h), 目标=目标):
                g = 几何(w, h, *目标); (补宽, 补高, 左, 上), (放宽, 放高), (裁宽, 裁高, 裁左, 裁上) = g['补'], g['放大'], g['裁']
                self.assertEqual((放宽 % 128, 放高 % 128), (0, 0), 'FlashVSR 的输出宽高要能被 128 整除')
                self.assertEqual((补宽 % 2, 补高 % 2), (0, 0)); self.assertGreaterEqual(补宽, w); self.assertGreaterEqual(补高, h)
                self.assertTrue(左 >= 0 and 上 >= 0 and 左 + w <= 补宽 and 上 + h <= 补高, '原片要放得进补边后的画布')
                self.assertTrue(裁宽 > 0 and 裁高 > 0 and 裁左 + 裁宽 <= 放宽 and 裁上 + 裁高 <= 放高, '裁的范围不能出界')
                self.assertLess(abs(放宽 / 补宽 - 放高 / 补高), 0.01, '横竖放大倍数要一样')

    def test_宽高比差太多能看出来(self):
        self.assertGreater(abs(几何(1024, 768)['拉伸']), 0.02)   # 4:3 的片子硬放到 16:9


@unittest.skipUnless(有ffmpeg and 有('cv2') and 有('numpy'), '要 ffmpeg、opencv、numpy')
class 去字幕(unittest.TestCase):
    def test_有没有音轨都能跑(self):
        with tempfile.TemporaryDirectory() as 临:
            for 带声音, 期望 in ((False, ['video']), (True, ['video', 'audio'])):
                with self.subTest(带声音=带声音):
                    入, 出 = os.path.join(临, f'in{带声音}.mp4'), os.path.join(临, f'out{带声音}.mp4'); 做片(入, 带声音)
                    r = 跑(os.path.join(工具, '去字幕.py'), 入, 出, '2', '10', '5', '100', '220', '140', '170')
                    self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(sorted(流(出)), sorted(期望))


@unittest.skipUnless(有('PIL'), '要 Pillow')
class 广告合成(unittest.TestCase):
    脚本 = os.path.join(工具, '广告合成.py')

    def test_字体打不开_说清楚怎么办(self):
        r = 跑(self.脚本, '--画面', '没有.mp4', '--输出', 'x.mp4', '--品牌', 'BRAND', '--字体', os.path.join(tempfile.gettempdir(), '没有这个字体.ttf'))
        self.assertNotEqual(r.returncode, 0); self.assertIn('--字体', r.stderr); self.assertNotIn('Traceback', r.stderr)

    @unittest.skipUnless(有ffmpeg, '要 ffmpeg')
    def test_不写字体_能跑完或者说清缺字体(self):
        with tempfile.TemporaryDirectory() as 临:
            入, 出 = os.path.join(临, 'in.mp4'), os.path.join(临, 'out.mp4'); 做片(入, True, '640x360')
            r = 跑(self.脚本, '--画面', 入, '--输出', 出, '--品牌', 'BRAND', '--口号', 'FIND YOUR LINE', '--结尾秒', '2')
            if r.returncode:   # 这台机器上没有任何一个默认字体：要明说，不能是一串报错
                self.assertIn('--字体', r.stderr); self.assertNotIn('Traceback', r.stderr)
            else: self.assertEqual(sorted(流(出)), ['audio', 'video'])


if __name__ == '__main__':
    unittest.main()
