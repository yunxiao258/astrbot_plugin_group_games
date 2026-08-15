# -*- coding: utf-8 -*-
"""AstrBot 群聊互动小游戏插件单元测试。

直接调用插件逻辑方法（异步命令入口用 asyncio.run），
覆盖：猜数字（大/小/中/放弃/非法输入）、成语接龙（首尾字/词库/结算）、
猜歌（全等/模糊/提示/放弃）、群会话隔离、超时清理、随机 seed 固定。
"""
import asyncio
import random
import sys
import time
import unittest

# 兼容控制台编码，避免中文断言输出乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, r"D:\astrbot\data\plugins")

from astrbot_plugin_group_games.main import (  # noqa: E402
    GroupGamesPlugin,
    IDIOMS,
    SONGS,
)


class FakeSession:
    """最小会话替身：str() 返回会话 UMO（按会话隔离的 key）"""

    def __init__(self, umo="default:GroupMessage:1001"):
        self.umo = umo

    def __str__(self):
        return self.umo


class FakeEvent:
    """最小事件替身：仅支持消息文本、会话与发送者信息"""

    def __init__(self, message_str="", umo="default:GroupMessage:1001",
                 sender_id="u1", sender_name="张三"):
        self.session = FakeSession(umo)
        self.message_str = message_str
        self._sender_id = sender_id
        self._sender_name = sender_name
        self.sent = []

    def get_sender_id(self):
        return self._sender_id

    def get_sender_name(self):
        return self._sender_name

    def get_group_id(self):
        return self.session.umo.split(":")[-1]

    def chain_result(self, chain):
        return chain

    async def send(self, chain):
        self.sent.append(chain)
        return None


def make_plugin(**cfg):
    """构造插件实例，默认配置可覆盖"""
    base = {
        "game_timeout_seconds": 120,
        "sweep_interval_seconds": 30,
        "guess_max": 100,
        "allow_repeat_idiom": False,
    }
    base.update(cfg)
    return GroupGamesPlugin(None, base)


# ==================== 猜数字 ====================

class TestGuessNumber(unittest.TestCase):
    def _number(self, p, key):
        return p._sessions[key]["guess"]["number"]

    def test_seed_fixed_and_range(self):
        # 相同 seed 两次开局数字一致，且落在 1-100
        random.seed(42)
        p1 = make_plugin()
        p1.start_guess("a")
        n1 = self._number(p1, "a")
        random.seed(42)
        p2 = make_plugin()
        p2.start_guess("a")
        n2 = self._number(p2, "a")
        self.assertEqual(n1, n2)
        self.assertGreaterEqual(n1, 1)
        self.assertLessEqual(n1, 100)

    def test_high_low_hit(self):
        random.seed(7)
        p = make_plugin()
        p.start_guess("g1")
        n = self._number(p, "g1")
        # 大了 / 小了 反馈
        if n == 1:
            self.assertIn("大", p.do_guess("g1", "u1", "张三", "2"))
            attempts = 2
        elif n == 100:
            self.assertIn("小", p.do_guess("g1", "u1", "张三", "99"))
            attempts = 2
        else:
            self.assertIn("大", p.do_guess("g1", "u1", "张三", str(n + 1)))
            self.assertIn("小", p.do_guess("g1", "u1", "张三", str(n - 1)))
            attempts = 3
        # 猜中：播报猜中者与次数
        r = p.do_guess("g1", "u1", "张三", str(n))
        self.assertIn("猜中", r)
        self.assertIn("张三", r)
        self.assertIn(f"共猜了 {attempts} 次", r)
        # 游戏已结束
        r = p.do_guess("g1", "u1", "张三", str(n))
        self.assertIn("没有进行中", r)

    def test_invalid_input(self):
        p = make_plugin()
        p.start_guess("g2")
        self.assertIn("请输入", p.do_guess("g2", "u1", "张三", "abc"))
        self.assertIn("请输入", p.do_guess("g2", "u1", "张三", "0"))
        self.assertIn("请输入", p.do_guess("g2", "u1", "张三", "-5"))
        self.assertIn("超出范围", p.do_guess("g2", "u1", "张三", "101"))

    def test_custom_max_boundary(self):
        # 自定义范围（/猜数字 1000）：校验必须用本局上限而非全局默认
        random.seed(11)
        p = make_plugin(guess_max=100)
        p.start_guess("c1", max_num=1000)
        n = self._number(p, "c1")
        self.assertGreaterEqual(n, 1)
        self.assertLessEqual(n, 1000)
        # 100 以内的合法猜测不应被误判超出范围
        r = p.do_guess("c1", "u1", "张三", "150")
        self.assertNotIn("超出范围", r)
        # 超过本局上限才报超出
        r2 = p.do_guess("c1", "u1", "张三", "1001")
        self.assertIn("超出范围", r2)
        # 提示文本中的范围随本局上限
        r3 = p.do_guess("c1", "u1", "张三", "0")
        self.assertIn("1-1000", r3)

    def test_custom_max_invalid_falls_back(self):
        # 非法 max_num 回退全局默认
        random.seed(3)
        p = make_plugin(guess_max=50)
        p.start_guess("c2", max_num="abc")
        n = self._number(p, "c2")
        self.assertLessEqual(n, 50)
        self.assertGreaterEqual(n, 1)

    def test_allow_repeat_dirty_value(self):
        # 字符串 "false" 不应被误判为允许重复
        p = make_plugin(allow_repeat_idiom="false")
        self.assertFalse(p.allow_repeat_idiom)

    def test_give_up(self):
        p = make_plugin()
        self.assertIn("没有进行中", p.give_up_guess("g3"))
        p.start_guess("g3")
        r = p.give_up_guess("g3")
        self.assertIn("答案揭晓", r)
        self.assertIn("没有进行中", p.give_up_guess("g3"))

    def test_start_when_active(self):
        p = make_plugin()
        p.start_guess("g4")
        r = p.start_guess("g4")
        self.assertIn("已有进行中", r)

    def test_counts_per_sender(self):
        # 两个不同玩家各自计数互不影响
        random.seed(1)
        p = make_plugin()
        p.start_guess("g5")
        n = self._number(p, "g5")
        if n > 1:
            p.do_guess("g5", "u1", "张三", str(n - 1))
        if n < 100:
            p.do_guess("g5", "u2", "李四", str(n + 1))
        r = p.do_guess("g5", "u1", "张三", str(n))
        self.assertIn("共猜了 2 次", r)


# ==================== 成语接龙 ====================

class TestIdiomChain(unittest.TestCase):
    def test_wordlist_size_and_shape(self):
        self.assertGreaterEqual(len(IDIOMS), 200)
        self.assertTrue(all(len(w) == 4 for w in IDIOMS))
        self.assertEqual(len(set(IDIOMS)), len(IDIOMS))

    def test_chain_flow_and_validation(self):
        p = make_plugin()
        # 找一个末字可被其他成语衔接的起始成语，保证测试可稳定接龙
        first = next(
            w for w in IDIOMS
            if any(x != w and x[0] == w[-1] for x in IDIOMS)
        )
        r = p.start_chain("g1", first=first)
        self.assertIn(first, r)
        self.assertIn(f"「{first[-1]}」", r)
        cands = [x for x in IDIOMS if x[0] == first[-1] and x != first]
        self.assertTrue(cands)

        # 成功接上一条
        r = p.do_chain("g1", "张三", cands[0])
        self.assertIn("接上", r)
        self.assertIn("已接 1 条", r)
        cur = p._sessions["g1"]["chain"]["current"]
        self.assertEqual(cur, cands[0])

        # 首字与上一条末字不符
        other = next(w for w in IDIOMS if w[0] != cur[-1])
        r = p.do_chain("g1", "张三", other)
        self.assertIn("需以", r)
        self.assertIn(f"「{cur[-1]}」", r)

        # 首字正确但不在词库（4 字且首字正确）
        fake = cur[-1] + "啊哈哈"
        r = p.do_chain("g1", "张三", fake)
        self.assertIn("词库", r)

        # 长度不足
        r = p.do_chain("g1", "张三", "哈哈")
        self.assertIn("四字", r)

        # 结算（起始 1 条 + 接上 1 条）
        r = p.end_chain("g1")
        self.assertIn("共接 2 条", r)
        self.assertIn(first, r)
        self.assertIn(cands[0], r)

        # 结算后游戏结束
        r = p.end_chain("g1")
        self.assertIn("没有进行中", r)

    def test_chain_without_game(self):
        p = make_plugin()
        self.assertIn("没有进行中", p.do_chain("gx", "张三", "心花怒放"))
        self.assertIn("没有进行中", p.end_chain("gx"))

    def test_repeat_idiom_rejected(self):
        # 精益求精 首尾同字：接自己可同时满足首字校验并触发重复拦截
        p = make_plugin()
        p.start_chain("g2", first="精益求精")
        r = p.do_chain("g2", "张三", "精益求精")
        self.assertIn("使用过", r)

    def test_allow_repeat_idiom(self):
        p = make_plugin(allow_repeat_idiom=True)
        p.start_chain("g2", first="精益求精")
        # 允许重复：接自己应成功
        r = p.do_chain("g2", "张三", "精益求精")
        self.assertIn("接上", r)
        self.assertIn("已接 1 条", r)


# ==================== 猜歌名 ====================

class TestGuessSong(unittest.TestCase):
    def test_song_list_size(self):
        self.assertGreaterEqual(len(SONGS), 30)
        for s in SONGS:
            self.assertTrue(s["title"] and s["artist"] and s["lyric"])

    def test_seed_fixed(self):
        random.seed(5)
        p1 = make_plugin()
        p1.start_song("a")
        t1 = p1._sessions["a"]["song"]["title"]
        random.seed(5)
        p2 = make_plugin()
        p2.start_song("a")
        t2 = p2._sessions["a"]["song"]["title"]
        self.assertEqual(t1, t2)

    def test_exact_match(self):
        random.seed(3)
        p = make_plugin()
        p.start_song("g1")
        title = p._sessions["g1"]["song"]["title"]
        r = p.do_song("g1", "张三", title)
        self.assertIn("猜中", r)
        self.assertIn("张三", r)
        # 已结束
        r = p.do_song("g1", "张三", title)
        self.assertIn("没有进行中", r)

    def test_fuzzy_match_and_hint(self):
        random.seed(11)
        p = make_plugin()
        r = p.start_song("g2")
        self.assertIn("歌词提示", r)
        game = p._sessions["g2"]["song"]
        norm = p._normalize_song(game["title"])
        self.assertTrue(norm)
        # 猜错
        r = p.do_song("g2", "张三", "没有这首歌")
        self.assertIn("不对", r)
        # 模糊匹配：标题前两字 + 干扰标点
        frag = norm[:2]
        r = p.do_song("g2", "张三", frag + "？")
        self.assertIn("猜中", r)
        # 提示（新开一局）
        p.start_song("g3")
        game3 = p._sessions["g3"]["song"]
        r = p.song_hint("g3")
        self.assertIn("歌手提示", r)
        self.assertIn(game3["artist"], r)
        self.assertIn(f"{len(game3['title'])} 个字", r)
        # 放弃
        r = p.give_up_song("g3")
        self.assertIn(game3["title"], r)
        self.assertIn("答案揭晓", r)

    def test_give_up_without_game(self):
        p = make_plugin()
        self.assertIn("没有进行中", p.give_up_song("gx"))
        self.assertIn("没有进行中", p.song_hint("gx"))

    def test_normalize(self):
        p = make_plugin()
        self.assertEqual(p._normalize_song(" 夜空中 最亮的星！"), "夜空中最亮的星")
        self.assertEqual(p._normalize_song("晴天 - 周杰伦"), "晴天周杰伦")


# ==================== 会话隔离与超时 ====================

class TestIsolationAndTimeout(unittest.TestCase):
    def test_group_isolation(self):
        p = make_plugin()
        p.start_guess("default:GroupMessage:1001")
        # 另一个群没有游戏
        r = p.do_guess("default:GroupMessage:2002", "u1", "李四", "50")
        self.assertIn("没有进行中", r)
        # 同一群里三个游戏互相独立
        p.start_guess("default:GroupMessage:1001")
        p.start_chain("default:GroupMessage:1001")
        p.start_song("default:GroupMessage:1001")
        sess = p._sessions["default:GroupMessage:1001"]
        self.assertIsNotNone(sess["guess"])
        self.assertIsNotNone(sess["chain"])
        self.assertIsNotNone(sess["song"])
        # 结束接龙不影响猜数字
        p.end_chain("default:GroupMessage:1001")
        r = p.do_guess("default:GroupMessage:1001", "u1", "张三", "50")
        self.assertNotIn("没有进行中", r)

    def test_sweep_removes_expired(self):
        p = make_plugin(game_timeout_seconds=1)
        p.start_guess("g1")
        p.start_chain("g2")
        p.start_song("g2")
        p.start_song("g3")
        self.assertEqual(len(p._sessions), 3)
        old = time.time() - 999
        p._sessions["g1"]["guess"]["last_activity"] = old
        p._sessions["g2"]["chain"]["last_activity"] = old
        n = p._sweep_expired()
        self.assertEqual(n, 2)
        # 全部游戏超时的空会话被整体删除，仍有活跃游戏的会话保留
        self.assertNotIn("g1", p._sessions)
        self.assertIn("g2", p._sessions)
        self.assertIsNone(p._sessions["g2"]["chain"])
        self.assertIsNotNone(p._sessions["g2"]["song"])
        self.assertIsNotNone(p._sessions["g3"]["song"])

    def test_lazy_expire(self):
        # 即使清扫任务未运行，操作时也会惰性检测超时
        p = make_plugin(game_timeout_seconds=1)
        p.start_guess("g1")
        p._sessions["g1"]["guess"]["last_activity"] = 0
        r = p.do_guess("g1", "u1", "张三", "50")
        self.assertIn("超时", r)
        # 超时清理后游戏已不存在
        r = p.give_up_guess("g1")
        self.assertIn("没有进行中", r)

    def test_config_defensive(self):
        # 非法配置回退默认值
        p = make_plugin(game_timeout_seconds="abc", sweep_interval_seconds=-5)
        self.assertEqual(p.timeout_seconds, 120)
        self.assertEqual(p.sweep_interval, 30)
        p2 = make_plugin(game_timeout_seconds="50")
        self.assertEqual(p2.timeout_seconds, 50)

    def test_terminate(self):
        p = make_plugin()
        p.start_guess("g1")

        async def _t():
            p._cleanup_task = asyncio.create_task(p._cleanup_loop())
            await asyncio.sleep(0)
            await p.terminate()
            await asyncio.sleep(0)

        asyncio.run(_t())
        self.assertIsNone(p._cleanup_task)
        self.assertEqual(p._sessions, {})


# ==================== 命令入口（async 处理器） ====================

class TestCommands(unittest.TestCase):
    def test_help_command(self):
        p = make_plugin()
        result = asyncio.run(p.cmd_help(FakeEvent("/游戏")))
        text = result[0].text
        for kw in ("猜数字", "成语接龙", "猜歌名", "/接龙", "/猜歌"):
            self.assertIn(kw, text)

    def test_guess_number_command(self):
        p = make_plugin()
        result = asyncio.run(p.cmd_guess_number(FakeEvent("/猜数字 放弃")))
        self.assertIn("没有进行中", result[0].text)
        result = asyncio.run(p.cmd_guess_number(FakeEvent("/猜数字")))
        self.assertIn("猜数字开始", result[0].text)
        result = asyncio.run(p.cmd_guess_number(FakeEvent("/猜数字 50")))
        self.assertTrue(result[0].text)

    def test_chain_command(self):
        p = make_plugin()
        result = asyncio.run(p.cmd_chain(FakeEvent("/接龙")))
        self.assertIn("成语接龙开始", result[0].text)
        result = asyncio.run(p.cmd_chain(FakeEvent("/接龙 结束")))
        self.assertIn("共接", result[0].text)

    def test_song_command(self):
        p = make_plugin()
        result = asyncio.run(p.cmd_song(FakeEvent("/猜歌")))
        self.assertIn("猜歌名开始", result[0].text)
        result = asyncio.run(p.cmd_song(FakeEvent("/猜歌 提示")))
        self.assertIn("歌手提示", result[0].text)
        result = asyncio.run(p.cmd_song(FakeEvent("/猜歌 放弃")))
        self.assertIn("答案揭晓", result[0].text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
