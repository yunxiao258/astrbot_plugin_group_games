# -*- coding: utf-8 -*-
"""新增四种群游戏玩法单元测试。

覆盖：谁是卧底状态机（加入/描述/投票/淘汰/胜负/全局单局锁/超时推进）、
24 点表达式校验（合法/非法/注入攻击/除零/有解发牌）、猜成语防刷与得分、
猜价格高低提示与冷却、积分 JSON 原子持久化、新命令入口。
"""
import asyncio
import json
import os
import random
import sys
import tempfile
import time
import unittest

# 兼容控制台编码，避免中文断言输出乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, r"D:\astrbot\data\plugins")

from astrbot_plugin_group_games.main import (  # noqa: E402
    GroupGamesPlugin,
    HELP_TEXT,
    IDIOM_QUIZZES,
    KEY_SPY,
    PRICE_ITEMS,
    SPY_WORDS,
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
    """构造插件实例：默认配置 + 临时目录积分文件（避免污染插件目录）"""
    base = {
        "game_timeout_seconds": 120,
        "sweep_interval_seconds": 30,
        "guess_max": 100,
        "allow_repeat_idiom": False,
        "scores_file": os.path.join(tempfile.mkdtemp(), "scores.json"),
    }
    base.update(cfg)
    return GroupGamesPlugin(None, base)


def _start_spy_5(p):
    """开一局 5 人谁是卧底，返回 (key, 卧底 id, 平民 id 列表)"""
    k = "default:GroupMessage:1001"
    for i in range(5):
        p.do_spy_join(k, f"u{i}", f"玩家{i}")
    p.start_spy(k)
    game = p._sessions[k][KEY_SPY]
    spy_id = next(pid for pid, pl in game["players"].items() if pl["is_spy"])
    civilians = [pid for pid in game["players"] if pid != spy_id]
    return k, spy_id, civilians


# ==================== 谁是卧底 ====================

class TestSpy(unittest.TestCase):
    def test_word_pairs(self):
        self.assertGreaterEqual(len(SPY_WORDS), 30)
        for civilian, spy in SPY_WORDS:
            self.assertTrue(civilian and spy)
            self.assertNotEqual(civilian, spy)

    def test_join_flow_and_limits(self):
        p = make_plugin(spy_max_players=4)
        k = "k1"
        r = p.do_spy_join(k, "u1", "张三")
        self.assertIn("加入成功", r)
        self.assertIn("1/4", r)
        # 重复加入拒绝
        r = p.do_spy_join(k, "u1", "张三")
        self.assertIn("已经加入", r)
        # 人数上限（上限 4）
        for i in range(2, 5):
            p.do_spy_join(k, f"u{i}", f"玩家{i}")
        r = p.do_spy_join(k, "u5", "玩家5")
        self.assertIn("人数已满", r)
        # 人数不足不能开局
        p2 = make_plugin()
        k2 = "k2"
        p2.do_spy_join(k2, "u1", "张三")
        p2.do_spy_join(k2, "u2", "李四")
        r = p2.start_spy(k2)
        self.assertIn("人数不足", r)

    def test_start_assigns_words(self):
        random.seed(1)
        p = make_plugin()
        k, spy_id, _ = _start_spy_5(p)
        game = p._sessions[k][KEY_SPY]
        self.assertEqual(game["phase"], "describing")
        # 恰好 1 名卧底，且平民词相同、卧底词不同
        self.assertEqual(sum(1 for pl in game["players"].values() if pl["is_spy"]), 1)
        civilian_word = game["civilian_word"]
        for pid, pl in game["players"].items():
            if pid == spy_id:
                self.assertEqual(pl["word"], game["spy_word"])
            else:
                self.assertEqual(pl["word"], civilian_word)

    def test_join_after_start_rejected(self):
        random.seed(1)
        p = make_plugin()
        k, _, _ = _start_spy_5(p)
        r = p.do_spy_join(k, "u9", "玩家9")
        self.assertIn("不能中途加入", r)

    def test_desc_once_per_round_and_vote_phase(self):
        random.seed(1)
        p = make_plugin()
        k, _, _ = _start_spy_5(p)
        game = p._sessions[k][KEY_SPY]
        # 同一人重复描述被拒
        r = p.do_spy_desc(k, "u0", "玩家0", "第一次描述")
        self.assertIn("还剩 4 人", r)
        r = p.do_spy_desc(k, "u0", "玩家0", "第二次描述")
        self.assertIn("描述过", r)
        # 描述阶段不允许投票（此时还剩 4 人未描述，仍处于描述阶段）
        r = p.do_spy_vote(k, "u0", "2")
        self.assertNotIn("投票成功", r)
        self.assertIn("描述", r)
        # 其余 4 人描述完毕自动进入投票
        for pid in ("u1", "u2", "u3", "u4"):
            r = p.do_spy_desc(k, pid, f"玩家{pid}", "描述")
        self.assertIn("投票", r)
        self.assertEqual(game["phase"], "voting")
        self.assertIn("1. 玩家0", r)  # 投票名单带编号

    def test_civilian_win(self):
        random.seed(1)
        p = make_plugin()
        k, spy_id, civilians = _start_spy_5(p)
        game = p._sessions[k][KEY_SPY]
        # 第一轮全部描述
        for pid in list(game["players"]):
            p.do_spy_desc(k, pid, f"玩家{pid}", "描述")
        # 全体投卧底：卧底出局 → 平民胜（卧底不能投自己，改投一名平民）
        alive = [x[0] for x in p._spy_alive_list(game)]
        spy_idx = alive.index(spy_id) + 1
        civ_idx = alive.index(civilians[0]) + 1
        for pid in list(game["players"]):
            target = str(civ_idx) if pid == spy_id else str(spy_idx)
            p.do_spy_vote(k, pid, target)
        # 最后一票触发结算，卧底被淘汰
        self.assertIsNone(p._sessions[k][KEY_SPY])
        self.assertIsNone(p._spy_owner)
        # 平民胜：4 名存活平民各 +3 分
        for cid in civilians:
            self.assertEqual(p._scores[cid]["points"], 3)

    def test_spy_win_when_two_left(self):
        random.seed(2)
        p = make_plugin()
        k, spy_id, civilians = _start_spy_5(p)
        game = p._sessions[k][KEY_SPY]
        # 第一轮淘汰一个平民（目标玩家自己不能投自己，改投另一名存活玩家）
        for pid in list(game["players"]):
            p.do_spy_desc(k, pid, f"玩家{pid}", "d")
        target = civilians[0]
        alive = [x[0] for x in p._spy_alive_list(game)]
        idx = alive.index(target) + 1
        other = next(x for x in alive if x != target)
        for pid in list(game["players"]):
            p.do_spy_vote(k, pid, str(idx) if pid != target else str(alive.index(other) + 1))
        # 卧底还在：进入第二轮
        game = p._sessions[k][KEY_SPY]
        self.assertIsNotNone(game)
        self.assertEqual(game["phase"], "describing")
        self.assertEqual(game["round"], 2)
        # 第二轮再淘汰一个平民 → 存活 3 人
        for pid in [x[0] for x in p._spy_alive_list(game)]:
            p.do_spy_desc(k, pid, f"玩家{pid}", "d")
        target2 = civilians[1]
        alive2 = [x[0] for x in p._spy_alive_list(game)]
        idx2 = alive2.index(target2) + 1
        other2 = next(x for x in alive2 if x != target2)
        for pid in alive2:
            p.do_spy_vote(k, pid, str(idx2) if pid != target2 else str(alive2.index(other2) + 1))
        # 存活 3 人继续
        game = p._sessions[k][KEY_SPY]
        self.assertIsNotNone(game)
        # 第三轮淘汰最后一名平民 → 存活 2 人（卧底 + 平民）→ 卧底胜
        for pid in [x[0] for x in p._spy_alive_list(game)]:
            p.do_spy_desc(k, pid, f"玩家{pid}", "d")
        target3 = civilians[2]
        alive3 = [x[0] for x in p._spy_alive_list(game)]
        idx3 = alive3.index(target3) + 1
        other3 = next(x for x in alive3 if x != target3)
        for pid in alive3:
            p.do_spy_vote(k, pid, str(idx3) if pid != target3 else str(alive3.index(other3) + 1))
        self.assertIsNone(p._sessions[k][KEY_SPY])
        # 卧底 +5 分
        self.assertEqual(p._scores[spy_id]["points"], 5)

    def test_vote_validation(self):
        random.seed(1)
        p = make_plugin()
        k, spy_id, _ = _start_spy_5(p)
        game = p._sessions[k][KEY_SPY]
        # 让全员描述完进入投票
        for pid in list(game["players"]):
            p.do_spy_desc(k, pid, f"玩家{pid}", "d")
        self.assertEqual(game["phase"], "voting")
        # 无效序号
        r = p.do_spy_vote(k, "u0", "99")
        self.assertIn("无效序号", r)
        r = p.do_spy_vote(k, "u0", "abc")
        self.assertIn("无效序号", r)
        # 不能投自己
        alive = [x[0] for x in p._spy_alive_list(game)]
        self_idx = alive.index("u0") + 1
        r = p.do_spy_vote(k, "u0", str(self_idx))
        self.assertIn("不能投自己", r)
        # 重复投票拒绝
        target = alive[0] if alive[0] != "u0" else alive[1]
        r = p.do_spy_vote(k, "u0", str(alive.index(target) + 1))
        self.assertIn("投票成功", r)
        r = p.do_spy_vote(k, "u0", str(alive.index(target) + 1))
        self.assertIn("已经投过", r)

    def test_global_lock(self):
        p = make_plugin()
        r = p.do_spy_join("groupA", "u1", "张三")
        self.assertIn("加入成功", r)
        # 其他群被全局单局锁拒绝
        r = p.do_spy_join("groupB", "u2", "李四")
        self.assertIn("全局单局", r)
        # 结束 A 群游戏后锁释放，B 群可开
        r = p.end_spy("groupA")
        self.assertIn("词对", r)
        r = p.do_spy_join("groupB", "u2", "李四")
        self.assertIn("加入成功", r)

    def test_quit_join_phase_dissolve(self):
        p = make_plugin()
        p.do_spy_join("k", "u1", "张三")
        r = p.do_spy_quit("k", "u1")
        self.assertIn("解散", r)
        self.assertIsNone(p._sessions["k"][KEY_SPY])
        self.assertIsNone(p._spy_owner)

    def test_quit_in_game_ends_when_spy_survives(self):
        random.seed(2)
        p = make_plugin()
        k, spy_id, civilians = _start_spy_5(p)
        # 两个平民退出 → 存活 3 人（卧底 + 2 平民）继续
        r = p.do_spy_quit(k, civilians[0])
        self.assertIn("继续", r)
        r = p.do_spy_quit(k, civilians[1])
        self.assertIn("继续", r)
        self.assertIsNotNone(p._sessions[k][KEY_SPY])
        # 再退一个平民 → 存活 2 人且卧底在 → 卧底胜
        r = p.do_spy_quit(k, civilians[2])
        self.assertIn("卧底", r)
        self.assertIsNone(p._sessions[k][KEY_SPY])

    def test_describe_timeout_advances_to_vote(self):
        random.seed(1)
        p = make_plugin()
        k, _, _ = _start_spy_5(p)
        game = p._sessions[k][KEY_SPY]
        game["phase_start"] = time.time() - 999  # 描述阶段已超时
        r = p.do_spy_desc(k, "u0", "玩家0", "描述")
        self.assertIn("投票阶段", r)
        self.assertEqual(game["phase"], "voting")

    def test_vote_timeout_resolves(self):
        random.seed(1)
        p = make_plugin()
        k, _, _ = _start_spy_5(p)
        game = p._sessions[k][KEY_SPY]
        for pid in list(game["players"]):
            p.do_spy_desc(k, pid, f"玩家{pid}", "d")
        self.assertEqual(game["phase"], "voting")
        game["phase_start"] = time.time() - 999  # 投票阶段已超时
        r = p.do_spy_vote(k, "u0", "1")
        self.assertIn("结算", r)
        # 无人投票随机淘汰：可能继续也可能直接结束，但状态必须一致
        game2 = p._sessions[k].get(KEY_SPY)
        if game2 is not None:
            self.assertEqual(game2["phase"], "describing")
            self.assertGreaterEqual(game2["round"], 2)

    def test_sweep_releases_global_lock(self):
        p = make_plugin(game_timeout_seconds=1)
        p.do_spy_join("k", "u1", "张三")
        self.assertEqual(p._spy_owner, "k")
        p._sessions["k"][KEY_SPY]["last_activity"] = 0
        n = p._sweep_expired()
        self.assertEqual(n, 1)
        self.assertIsNone(p._spy_owner)
        # 锁释放后可重新开局
        r = p.do_spy_join("k2", "u2", "李四")
        self.assertIn("加入成功", r)


# ==================== 24 点 ====================

class Test24Point(unittest.TestCase):
    def test_valid_expressions(self):
        v = GroupGamesPlugin._validate_24_expr
        self.assertEqual(v("8/(3-8/3)", [8, 8, 3, 3]), (True, "正确！"))
        self.assertEqual(v("(1+2+3)*4", [1, 2, 3, 4]), (True, "正确！"))
        self.assertEqual(v("6/(1-3/4)", [1, 3, 4, 6]), (True, "正确！"))
        self.assertEqual(v("(8-6)*(8+4)", [8, 6, 8, 4]), (True, "正确！"))
        # 分数中间结果（5-1/5=24/5，再乘 5）
        self.assertEqual(v("(5-1/5)*5", [5, 1, 5, 5]), (True, "正确！"))

    def test_reject_injections_and_dirty(self):
        v = GroupGamesPlugin._validate_24_expr
        cards = [8, 8, 3, 3]
        # 幂运算 / 整除 / 取余 / 位运算
        for bad in ("8**2", "8//3", "8%3", "8^8"):
            ok, msg = v(bad, cards)
            self.assertFalse(ok, bad)
            self.assertIn("非法运算符", msg)
        # 函数调用与内置注入
        ok, msg = v("abs(8)", cards)
        self.assertFalse(ok)
        self.assertIn("非法内容", msg)
        ok, msg = v("__import__('os')", cards)
        self.assertFalse(ok)
        # 浮点 / 科学计数 / 十六进制 / 下划线数字
        for bad in ("1.5", "1e3", "0x10", "1_000"):
            ok, msg = v(bad, cards)
            self.assertFalse(ok, bad)
            self.assertIn("非法数字", msg)
        # 数字使用次数与牌面不符（8 只出现了 1 次）
        ok, msg = v("8+3+3+3", cards)
        self.assertFalse(ok)
        self.assertIn("恰好", msg)
        # 缺少数字
        ok, msg = v("8+3", cards)
        self.assertFalse(ok)
        # 空表达式
        ok, msg = v("", cards)
        self.assertFalse(ok)
        self.assertIn("为空", msg)
        ok, msg = v("   ", cards)
        self.assertFalse(ok)
        # 语法错误（括号不闭合）
        ok, msg = v("(8+3*3", cards)
        self.assertFalse(ok)
        # 结果不等于 24（189）
        ok, msg = v("8*8*3-3", cards)
        self.assertFalse(ok)
        self.assertIn("不等于 24", msg)

    def test_reject_division_by_zero(self):
        v = GroupGamesPlugin._validate_24_expr
        ok, msg = v("8/0+8-0", [8, 8, 0, 0])
        self.assertFalse(ok)
        self.assertIn("除数", msg)

    def test_safe_eval_no_code_execution(self):
        # 单测安全求值器：函数调用/属性访问/复杂节点一律拒绝
        se = GroupGamesPlugin._safe_eval_24
        import ast as _ast
        for src in ("abs(8)", "8 .real", "open('x')", "lambda: 1"):
            node = _ast.parse(src, mode="eval").body
            with self.assertRaises(Exception):
                se(node)

    def test_solvable_checker(self):
        self.assertTrue(GroupGamesPlugin._cards_solvable([8, 8, 3, 3]))
        self.assertTrue(GroupGamesPlugin._cards_solvable([1, 2, 3, 4]))
        self.assertFalse(GroupGamesPlugin._cards_solvable([1, 1, 1, 1]))

    def test_deal_cards_always_solvable(self):
        random.seed(9)
        for _ in range(20):
            cards = GroupGamesPlugin._deal_24_cards()
            self.assertEqual(len(cards), 4)
            self.assertTrue(all(1 <= c <= 13 for c in cards))
            self.assertTrue(GroupGamesPlugin._cards_solvable(cards))

    def test_game_flow_and_cooldown(self):
        random.seed(3)
        p = make_plugin()
        r = p.start_24("k")
        self.assertIn("24 点挑战开始", r)
        game = p._sessions["k"]["game24"]
        self.assertEqual(len(game["cards"]), 4)
        # 错误算式
        r = p.do_24("k", "u1", "张三", "8+3")
        self.assertIn("❌", r)
        # 冷却：连续提交被拒
        r = p.do_24("k", "u1", "张三", "8+3")
        self.assertIn("频繁", r)
        # 绕过冷却：改牌面为已知可解的 8 8 3 3
        game["cooldown"]["u1"] = 0
        game["cards"] = [8, 8, 3, 3]
        r = p.do_24("k", "u1", "张三", "8/(3-8/3)")
        self.assertIn("算出 24", r)
        self.assertIn("积分", r)
        # 游戏已结束
        r = p.do_24("k", "u2", "李四", "8/(3-8/3)")
        self.assertIn("没有进行中", r)
        # 放弃（新开一局）
        p.start_24("k")
        r = p.give_up_24("k")
        self.assertIn("牌面", r)


# ==================== 猜成语 ====================

class TestIdiomQuiz(unittest.TestCase):
    def test_quiz_bank(self):
        self.assertGreaterEqual(len(IDIOM_QUIZZES), 50)
        for q in IDIOM_QUIZZES:
            self.assertTrue(q["clue"] and q["answer"] and q["explain"])

    def test_answer_with_score_and_explain(self):
        random.seed(4)
        p = make_plugin()
        r = p.start_idiom_quiz("k")
        self.assertIn("猜成语开始", r)
        ans = p._sessions["k"]["idiom_quiz"]["quiz"]["answer"]
        # 带空白的答案也能匹配
        r = p.do_idiom_quiz("k", "u1", "张三", "  " + ans + " ")
        self.assertIn("答对", r)
        self.assertIn("解释", r)
        self.assertIn("积分", r)
        self.assertEqual(p._scores["u1"]["points"], 2)
        # 已结束
        r = p.do_idiom_quiz("k", "u1", "张三", ans)
        self.assertIn("没有进行中", r)

    def test_cooldown_anti_spam(self):
        random.seed(4)
        p = make_plugin(idiom_quiz_cooldown_seconds=5)
        p.start_idiom_quiz("k")
        ans = p._sessions["k"]["idiom_quiz"]["quiz"]["answer"]
        # 答错进入冷却
        r = p.do_idiom_quiz("k", "u1", "张三", "完全错误的答案")
        self.assertIn("不对", r)
        # 冷却期内即使答对也被拒绝（防刷）
        r = p.do_idiom_quiz("k", "u1", "张三", ans)
        self.assertIn("冷却", r)
        # 冷却结束后可正常抢答
        game = p._sessions["k"]["idiom_quiz"]
        game["cooldown_until"] = 0
        r = p.do_idiom_quiz("k", "u1", "张三", ans)
        self.assertIn("答对", r)

    def test_timeout_and_give_up(self):
        random.seed(4)
        p = make_plugin(idiom_quiz_seconds=60)
        p.start_idiom_quiz("k")
        p._sessions["k"]["idiom_quiz"]["last_activity"] = 0
        r = p.do_idiom_quiz("k", "u1", "张三", "答案")
        self.assertIn("超时", r)
        # 放弃
        p.start_idiom_quiz("k")
        ans = p._sessions["k"]["idiom_quiz"]["quiz"]["answer"]
        r = p.give_up_idiom_quiz("k")
        self.assertIn("答案揭晓", r)
        self.assertIn(ans, r)
        self.assertIn("没有进行中", p.give_up_idiom_quiz("k"))

    def test_sweep_covers_new_games(self):
        # 新游戏 key 纳入清扫：猜成语 / 24点 / 猜价格 超时后被清理
        p = make_plugin(game_timeout_seconds=1)
        p.start_idiom_quiz("g1")
        p.start_24("g2")
        p.start_price("g3")
        old = time.time() - 999
        p._sessions["g1"]["idiom_quiz"]["last_activity"] = old
        p._sessions["g2"]["game24"]["last_activity"] = old
        p._sessions["g3"]["price"]["last_activity"] = old
        n = p._sweep_expired()
        self.assertEqual(n, 3)
        self.assertNotIn("g1", p._sessions)
        self.assertNotIn("g2", p._sessions)
        self.assertNotIn("g3", p._sessions)


# ==================== 猜价格 ====================

class TestPrice(unittest.TestCase):
    def test_items(self):
        self.assertGreaterEqual(len(PRICE_ITEMS), 20)
        for it in PRICE_ITEMS:
            self.assertTrue(it["name"])
            self.assertGreater(it["price"], 0)

    def test_high_low_hit(self):
        random.seed(6)
        p = make_plugin()
        r = p.start_price("k")
        self.assertIn("猜价格开始", r)
        price = p._sessions["k"]["price"]["item"]["price"]
        # 低了
        r = p.do_price("k", "u1", "张三", str(max(1, price - 1)))
        self.assertIn("低", r)
        # 冷却：3 秒内再猜被拒
        r = p.do_price("k", "u1", "张三", str(max(1, price - 2)))
        self.assertIn("太快", r)
        # 绕过冷却后：高了
        p._sessions["k"]["price"]["last_guess"]["u1"] = 0
        r = p.do_price("k", "u1", "张三", str(price + 1))
        self.assertIn("高", r)
        # 猜中得分并结束
        p._sessions["k"]["price"]["last_guess"]["u1"] = 0
        r = p.do_price("k", "u1", "张三", str(price))
        self.assertIn("猜中", r)
        self.assertIn("积分", r)
        self.assertEqual(p._scores["u1"]["points"], 2)
        # 已结束
        r = p.do_price("k", "u2", "李四", str(price))
        self.assertIn("没有进行中", r)

    def test_invalid_input(self):
        random.seed(6)
        p = make_plugin()
        p.start_price("k")
        r = p.do_price("k", "u1", "张三", "abc")
        self.assertIn("正整数", r)
        r = p.do_price("k", "u1", "张三", "-5")
        self.assertIn("正整数", r)
        r = p.do_price("k", "u1", "张三", "0")
        self.assertIn("正整数", r)

    def test_give_up(self):
        random.seed(6)
        p = make_plugin()
        r = p.give_up_price("k")
        self.assertIn("没有进行中", r)
        p.start_price("k")
        item = p._sessions["k"]["price"]["item"]
        r = p.give_up_price("k")
        self.assertIn("答案揭晓", r)
        self.assertIn(item["name"], r)


# ==================== 积分持久化 ====================

class TestScores(unittest.TestCase):
    def test_persist_roundtrip(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "scores.json")
        p1 = make_plugin(scores_file=path)
        self.assertEqual(p1._add_score("u1", "张三", 5), 5)
        # 新实例可重新加载
        p2 = make_plugin(scores_file=path)
        self.assertEqual(p2._scores["u1"]["points"], 5)
        self.assertEqual(p2._scores["u1"]["name"], "张三")
        # 磁盘文件为合法 JSON，且原子写无 .tmp 残留
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["u1"]["points"], 5)
        self.assertFalse(os.path.exists(path + ".tmp"))
        # 继续累计
        p2._add_score("u1", "张三", 3)
        p3 = make_plugin(scores_file=path)
        self.assertEqual(p3._scores["u1"]["points"], 8)

    def test_corrupt_file_falls_back(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "scores.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{corrupt json!!")
        p = make_plugin(scores_file=path)
        self.assertEqual(p._scores, {})  # 损坏文件静默回退，不崩溃
        # 之后仍可正常写入
        p._add_score("u1", "张三", 2)
        p2 = make_plugin(scores_file=path)
        self.assertEqual(p2._scores["u1"]["points"], 2)

    def test_unknown_sender_ignored(self):
        p = make_plugin()
        self.assertEqual(p._add_score("未知", "张三", 5), 0)
        self.assertEqual(p._scores, {})

    def test_show_scores_rank(self):
        p = make_plugin()
        p._add_score("u1", "张三", 3)
        p._add_score("u2", "李四", 8)
        p._add_score("u3", "王五", 5)
        text = p.show_scores()
        self.assertIn("李四", text)
        self.assertIn("8 分", text)
        # 排序：李四第一
        self.assertLess(text.index("1. 李四"), text.index("张三"))
        empty = make_plugin()
        self.assertIn("空空", empty.show_scores())


# ==================== 命令入口（async 处理器） ====================

class TestNewCommands(unittest.TestCase):
    def test_help_includes_new_games(self):
        for kw in ("谁是卧底", "猜成语", "24 点", "猜价格", "/积分"):
            self.assertIn(kw, HELP_TEXT)

    def test_spy_command(self):
        p = make_plugin()
        r = asyncio.run(p.cmd_spy(FakeEvent("/卧底 加入")))
        self.assertIn("加入成功", r[0].text)
        r = asyncio.run(p.cmd_spy(FakeEvent("/卧底 状态")))
        self.assertIn("谁是卧底", r[0].text)
        r = asyncio.run(p.cmd_spy(FakeEvent("/卧底 加入")))
        self.assertIn("已经加入", r[0].text)
        r = asyncio.run(p.cmd_spy(FakeEvent("/卧底 结束")))
        self.assertIn("词对", r[0].text)

    def test_idiom_quiz_command(self):
        p = make_plugin()
        r = asyncio.run(p.cmd_idiom_quiz(FakeEvent("/猜成语")))
        self.assertIn("猜成语开始", r[0].text)
        r = asyncio.run(p.cmd_idiom_quiz(FakeEvent("/猜成语 放弃")))
        self.assertIn("答案揭晓", r[0].text)

    def test_24_command(self):
        p = make_plugin()
        r = asyncio.run(p.cmd_24(FakeEvent("/24点")))
        self.assertIn("24 点挑战开始", r[0].text)
        r = asyncio.run(p.cmd_24(FakeEvent("/24点 放弃")))
        self.assertIn("牌面", r[0].text)

    def test_price_command(self):
        p = make_plugin()
        r = asyncio.run(p.cmd_price(FakeEvent("/猜价格")))
        self.assertIn("猜价格开始", r[0].text)
        r = asyncio.run(p.cmd_price(FakeEvent("/猜价格 放弃")))
        self.assertIn("答案揭晓", r[0].text)

    def test_scores_command(self):
        p = make_plugin()
        r = asyncio.run(p.cmd_scores(FakeEvent("/积分")))
        self.assertIn("积分榜", r[0].text)
        p._add_score("u1", "张三", 6)
        r = asyncio.run(p.cmd_scores(FakeEvent("/积分")))
        self.assertIn("张三", r[0].text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
