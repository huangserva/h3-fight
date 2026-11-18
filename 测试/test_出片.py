# 出片连接的测试：本机起一个假的 ComfyUI，把“被拒绝 / 回音丢了 / 连不上 / 任务丢了 / 跑完没片 / 等太久”都演一遍。
# 不需要显卡，也不需要真的 ComfyUI。ssh 模式用假的 ssh、scp 命令在本机演（Windows 或没有 curl 时跳过）。
# 用法：python3 -m unittest discover -s 测试 -v
import collections, json, os, shutil, socket, stat, subprocess, sys, tempfile, threading, unittest, uuid, warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import urlparse, parse_qs

根 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(根, '工具'))
from 连接 import Comfy, 连不上, 出错, 令牌键

def setUpModule(): warnings.simplefilter('ignore', ResourceWarning)   # 工具里很多 json.load(open(...))，不在这里刷屏


校验失败 = {'error': {'type': 'prompt_outputs_failed_validation', 'message': 'Prompt outputs failed validation', 'details': '', 'extra_info': {}},
        'node_errors': {'3': {'class_type': 'LoraLoaderModelOnly', 'dependent_outputs': ['9'],
                              'errors': [{'type': 'value_not_in_list', 'message': 'Value not in list', 'details': "lora_name: 'H3_Fight_Flow_V1.safetensors' not in []"}]}}}
工作流 = {'1': {'class_type': 'MiniMaxH3AudioConditioningT8', 'inputs': {'prompt': '', 'clip': ['2', 0]}},
       '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': 'x.safetensors'}},
       '3': {'class_type': 'SelfLiftAvatarH3Sampler', 'inputs': {'seed': 0, 'positive': ['1', 0]}},
       '9': {'class_type': 'SaveVideo', 'inputs': {'filename_prefix': 'video/x', 'video': ['3', 0]}}}


class 假Comfy:
    """只实现出片用到的几个接口。行为用下面几个开关控制。"""

    def __init__(self):
        self.提交 = []          # 真正收下的任务（/prompt 的正文）
        self.队列 = []          # 和 ComfyUI 一样：[序号, 任务号, 工作流, extra_data, 要执行的输出]
        self.历史 = {}
        self.上传 = []
        self.次数 = collections.Counter()
        self.拒绝 = None        # (状态码, dict)：/prompt 直接回这个
        self.吞回音 = 0         # 接下来几次 /prompt：收下任务，但不回应就断开
        self.丢请求 = 0         # 接下来几次 /prompt：不收任务，直接断开
        self.立即完成 = False    # 收下任务马上算跑完
        self.片 = b'\x00\x00\x00\x18ftypmp42 fake'
        假 = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def 回(self, 码, 体, 型='application/json'):
                体 = 体 if isinstance(体, bytes) else json.dumps(体).encode()
                self.send_response(码); self.send_header('Content-Type', 型); self.send_header('Content-Length', str(len(体))); self.end_headers(); self.wfile.write(体)

            def do_GET(self):
                u = urlparse(self.path); 假.次数[u.path] += 1
                if u.path == '/queue': return self.回(200, {'queue_running': [], 'queue_pending': 假.队列})
                if u.path == '/history': return self.回(200, 假.历史)
                if u.path.startswith('/history/'):
                    pid = u.path.split('/')[-1]; return self.回(200, {pid: 假.历史[pid]} if pid in 假.历史 else {})
                if u.path == '/view': return self.回(200, 假.片, 'video/mp4')
                self.回(404, {'error': 'not found'})

            def do_POST(self):
                体 = self.rfile.read(int(self.headers.get('Content-Length', 0))); 假.次数[self.path] += 1
                if self.path == '/upload/image':
                    假.上传.append(体); return self.回(200, {'name': 'hero.png', 'subfolder': '', 'type': 'input'})
                if self.path != '/prompt': return self.回(404, {'error': 'not found'})
                if 假.拒绝: return self.回(*假.拒绝)
                if 假.丢请求 > 0: 假.丢请求 -= 1; return     # 什么都不回，连接直接断
                d = json.loads(体); pid = str(uuid.uuid4())
                假.提交.append(d); 假.队列.append([len(假.提交), pid, d['prompt'], d.get('extra_data', {}), ['9']])
                if 假.立即完成: 假.完成(pid)
                if 假.吞回音 > 0: 假.吞回音 -= 1; return
                self.回(200, {'prompt_id': pid, 'number': len(假.提交), 'node_errors': {}})

        self.服 = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.地址 = f'http://127.0.0.1:{self.服.server_address[1]}'
        threading.Thread(target=self.服.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True).start()

    def 关(self):
        self.服.shutdown(); self.服.server_close()

    def 完成(self, pid, 输出='照工作流', 状态=None):
        """把任务从队列挪进历史。输出默认照工作流保存节点的 filename_prefix 给一个 mp4。"""
        项 = next(x for x in self.队列 if x[1] == pid); self.队列.remove(项)
        if 输出 == '照工作流':
            子, _, 名 = next(v['inputs']['filename_prefix'] for v in 项[2].values() if 'filename_prefix' in v['inputs']).rpartition('/')
            输出 = {'9': {'images': [{'filename': f'{名}_00001_.mp4', 'subfolder': 子, 'type': 'output'}], 'animated': [True]}}
        self.历史[pid] = {'prompt': 项, 'outputs': 输出, 'status': 状态 or {'status_str': 'success', 'completed': True, 'messages': []}}


def 空端口():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); 口 = s.getsockname()[1]; s.close(); return 口


class 用例:
    """两种模式（local / ssh）都要过的测试。"""

    def setUp(self):
        self.假 = 假Comfy(); self.addCleanup(self.假.关)
        self.临 = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.临, True)
        self.睡过 = []; self.睡时 = None
        self.连 = Comfy(self.配置(self.假.地址), 重试=3, 间隔=0, 睡=self.睡)

    def 睡(self, 秒):
        self.睡过.append(秒)
        if self.睡时: self.睡时()

    def 排一个(self):
        """提交一个任务并让它留在队列里，返回任务号。"""
        pid = self.连.提交(工作流); self.assertEqual(self.假.队列[-1][1], pid); return pid

    # ----- 提交 -----
    def test_校验失败不重试_并打出原因(self):
        self.假.拒绝 = (400, 校验失败)
        with self.assertRaises(出错) as c: self.连.提交(工作流)
        话 = str(c.exception)
        self.assertIn('HTTP 400', 话); self.assertIn('Prompt outputs failed validation', 话)
        self.assertIn('节点 3（LoraLoaderModelOnly）', 话); self.assertIn('H3_Fight_Flow_V1.safetensors', 话)
        self.assertEqual(self.假.次数['/prompt'], 1, '被拒绝后不应该重试')
        self.assertEqual(self.睡过, [])

    def test_回音丢了不重复提交(self):
        self.假.吞回音 = 1
        pid = self.连.提交(工作流)
        self.assertEqual(len(self.假.提交), 1, '任务已经进了队列，不能再提交一遍')
        self.assertEqual(pid, self.假.队列[0][1])
        self.assertEqual(self.假.次数['/prompt'], 1)

    def test_回音丢了而且任务已经跑完_也认得出(self):
        self.假.吞回音 = 1; self.假.立即完成 = True
        pid = self.连.提交(工作流)
        self.assertEqual(len(self.假.提交), 1); self.assertIn(pid, self.假.历史)

    def test_请求没到就重提_只提一次(self):
        self.假.丢请求 = 1
        pid = self.连.提交(工作流)
        self.assertEqual(len(self.假.提交), 1); self.assertEqual(self.假.次数['/prompt'], 2)
        self.assertEqual(pid, self.假.队列[0][1])

    def test_提交带了令牌(self):
        self.排一个()
        self.assertEqual(len(self.假.提交[0]['extra_data'][令牌键]), 32)
        self.assertEqual(self.假.提交[0]['prompt'], 工作流)

    # ----- 连不上 -----
    def test_连不上有上限(self):
        连 = Comfy(self.配置(f'http://127.0.0.1:{空端口()}'), 重试=3, 间隔=7, 睡=self.睡)
        with self.assertRaises(连不上): 连.请求('/queue')
        self.assertEqual(self.睡过, [7, 7], '试 3 次，中间歇 2 次')
        self.睡过.clear()
        with self.assertRaises(连不上): 连.提交(工作流)
        self.assertEqual(len(self.睡过), 3)

    # ----- 等出片 -----
    def test_等到出片并下载(self):
        pid = self.排一个()
        self.睡时 = lambda: self.假.队列 and self.假.完成(pid)   # 第一次歇的时候任务跑完
        x = self.连.等(pid, 轮询=30)
        self.assertEqual((x['filename'], x['subfolder']), ('x_00001_.mp4', 'video'))
        self.assertEqual(self.睡过, [30])
        self.放远程文件(x); 本 = os.path.join(self.临, '下载.mp4')
        self.连.下载(x, 本)
        self.assertEqual(open(本, 'rb').read(), self.假.片)

    def test_执行出错_打出节点和原因(self):
        pid = self.排一个()
        self.假.完成(pid, 输出={}, 状态={'status_str': 'error', 'completed': False, 'messages': [
            ['execution_start', {'prompt_id': pid}],
            ['execution_error', {'node_id': '3', 'node_type': 'SelfLiftAvatarH3Sampler', 'exception_message': 'CUDA out of memory', 'traceback': []}]]})
        with self.assertRaises(出错) as c: self.连.等(pid)
        self.assertIn('CUDA out of memory', str(c.exception)); self.assertIn('SelfLiftAvatarH3Sampler', str(c.exception))

    def test_被取消(self):
        pid = self.排一个()
        self.假.完成(pid, 输出={}, 状态={'status_str': 'error', 'completed': False, 'messages': [['execution_interrupted', {'prompt_id': pid}]]})
        with self.assertRaises(出错) as c: self.连.等(pid)
        self.assertIn('中断', str(c.exception))

    def test_跑完没有mp4_不会一直等(self):
        pid = self.排一个()
        self.假.完成(pid, 输出={'9': {'images': [{'filename': 'x_00001_.png', 'subfolder': 'video', 'type': 'output'}]}})
        with self.assertRaises(出错) as c: self.连.等(pid)
        self.assertIn('没有 mp4', str(c.exception)); self.assertIn('x_00001_.png', str(c.exception))
        self.assertEqual(self.睡过, [])

    def test_任务丢了_不会一直等(self):
        pid = self.排一个(); self.假.队列.clear()   # ComfyUI 重启：队列没了，历史里也没有
        with self.assertRaises(出错) as c: self.连.等(pid)
        self.assertIn('不在队列里', str(c.exception))
        self.assertEqual(len(self.睡过), 1, '连着两轮都找不到才算丢')

    def test_等太久会停(self):
        pid = self.排一个()   # 任务一直排着
        with mock.patch('连接.time.monotonic', side_effect=[0, 60, 120, 7300, 7400]):
            with self.assertRaises(出错) as c: self.连.等(pid, 最多等=120)
        self.assertIn('120 分钟', str(c.exception)); self.assertIn(pid, str(c.exception))
        self.assertEqual(len(self.睡过), 2)

    def test_上传(self):
        图 = os.path.join(self.临, 'hero.png'); open(图, 'wb').write(b'\x89PNG fake')
        self.assertEqual(self.连.上传(图), 'hero.png')
        self.查上传(b'\x89PNG fake')


class 本机(用例, unittest.TestCase):
    def 配置(self, 地址): return {'mode': 'local', 'comfy_url': 地址}
    def 放远程文件(self, x): pass   # local 模式走 /view
    def 查上传(self, 内容):
        self.assertEqual(len(self.假.上传), 1); self.assertIn(内容, self.假.上传[0]); self.assertIn(b'filename="hero.png"', self.假.上传[0])


假ssh = '''#!/bin/sh
# 假 ssh：不连任何机器，去掉选项和主机名，在本机执行命令
echo ssh >> "$H3_FAKE_LOG"
if [ -n "$H3_FAKE_SSH_DOWN" ]; then echo "ssh: connect to host fakehost port 22: Connection refused" >&2; exit 255; fi
while [ "$1" = "-o" ]; do shift 2; done
shift
exec sh -c "$*"
'''
假scp = '''#!/bin/sh
# 假 scp：去掉选项和“主机:”前缀，在本机复制
echo scp >> "$H3_FAKE_LOG"
while [ "$1" = "-q" ] || [ "$1" = "-o" ]; do if [ "$1" = "-o" ]; then shift 2; else shift; fi; done
if [ -n "$H3_FAKE_SCP_DOWN" ]; then echo "scp: Connection closed" >&2; exit 255; fi
exec cp "${1#fakehost:}" "${2#fakehost:}"
'''


能演ssh = os.name != 'nt' and bool(shutil.which('curl') and shutil.which('sh'))


def 搭假远程(测试):
    """在临时目录里放假的 ssh、scp 和一个“远程 ComfyUI 目录”，返回（目录, 远程 ComfyUI 目录, 调用日志, 要加的环境变量）。"""
    壳 = tempfile.mkdtemp(); 测试.addCleanup(shutil.rmtree, 壳, True)
    for 名, 文 in (('ssh', 假ssh), ('scp', 假scp)):
        p = os.path.join(壳, 名); open(p, 'w').write(文); os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
    远 = os.path.join(壳, 'ComfyUI'); os.makedirs(os.path.join(远, 'input')); os.makedirs(os.path.join(远, 'output'))
    日志 = os.path.join(壳, '调用.log')
    return 壳, 远, 日志, {'PATH': 壳 + os.pathsep + os.environ['PATH'], 'H3_FAKE_LOG': 日志, 'LC_ALL': 'C'}


@unittest.skipUnless(能演ssh, 'ssh 模式的测试要 sh 和 curl')
class 经ssh(用例, unittest.TestCase):
    def setUp(self):
        self.壳, self.远, self.日志, 环境 = 搭假远程(self)
        补 = mock.patch.dict(os.environ, 环境); 补.start(); self.addCleanup(补.stop)
        super().setUp()

    def 配置(self, 地址): return {'mode': 'ssh', 'comfy_url': 地址, 'ssh_host': 'fakehost', 'remote_comfy_dir': self.远}
    def 调用(self, 名): return open(self.日志).read().split().count(名) if os.path.exists(self.日志) else 0

    def 放远程文件(self, x):
        目 = os.path.join(self.远, 'output', x['subfolder']); os.makedirs(目, exist_ok=True)
        open(os.path.join(目, x['filename']), 'wb').write(self.假.片)

    def 查上传(self, 内容):
        self.assertEqual(open(os.path.join(self.远, 'input', 'hero.png'), 'rb').read(), 内容)
        self.assertEqual(self.假.上传, [], 'ssh 模式用 scp 传图，不走 /upload/image')

    def test_ssh断了有上限(self):
        with mock.patch.dict(os.environ, {'H3_FAKE_SSH_DOWN': '1'}):
            with self.assertRaises(连不上) as c: self.连.请求('/queue')
        self.assertIn('Connection refused', str(c.exception)); self.assertEqual(self.调用('ssh'), 3)

    def test_scp断了有上限(self):
        with mock.patch.dict(os.environ, {'H3_FAKE_SCP_DOWN': '1'}):
            with self.assertRaises(连不上): self.连.下载({'filename': 'x.mp4', 'subfolder': 'video'}, os.path.join(self.临, 'x.mp4'))
        self.assertEqual(self.调用('scp'), 3)

    def test_远程没有这个文件_不重试(self):
        with self.assertRaises(出错) as c: self.连.下载({'filename': '没有.mp4', 'subfolder': 'video'}, os.path.join(self.临, 'x.mp4'))
        self.assertIn('No such file', str(c.exception)); self.assertEqual(self.调用('scp'), 1)


class 整条命令(unittest.TestCase):
    """把 工具/ 和 库/ 拷到临时目录，配上假 ComfyUI 和一个最小工作流模板，真的跑 出片.py。"""

    def setUp(self):
        self.假 = 假Comfy(); self.addCleanup(self.假.关)
        self.临 = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, self.临, True)
        for 名 in ('工具', '库'): shutil.copytree(os.path.join(根, 名), os.path.join(self.临, 名))
        json.dump({'mode': 'local', 'comfy_url': self.假.地址}, open(os.path.join(self.临, 'config.json'), 'w'))
        json.dump(工作流, open(os.path.join(self.临, '库', '模板', '无参考图.json'), 'w'))
        self.出 = os.path.join(self.临, 'out')

    def 跑(self, *参, 环境=None):
        return subprocess.run([sys.executable, os.path.join(self.临, '工具', '出片.py'), os.path.join(self.临, '库', '来源', 'k4f.txt'), '--输出', self.出, *参],
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120, env={**os.environ, 'PYTHONIOENCODING': 'utf-8', **(环境 or {})})

    @unittest.skipUnless(能演ssh, 'ssh 模式的测试要 sh 和 curl')
    def test_ssh模式_传首帧_提交_下载(self):
        壳, 远, 日志, 环境 = 搭假远程(self)
        json.dump({'mode': 'ssh', 'comfy_url': self.假.地址, 'ssh_host': 'fakehost', 'remote_comfy_dir': 远}, open(os.path.join(self.临, 'config.json'), 'w'))
        os.makedirs(os.path.join(远, 'output', 'h3_fight')); open(os.path.join(远, 'output', 'h3_fight', 't5_00001_.mp4'), 'wb').write(self.假.片)
        首帧 = os.path.join(self.临, '上一段最后一帧.png'); open(首帧, 'wb').write(b'\x89PNG fake')
        self.假.立即完成 = True
        r = self.跑('--名字', 't5', '--首帧', 首帧, 环境=环境)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(open(os.path.join(self.出, 't5.mp4'), 'rb').read(), self.假.片)
        self.assertEqual(open(os.path.join(远, 'input', '上一段最后一帧.png'), 'rb').read(), b'\x89PNG fake')
        self.assertEqual(len(self.假.提交), 1)
        流 = self.假.提交[0]['prompt']; 引导 = [v for v in 流.values() if v['class_type'] == 'MiniMaxH3AddGuide']
        self.assertEqual(len(引导), 1); self.assertEqual(流[引导[0]['inputs']['image'][0]]['inputs']['image'], '上一段最后一帧.png')

    def test_提交到下载(self):
        self.假.立即完成 = True
        r = self.跑('--名字', '测试段1', '--种子', '7')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('下载完成', r.stdout)
        self.assertEqual(open(os.path.join(self.出, '测试段1.mp4'), 'rb').read(), self.假.片)
        self.assertEqual(len(self.假.提交), 1)
        流 = self.假.提交[0]['prompt']
        self.assertEqual(流['9']['inputs']['filename_prefix'], 'h3_fight/测试段1'); self.assertEqual(流['3']['inputs']['seed'], 7)
        self.assertEqual(流['1']['inputs']['prompt'], open(os.path.join(根, '库', '来源', 'k4f.txt'), encoding='utf-8').read())
        self.assertIn('测试段1', open(os.path.join(self.出, '提交记录.txt'), encoding='utf-8').read())

    def test_校验失败_马上停_说清原因(self):
        self.假.拒绝 = (400, 校验失败)
        r = self.跑('--名字', 't2')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('节点 3（LoraLoaderModelOnly）', r.stderr); self.assertIn('自检.py', r.stderr)
        self.assertNotIn('连不上', r.stderr)
        self.assertEqual(self.假.次数['/prompt'], 1)
        self.assertFalse(os.path.exists(os.path.join(self.出, '提交记录.txt')))

    def test_名字里有空格或引号_不提交(self):
        for 名 in ('a b', "a'b", 'a/b', 'a;b'):
            with self.subTest(名字=名):
                r = self.跑('--名字', 名)
                self.assertNotEqual(r.returncode, 0); self.assertIn('--名字', r.stderr)
        self.assertEqual(self.假.次数['/prompt'], 0)

    def test_只导出_不联网(self):
        r = self.跑('--名字', 't3', '--只导出')
        self.assertIn('只导出', r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.出, 't3.json'))); self.assertEqual(sum(self.假.次数.values()), 0)


if __name__ == '__main__':
    unittest.main()
