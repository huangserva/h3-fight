# ComfyUI 连接，出片.py 用。mode=local 直接走 HTTP；mode=ssh 在远程机器上用 curl 发同样的请求（正文经 ssh 的标准输入传过去），传文件用 scp。
# 三种失败分开处理：
#   连不上（网络断、ssh 断、ComfyUI 没启动）：隔一会儿重试，到上限就停，报最后一次的原因；
#   ComfyUI 回了 4xx / 5xx（工作流校验失败、缺模型等）：不重试，把它说的原因原样打出来；
#   提交后没等到回音：先按令牌查队列和历史，确认没提交成功才重提，同一段不会出两遍。
# 等出片也有尽头：任务跑完没有 mp4、任务从队列里消失（ComfyUI 重启过）、超过 最多等 分钟，都会停下来说明原因。
import http.client, json, os, shlex, subprocess, time, urllib.error, urllib.parse, urllib.request, uuid


class 连不上(Exception):
    """网络这一层的失败，重试可能就好了。"""


class 出错(Exception):
    """ComfyUI 或远程命令明确说了不行，重试没用。"""


令牌键 = 'h3_fight_token'   # 提交时放进 extra_data，ComfyUI 会原样带进 /queue 和 /history，用来认“这是不是我刚才提交的那一个”
JSON头 = {'Content-Type': 'application/json'}


def 说人话(码, 正文):
    """把 ComfyUI 的报错整理成几行：哪个节点、什么原因。不是它的 JSON 格式就原样截一段。"""
    文 = 正文.decode('utf-8', 'replace') if isinstance(正文, bytes) else str(正文)
    行 = [f'ComfyUI 拒绝了请求（HTTP {码}）']
    try: d = json.loads(文)
    except ValueError: d = None
    if isinstance(d, dict) and ('error' in d or 'node_errors' in d):
        e = d.get('error')
        if isinstance(e, dict): 行[0] += '：' + '：'.join(str(e[k]) for k in ('message', 'details') if e.get(k))
        elif e: 行[0] += f'：{e}'
        节点错 = d.get('node_errors')
        for 号, v in (节点错.items() if isinstance(节点错, dict) else []):
            for x in v.get('errors', []):
                行.append(f'  节点 {号}（{v.get("class_type", "?")}）：' + '：'.join(str(x[k])[:300] for k in ('message', 'details') if x.get(k)))
    elif 文.strip(): 行.append('  ' + 文.strip()[:800])
    return '\n'.join(行)


class Comfy:
    def __init__(self, 配置, 重试=30, 间隔=10, 睡=time.sleep):
        """重试 × 间隔 = 连不上时最多等多久（默认 30 × 10 秒 = 5 分钟）。"""
        self.模式 = 配置.get('mode', 'local'); self.地址 = 配置.get('comfy_url', 'http://127.0.0.1:8188').rstrip('/')
        self.主机 = 配置.get('ssh_host', ''); self.远 = 配置.get('remote_comfy_dir', '')
        self.重试, self.间隔, self.睡 = 重试, 间隔, 睡

    # ---------- 发请求 ----------
    def 一次(self, path, data=None, headers=None, timeout=60):
        """发一个请求，只试一次，返回正文（bytes）。连不上 → 连不上；ComfyUI 回 4xx / 5xx → 出错。"""
        if self.模式 == 'ssh': return self._经ssh(path, data, headers or {}, timeout)
        req = urllib.request.Request(self.地址 + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()
        except urllib.error.HTTPError as e:   # 要排在 OSError 前面：HTTPError 也是 OSError
            raise 出错(说人话(e.code, e.read())) from None
        except (OSError, http.client.HTTPException) as e:
            raise 连不上(f'{self.地址}：{e}') from None

    def _经ssh(self, path, data, headers, timeout):
        cmd = ['curl', '-sS', '--max-time', str(timeout), '-w', r'\n%{http_code}']
        for k, v in headers.items(): cmd += ['-H', f'{k}: {v}']
        if data is not None: cmd += ['--data-binary', '@-']
        cmd.append(self.地址 + path)
        try:
            r = subprocess.run(['ssh', '-o', 'ConnectTimeout=20', self.主机, ' '.join(shlex.quote(x) for x in cmd)], capture_output=True,
                               **({'input': data} if data is not None else {'stdin': subprocess.DEVNULL}))
        except FileNotFoundError:
            raise 出错('这台机器没有 ssh 命令（mode=ssh 要用）') from None
        怨 = r.stderr.decode('utf-8', 'replace').strip()
        if r.returncode == 255: raise 连不上(f'ssh {self.主机}：{怨 or "连接失败"}')
        if r.returncode in (126, 127): raise 出错(f'远程机器 {self.主机} 上跑不了 curl：{怨}')
        if r.returncode: raise 连不上(f'{self.主机} 上的 curl 连不上 {self.地址}（退出码 {r.returncode}）：{怨}')
        正文, _, 码 = r.stdout.rpartition(b'\n')
        if not 码.isdigit(): raise 连不上(f'{self.主机} 上的 curl 没返回状态码')
        if int(码) >= 400: raise 出错(说人话(int(码), 正文))
        return 正文

    def 请求(self, path, data=None, headers=None, timeout=60):
        """可以放心重发的请求（查历史、查队列、下载、覆盖上传）：连不上就重试，到上限抛 连不上。提交任务不要用它，用 提交()。"""
        for i in range(self.重试):
            try: return self.一次(path, data, headers, timeout)
            except 连不上 as e:
                最后 = e
                if i + 1 < self.重试: self.睡(self.间隔)
        raise 连不上(f'试了 {self.重试} 次：{最后}')

    def _scp(self, 从, 到):
        for i in range(self.重试):
            try: r = subprocess.run(['scp', '-q', '-o', 'ConnectTimeout=20', 从, 到], capture_output=True, stdin=subprocess.DEVNULL)
            except FileNotFoundError: raise 出错('这台机器没有 scp 命令（mode=ssh 要用）') from None
            if r.returncode == 0: return
            最后 = r.stderr.decode('utf-8', 'replace').strip() or f'退出码 {r.returncode}'
            if 'No such file' in 最后 or 'not a regular file' in 最后:   # 文件本身不在，重试没用
                raise 出错(f'scp {从} → {到} 失败：{最后}')
            if i + 1 < self.重试: self.睡(self.间隔)
        raise 连不上(f'scp {从} → {到} 试了 {self.重试} 次：{最后}')

    # ---------- 出片的几步 ----------
    def 上传(self, 本地):
        """把图传到 ComfyUI 的 input 目录，返回 ComfyUI 里的文件名。"""
        名 = os.path.basename(本地)
        if self.模式 == 'ssh':
            self._scp(本地, f'{self.主机}:{self.远}/input/'); return 名
        边界 = uuid.uuid4().hex; 文件名 = 名.replace('"', '%22')
        体 = (f'--{边界}\r\nContent-Disposition: form-data; name="image"; filename="{文件名}"\r\nContent-Type: image/png\r\n\r\n').encode() \
            + open(本地, 'rb').read() + f'\r\n--{边界}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{边界}--\r\n'.encode()
        return json.loads(self.请求('/upload/image', 体, {'Content-Type': f'multipart/form-data; boundary={边界}'}))['name']

    def 找令牌(self, 令):
        """在队列和最近的历史里找带这个令牌的任务，返回任务号；没有返回 None。只试一次，连不上会抛。"""
        q = json.loads(self.一次('/queue') or b'{}')
        for it in list(q.get('queue_running', [])) + list(q.get('queue_pending', [])):
            if isinstance(it, (list, tuple)) and len(it) > 3 and isinstance(it[3], dict) and it[3].get(令牌键) == 令: return it[1]
        for pid, v in json.loads(self.一次('/history?max_items=64') or b'{}').items():
            p = v.get('prompt') if isinstance(v, dict) else None
            if isinstance(p, (list, tuple)) and len(p) > 3 and isinstance(p[3], dict) and p[3].get(令牌键) == 令: return pid
        return None

    def 提交(self, 工作流):
        """提交任务，返回任务号。没等到回音时，先查这个任务是不是其实已经进了队列，没有才重提。"""
        令 = uuid.uuid4().hex
        体 = json.dumps({'prompt': 工作流, 'extra_data': {令牌键: 令}}).encode()
        for _ in range(self.重试):
            try: 回 = self.一次('/prompt', 体, JSON头)
            except 连不上 as e: 最后 = e
            else:
                try: return json.loads(回)['prompt_id']
                except (ValueError, KeyError, TypeError): raise 出错(f'ComfyUI 的 /prompt 回了看不懂的内容：{回[:300]!r}') from None
            self.睡(self.间隔)   # 等一下再查：请求可能已经到了，只是回音丢了
            try:
                pid = self.找令牌(令)
                if pid: return pid
            except 连不上: pass   # 还是连不上：下一轮再试
        raise 连不上(f'试了 {self.重试} 次：{最后}')

    def 历史(self, pid):
        return json.loads(self.请求(f'/history/{pid}') or b'{}').get(pid, {})

    def 在队列(self, pid):
        return pid.encode() in self.请求('/queue')   # 不解析结构：任务号出现在队列里就算（正在跑或排队）

    def 等(self, pid, 轮询=30, 最多等=120):
        """等任务出完，返回输出的 mp4 那一项（filename / subfolder / type）。最多等 的单位是分钟，0 = 一直等。"""
        起 = time.monotonic(); 不见 = 0
        while True:
            h = self.历史(pid); st = h.get('status') or {}
            if st.get('status_str') == 'error':
                事 = [m for m in st.get('messages') or [] if isinstance(m, (list, tuple)) and len(m) > 1]
                e = [m[1] for m in 事 if m[0] == 'execution_error']
                if e: raise 出错(f'出错：节点 {e[0].get("node_id", "?")}（{e[0].get("node_type", "?")}）：{str(e[0].get("exception_message", ""))[:500]}')
                if any(m[0] == 'execution_interrupted' for m in 事): raise 出错('任务被中断了（有人在 ComfyUI 里取消了它）')
                raise 出错('出错：未知（ComfyUI 没给原因，看它的终端输出）')
            if h:   # 进了历史就是跑完了
                文件 = [x for v in (h.get('outputs') or {}).values() for k in ('images', 'videos', 'gifs') for x in v.get(k, []) if str(x.get('filename', '')).endswith('.mp4')]
                if 文件: return 文件[-1]
                有 = sorted({str(x.get('filename')) for v in (h.get('outputs') or {}).values() for xs in v.values() if isinstance(xs, list) for x in xs if isinstance(x, dict)})
                raise 出错(f'任务跑完了，但输出里没有 mp4（输出：{", ".join(有) or "空"}）。检查工作流的保存节点是不是存成了 mp4')
            if self.在队列(pid): 不见 = 0
            else:
                不见 += 1   # 可能正好在“刚跑完、历史还没查”的缝里，所以连着两轮都不见才算丢
                if 不见 >= 2: raise 出错(f'任务 {pid} 不在队列里，也没有历史记录：ComfyUI 可能重启过，或者队列被清空了。要重新提交')
            if 最多等 and time.monotonic() - 起 > 最多等 * 60:
                raise 出错(f'等了 {最多等:g} 分钟还没出完，不等了。任务 {pid} 可能还在 ComfyUI 里跑，出完的文件在它的 output 目录里；要多等就加大 --最多等')
            self.睡(轮询)

    def 下载(self, x, 本):
        """把 等() 返回的那个文件下载到本地路径 本。"""
        if self.模式 == 'ssh':
            self._scp(f"{self.主机}:" + f"{self.远}/output/{x.get('subfolder', '')}/{x['filename']}".replace('//', '/'), 本)
        else:
            q = urllib.parse.urlencode({'filename': x['filename'], 'subfolder': x.get('subfolder', ''), 'type': x.get('type', 'output')})
            数据 = self.请求(f'/view?{q}', timeout=600)
            with open(本, 'wb') as f: f.write(数据)
