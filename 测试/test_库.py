# 库的回归测试：改检查器、改库之前和之后都跑一遍，保证“好片全过、差片全不过”没被改坏，生成文件和来源对得上。
# 用法：python3 -m unittest discover -s 测试 -v      （只用标准库，不用显卡）
import json, os, re, shutil, subprocess, sys, tempfile, unittest, warnings

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(根, '工具'))
from 共用 import 库, 读, 镜头, 题材of, 词句表, 时间表
from 检查 import 查

说明 = {k: v for k, v in json.load(open(os.path.join(库, '来源说明.json'), encoding='utf-8')).items() if not k.startswith('_')}
来源 = lambda 名: os.path.join(库, '来源', 名 + '.txt')


def setUpModule(): warnings.simplefilter('ignore', ResourceWarning)   # 工具里很多 json.load(open(...))，不在这里刷屏


class 校准(unittest.TestCase):
    """README 的说法：库里的好片全部通过检查，已知写得差的全部不通过。"""

    def test_A级全部通过(self):
        甲 = [名 for 名, v in 说明.items() if v['等级'] == 'A']
        self.assertGreaterEqual(len(甲), 30)
        for 名 in 甲:
            with self.subTest(来源=名):
                # 照 15 秒排的旧 6 镜来源是“旧结构”：新写这样排是错误，核对旧来源时用 旧时间表 降成提醒
                旧 = 时间表(读(来源(名)))[2] == '15 秒'
                错, _, _ = 查(来源(名), 排除=名, 题材=题材of(说明[名]), 旧时间表=旧)
                self.assertEqual(错, [])

    def test_旧时间表的来源不加参数只错在时间表(self):
        旧 = [名 for 名, v in 说明.items() if v['等级'] == 'A' and 时间表(读(来源(名)))[2] == '15 秒']
        self.assertGreaterEqual(len(旧), 20)
        for 名 in 旧:
            with self.subTest(来源=名):
                错, _, _ = 查(来源(名), 排除=名, 题材=题材of(说明[名]))
                self.assertEqual(len(错), 1); self.assertIn('10 秒片写成 15 秒的镜头时间', 错[0])

    def test_B级全部不通过(self):
        乙 = [名 for 名, v in 说明.items() if v['等级'] == 'B']
        self.assertGreaterEqual(len(乙), 4)
        for 名 in 乙:
            with self.subTest(来源=名):
                错, _, _ = 查(来源(名), 排除=名, 题材=题材of(说明[名]))
                self.assertNotEqual(错, [])


class 同步(unittest.TestCase):
    """同一批提示词存在 来源/、镜头块.json、库对照.md 三处，后两处是生成的，必须和来源一致。"""

    def test_每条来源都有文件和标注(self):
        标注 = json.load(open(os.path.join(库, '镜头标注.json'), encoding='utf-8'))
        for 名 in 说明:
            with self.subTest(来源=名):
                self.assertTrue(os.path.exists(来源(名)), '来源说明里有，来源/ 里没有这个文件')
                self.assertEqual(len(镜头(读(来源(名)))), len(标注.get(名, [])), '镜头数和镜头标注对不上')
        多 = {f[:-4] for f in os.listdir(os.path.join(库, '来源')) if f.endswith('.txt')} - set(说明)
        self.assertEqual(多, set(), '来源/ 里有文件没写进来源说明')

    def test_生成文件和来源同步(self):
        """在临时目录里重跑 建库.py，结果要和仓库里的一字不差。不一致 = 改了来源没重新建库（或手改了生成文件）。"""
        with tempfile.TemporaryDirectory() as 临:
            for 名 in ('工具', '库'): shutil.copytree(os.path.join(根, 名), os.path.join(临, 名))
            shutil.copy(os.path.join(根, 'config.example.json'), 临)   # 不带 config.json：对照页写到默认位置
            r = subprocess.run([sys.executable, os.path.join(临, '工具', '建库.py')], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 0, r.stderr)
            for 文件 in ('库/镜头块.json', '库/词句出处.json', '库对照.md'):
                with self.subTest(文件=文件):
                    self.assertTrue(读(os.path.join(临, 文件)) == 读(os.path.join(根, 文件)), f'{文件} 过期了：跑一遍 python3 工具/建库.py')

    def test_说明文档里的数字(self):
        块 = len(json.load(open(os.path.join(库, '镜头块.json'), encoding='utf-8')))
        self.assertEqual(块, sum(len(镜头(读(来源(名)))) for 名 in 说明))
        for 文件, 式 in (('README.md', r'镜头块库（(\d+) 块）'), ('README_en.md', r'Shot-block library \((\d+) blocks\)')):
            with self.subTest(文件=文件):
                m = re.search(式, 读(os.path.join(根, 文件)))
                self.assertTrue(m, '找不到镜头块数量')
                self.assertEqual(int(m.group(1)), 块, '说明文档里的镜头块数量和库对不上')

    def test_招牌写法是16个(self):
        self.assertEqual(sum(bool(e['招牌']) for e in 词句表()), 16)   # 检查.py 的提示语里写死了“/16”


class 时间表标注(unittest.TestCase):
    """哪些来源是照 15 秒片排的旧 6 镜写法，是从来源文字里算出来的，不靠手写。"""

    def test_和踩坑表认的是同一件事(self):
        坑 = next(k for k in json.load(open(os.path.join(库, '踩坑.json'), encoding='utf-8'))['坑'] if k['名'] == '10 秒片写成 15 秒的镜头时间')
        for 名 in 说明:
            with self.subTest(来源=名):
                文 = 读(来源(名)); 数, 点, 表 = 时间表(文)
                self.assertEqual(数, len(镜头(文))); self.assertEqual(点[0], 0.0)
                self.assertTrue(all(a < b for a, b in zip(点, 点[1:])), '镜头时间点要一个比一个晚')
                self.assertEqual(表 == '15 秒', bool(re.search(坑['检测'], 文.lower())))

    def test_每个镜头块都标了(self):
        块 = json.load(open(os.path.join(库, '镜头块.json'), encoding='utf-8'))
        for b in 块:
            self.assertIn(b['时间表'], ('10 秒', '15 秒'), b['编号']); self.assertIsInstance(b['起点秒'], float, b['编号'])
        self.assertTrue(all(b['时间表'] == '10 秒' for b in 块 if b['题材'] == '运动'))

    def test_说明文档点名的入门样例要么是10秒时间表_要么写明了是旧写法(self):
        """README 推荐照着改的那条来源如果是旧的 15 秒时间表，旁边必须说明，免得新手照抄时间点。"""
        for 文件, 旧写法 in (('README.md', '旧'), ('README_en.md', 'older')):
            with self.subTest(文件=文件):
                段 = [l for l in 读(os.path.join(根, 文件)).splitlines() if '库/来源/' in l and '.txt' in l]
                self.assertTrue(段, '找不到推荐的入门样例')
                for 行 in 段:
                    for 名 in re.findall(r'库/来源/([^`/]+)\.txt', 行):
                        if 时间表(读(来源(名)))[2] == '15 秒': self.assertIn(旧写法, 行, f'{名} 是 15 秒旧时间表，这一行要说明')


class 五镜时间表(unittest.TestCase):
    """10 秒 5 镜（0 / 2 / 4.5 / 6.5 / 7.5）的几条提醒：库里的 5 镜来源一条都不该中，改坏了要中。"""
    提醒词 = ('排在 10 秒里', '只剩', '交手镜头太短', '特写，却写了动作')

    def 改了再查(self, 改):
        文 = 改(读(来源('k4f')))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'x.txt'); open(p, 'w', encoding='utf-8').write(文)
            return 查(p)

    def test_库里的五镜来源不中(self):
        新 = [名 for 名, v in 说明.items() if v['等级'] == 'A' and 题材of(v) == '打戏' and 时间表(读(来源(名)))[2] == '10 秒']
        self.assertGreaterEqual(len(新), 30)
        for 名 in 新:
            with self.subTest(来源=名):
                _, 醒, _ = 查(来源(名), 排除=名)
                self.assertEqual([x for x in 醒 if any(w in x for w in self.提醒词)], [])

    def test_特写里塞动作会提醒(self):
        _, 醒, _ = self.改了再查(lambda t: t.replace('Her breathing is calm;', 'He roars and swipes at her; she pivots, kicks off his arm and dives back down. Her breathing is calm;'))
        self.assertTrue(any('特写，却写了动作' in x for x in 醒), 醒)

    def test_收尾太短会提醒(self):
        _, 醒, _ = self.改了再查(lambda t: t.replace('At 00:07.500', 'At 00:08.500'))
        self.assertTrue(any('只剩 1.5 秒' in x for x in 醒), 醒)

    def test_交手镜头太短会提醒(self):
        _, 醒, _ = self.改了再查(lambda t: t.replace('At 00:04.500', 'At 00:03.000'))
        self.assertTrue(any('交手镜头太短：第 2 镜 1 秒' in x for x in 醒), 醒)

    def test_时间点倒着排是错误(self):
        错, _, _ = self.改了再查(lambda t: t.replace('At 00:04.500', 'At 00:07.000'))
        self.assertTrue(any('一个比一个晚' in x for x in 错), 错)

    def test_新提示词按15秒排是错误(self):
        错, _, _ = 查(来源('k4d'), 排除='k4d')
        self.assertTrue(any('15 秒' in x for x in 错), 错)


class 查重复认兵器(unittest.TestCase):
    """查重复.py：兵器戏不查近身手部细分、不把蹬地和单膝跪地算成拳脚；徒手戏照旧查。"""

    def 跑(self, *名):
        return subprocess.run([sys.executable, os.path.join(根, '工具', '查重复.py')] + [来源(n) for n in 名], capture_output=True, text=True).stdout

    def test_兵器戏不误报(self):
        出 = self.跑('k3f', 'k4f')
        self.assertIn('兵器戏', 出); self.assertIn('没发现单一问题', 出)
        self.assertIn('锁刀角力', 出); self.assertNotIn('近身手部对打', 出)

    def test_徒手戏照旧查(self):
        出 = self.跑('日漫A1', '日漫A2', '日漫A3', '日漫A5')
        self.assertNotIn('兵器戏', 出); self.assertIn('近身细分', 出); self.assertIn('“拳脚连打”占', 出)
        self.assertNotIn('锁刀角力×', 出); self.assertNotIn('刀剑硬接×', 出)

    def test_蹬地和跪地不算拳脚(self):
        出 = self.跑('浮桥追逐1f', '浮桥追逐2f')
        self.assertNotIn('“拳脚连打”占', 出); self.assertNotIn('头槌肘击', 出.split('整片')[0]); self.assertNotIn('“射箭”占', 出)


if __name__ == '__main__':
    unittest.main()
