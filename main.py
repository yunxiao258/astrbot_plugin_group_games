# -*- coding: utf-8 -*-
"""AstrBot 群聊互动小游戏插件：猜数字 / 成语接龙 / 猜歌名。

三个小游戏均按群/会话（session umo）隔离状态，互不干扰；
游戏状态纯内存保存，带超时自动清理（后台清扫任务）。
"""

import asyncio
import random
import re
import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.all import Plain
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

PLUGIN_NAME = "astrbot_plugin_group_games"
PLUGIN_AUTHOR = "云晓"
PLUGIN_DESC = "群聊互动小游戏：猜数字/成语接龙/猜歌名"
PLUGIN_VERSION = "1.0.0"

# ==================== 内置成语词库（四字成语，共 240 条） ====================
IDIOMS: list[str] = [
    "爱不释手", "安居乐业", "百发百中", "百花齐放", "百折不挠", "半途而废",
    "饱经风霜", "杯水车薪", "背水一战", "比翼双飞", "闭门造车", "变幻莫测",
    "别有洞天", "冰天雪地", "博古通今", "不耻下问", "不寒而栗", "不劳而获",
    "不约而同", "才高八斗", "草木皆兵", "层出不穷", "差强人意", "车水马龙",
    "称心如意", "趁热打铁", "成竹在胸", "赤胆忠心", "宠辱不惊", "出类拔萃",
    "初出茅庐", "触目惊心", "川流不息", "垂头丧气", "唇亡齿寒", "从容不迫",
    "粗茶淡饭", "寸草不生", "大器晚成", "大公无私", "大显身手", "大智若愚",
    "单枪匹马", "胆大心细", "当机立断", "刀山火海", "倒背如流", "得心应手",
    "滴水穿石", "地大物博", "颠三倒四", "点石成金", "雕虫小技", "东山再起",
    "斗转星移", "独出心裁", "独一无二", "对牛弹琴", "对症下药", "恩将仇报",
    "耳濡目染", "翻山越岭", "反败为胜", "返老还童", "方兴未艾", "飞黄腾达",
    "废寝忘食", "分道扬镳", "奋不顾身", "风调雨顺", "风平浪静", "风驰电掣",
    "锋芒毕露", "逢凶化吉", "扶摇直上", "浮光掠影", "福星高照", "赴汤蹈火",
    "覆水难收", "改过自新", "甘拜下风", "高瞻远瞩", "高枕无忧", "隔岸观火",
    "各显神通", "功成名就", "攻其不备", "古色古香", "蛊惑人心", "顾此失彼",
    "刮目相看", "寡不敌众", "拐弯抹角", "光明磊落", "鬼斧神工", "国泰民安",
    "过目不忘", "海底捞针", "海阔天空", "邯郸学步", "含辛茹苦", "汗马功劳",
    "好事多磨", "浩浩荡荡", "和盘托出", "鹤立鸡群", "横七竖八", "哄堂大笑",
    "狐假虎威", "虎头蛇尾", "花好月圆", "花言巧语", "画龙点睛", "画蛇添足",
    "欢天喜地", "慌不择路", "恍然大悟", "灰心丧气", "回天乏术", "讳疾忌医",
    "绘声绘色", "浑水摸鱼", "豁然开朗", "饥不择食", "机不可失", "鸡飞蛋打",
    "积少成多", "急中生智", "集思广益", "记忆犹新", "家喻户晓", "坚持不懈",
    "坚如磐石", "见多识广", "见机行事", "见义勇为", "江郎才尽", "将计就计",
    "交头接耳", "焦头烂额", "脚踏实地", "接二连三", "捷足先登", "竭尽全力",
    "金碧辉煌", "金蝉脱壳", "金玉良言", "津津有味", "锦上添花", "尽心尽力",
    "进退两难", "惊弓之鸟", "惊天动地", "精益求精", "井井有条", "居高临下",
    "鞠躬尽瘁", "举一反三", "举世闻名", "举足轻重", "聚精会神", "绝处逢生",
    "开诚布公", "开门见山", "开天辟地", "侃侃而谈", "刻不容缓", "刻舟求剑",
    "空穴来风", "口若悬河", "苦口婆心", "快马加鞭", "狂风暴雨", "脍炙人口",
    "滥竽充数", "狼狈为奸", "老马识途", "乐不思蜀", "雷厉风行", "冷嘲热讽",
    "理直气壮", "力挽狂澜", "励精图治", "良药苦口", "两全其美", "量力而行",
    "了如指掌", "临危不惧", "淋漓尽致", "琳琅满目", "流连忘返", "柳暗花明",
    "六神无主", "龙飞凤舞", "龙马精神", "龙腾虎跃", "炉火纯青", "鹿死谁手",
    "乱七八糟", "络绎不绝", "落花流水", "落井下石", "马到成功", "埋头苦干",
    "满载而归", "漫不经心", "毛遂自荐", "门可罗雀", "闷闷不乐", "面红耳赤",
    "妙不可言", "名不虚传", "名副其实", "明察秋毫", "明哲保身", "模棱两可",
    "莫名其妙", "墨守成规", "目不转睛", "目中无人", "目瞪口呆", "南辕北辙",
    "难能可贵", "能说会道", "鸟语花香", "宁缺毋滥", "弄巧成拙", "怒发冲冠",
    "呕心沥血", "藕断丝连", "拍案叫绝", "排山倒海", "盘根错节", "抛砖引玉",
    "披荆斩棘", "平步青云", "平分秋色", "破釜沉舟", "七上八下", "七嘴八舌",
    "旗开得胜", "杞人忧天", "千变万化", "千方百计", "千军万马", "千钧一发",
    "千篇一律", "千载难逢", "前车之鉴", "前赴后继", "前功尽弃", "巧夺天工",
    "亲密无间", "勤能补拙", "沁人心脾", "青出于蓝", "轻车熟路", "轻而易举",
    "倾盆大雨", "情不自禁", "情投意合", "晴天霹雳", "穷途末路", "秋高气爽",
    "曲高和寡", "取长补短", "全力以赴", "全神贯注", "群策群力", "人山人海",
    "人云亦云", "忍辱负重", "任劳任怨", "日积月累", "日月如梭", "融会贯通",
    "如虎添翼", "如胶似漆", "如雷贯耳", "如梦初醒", "如鱼得水", "入木三分",
    "三顾茅庐", "三心二意", "三言两语", "山清水秀", "山穷水尽", "善始善终",
    "赏心悦目", "上行下效", "少见多怪", "舍己为人", "舍生取义", "设身处地",
    "身经百战", "身临其境", "深入浅出", "深思熟虑", "神采奕奕", "神通广大",
    "审时度势", "生龙活虎", "声东击西", "胜券在握", "石破天惊", "十全十美",
    "实事求是", "守株待兔", "水到渠成", "水落石出", "水乳交融", "水深火热",
    "水泄不通", "顺理成章", "司空见惯", "四海为家", "四面楚歌", "四通八达",
    "似是而非", "肃然起敬", "随波逐流", "随机应变", "随心所欲", "损人利己",
    "谈笑风生", "叹为观止", "天翻地覆", "天花乱坠", "天经地义", "天罗地网",
    "天南地北", "天壤之别", "天衣无缝", "铁面无私", "同甘共苦", "同舟共济",
    "投其所好", "突飞猛进", "图穷匕见", "土崩瓦解", "推陈出新", "脱颖而出",
    "歪打正着", "外强中干", "完璧归赵", "玩物丧志", "万籁俱寂", "万无一失",
    "亡羊补牢", "忘恩负义", "望尘莫及", "望梅止渴", "望洋兴叹", "危言耸听",
    "威风凛凛", "唯命是从", "未雨绸缪", "温故知新", "闻鸡起舞", "稳如泰山",
    "问心无愧", "卧薪尝胆", "无边无际", "无出其右", "无地自容", "无价之宝",
    "无可奈何", "无穷无尽", "无声无息", "无所适从", "无微不至", "无忧无虑",
    "五光十色", "五花八门", "五体投地", "物美价廉", "物以类聚", "喜出望外",
    "喜气洋洋", "细水长流", "狭路相逢", "先发制人", "先见之明", "相得益彰",
    "相敬如宾", "想入非非", "小心翼翼", "心花怒放", "心旷神怡", "心灵手巧",
    "心满意足", "心有灵犀", "心直口快", "欣欣向荣", "欣喜若狂", "新陈代谢",
    "信口开河", "兴高采烈", "行云流水", "幸灾乐祸", "雄心壮志", "虚怀若谷",
    "栩栩如生", "旭日东升", "悬梁刺股", "学富五车", "雪中送炭", "严阵以待",
    "言而无信", "言而有信", "眼高手低", "扬长避短", "扬眉吐气", "摇摇欲坠",
    "一波三折", "一尘不染", "一成不变", "一筹莫展", "一触即发", "一蹴而就",
    "一刀两断", "一分为二", "一鼓作气", "一箭双雕", "一举两得", "一鸣惊人",
    "一目了然", "一如既往", "一丝不苟", "一往无前", "一望无际", "一五一十",
    "一言九鼎", "一针见血", "一知半解", "一字千金", "依依不舍", "仪表堂堂",
    "以德报怨", "以毒攻毒", "以逸待劳", "义不容辞", "义无反顾", "异口同声",
    "异想天开", "抑扬顿挫", "易如反掌", "意气风发", "意味深长", "因地制宜",
    "因小失大", "饮水思源", "迎刃而解", "勇往直前", "优柔寡断", "犹豫不决",
    "游刃有余", "有备无患", "有口皆碑", "有名无实", "有目共睹", "有始有终",
    "有条不紊", "有勇无谋", "愚公移山", "与日俱增", "语重心长", "欲盖弥彰",
    "欲擒故纵", "原封不动", "源远流长", "运筹帷幄", "载歌载舞", "再接再厉",
    "赞不绝口", "择善而从", "张灯结彩", "张冠李戴", "招兵买马", "朝气蓬勃",
    "朝三暮四", "针锋相对", "真知灼见", "争分夺秒", "争先恐后", "蒸蒸日上",
    "知己知彼", "知难而进", "执迷不悟", "只争朝夕", "纸上谈兵", "指鹿为马",
    "志同道合", "智勇双全", "置之不理", "中流砥柱", "众口一词", "众叛亲离",
    "众志成城", "周而复始", "珠联璧合", "转危为安", "装模作样", "壮志凌云",
    "追本溯源", "自暴自弃", "自不量力", "自告奋勇", "自力更生", "自食其果",
    "自相矛盾", "自以为是", "自知之明", "自作自受", "纵横交错", "走马观花",
    "足智多谋", "坐井观天", "坐立不安", "坐享其成",
]

# ==================== 内置歌单（标题 + 歌手 + 一句歌词提示） ====================
SONGS: list[dict] = [
    {"title": "晴天", "artist": "周杰伦", "lyric": "故事的小黄花，从出生那年就飘着"},
    {"title": "七里香", "artist": "周杰伦", "lyric": "窗外的麻雀，在电线杆上多嘴"},
    {"title": "青花瓷", "artist": "周杰伦", "lyric": "天青色等烟雨，而我在等你"},
    {"title": "稻香", "artist": "周杰伦", "lyric": "还记得你说家是唯一的城堡"},
    {"title": "告白气球", "artist": "周杰伦", "lyric": "塞纳河畔，左岸的咖啡"},
    {"title": "小幸运", "artist": "田馥甄", "lyric": "原来你是我最想留住的幸运"},
    {"title": "后来", "artist": "刘若英", "lyric": "后来，我总算学会了如何去爱"},
    {"title": "童话", "artist": "光良", "lyric": "你哭着对我说，童话里都是骗人的"},
    {"title": "平凡之路", "artist": "朴树", "lyric": "我曾经跨过山和大海"},
    {"title": "海阔天空", "artist": "Beyond", "lyric": "原谅我这一生不羁放纵爱自由"},
    {"title": "光辉岁月", "artist": "Beyond", "lyric": "钟声响起归家的讯号"},
    {"title": "十年", "artist": "陈奕迅", "lyric": "十年之前，我不认识你"},
    {"title": "孤勇者", "artist": "陈奕迅", "lyric": "爱你孤身走暗巷"},
    {"title": "演员", "artist": "薛之谦", "lyric": "简单点，说话的方式简单点"},
    {"title": "丑八怪", "artist": "薛之谦", "lyric": "如果世界漆黑，其实我很美"},
    {"title": "凉凉", "artist": "张碧晨", "lyric": "入夜渐微凉，繁花落地成霜"},
    {"title": "匆匆那年", "artist": "王菲", "lyric": "匆匆那年我们究竟说了几遍再见"},
    {"title": "传奇", "artist": "王菲", "lyric": "只是因为在人群中多看了你一眼"},
    {"title": "成都", "artist": "赵雷", "lyric": "和我在成都的街头走一走"},
    {"title": "南山南", "artist": "马頔", "lyric": "你在南方的艳阳里，大雪纷飞"},
    {"title": "夜空中最亮的星", "artist": "逃跑计划", "lyric": "夜空中最亮的星，能否听清"},
    {"title": "贝加尔湖畔", "artist": "李健", "lyric": "多少年以后，往事随云走"},
    {"title": "朋友", "artist": "周华健", "lyric": "朋友一生一起走"},
    {"title": "月亮代表我的心", "artist": "邓丽君", "lyric": "你问我爱你有多深"},
    {"title": "甜蜜蜜", "artist": "邓丽君", "lyric": "甜蜜蜜，你笑得甜蜜蜜"},
    {"title": "突然好想你", "artist": "五月天", "lyric": "突然好想你，你会在哪里"},
    {"title": "倔强", "artist": "五月天", "lyric": "我和我最后的倔强"},
    {"title": "年少有为", "artist": "李荣浩", "lyric": "假如我年少有为不自卑"},
    {"title": "李白", "artist": "李荣浩", "lyric": "要是能重来，我要选李白"},
    {"title": "消愁", "artist": "毛不易", "lyric": "一杯敬朝阳，一杯敬月光"},
    {"title": "光年之外", "artist": "邓紫棋", "lyric": "感受停在我发端的指尖"},
    {"title": "泡沫", "artist": "邓紫棋", "lyric": "阳光下的泡沫，是彩色的"},
    {"title": "修炼爱情", "artist": "林俊杰", "lyric": "修炼爱情的悲欢"},
    {"title": "江南", "artist": "林俊杰", "lyric": "风到这里就是黏"},
    {"title": "隐形的翅膀", "artist": "张韶涵", "lyric": "每一次，都在徘徊孤单中坚强"},
    {"title": "起风了", "artist": "买辣椒也用券", "lyric": "我曾将青春翻涌成她"},
]

# ==================== 帮助文本 ====================
HELP_TEXT = (
    "🎮 群聊互动小游戏玩法\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "🎯 猜数字：/猜数字 开始；/猜数字 <数字> 猜数；/猜数字 放弃 揭晓答案\n"
    "🐉 成语接龙：/接龙 开始；/接龙 <成语> 接龙；/接龙 结束 结算\n"
    "🎵 猜歌名：/猜歌 开始；/猜歌 <歌名> 猜歌（支持模糊匹配）；"
    "/猜歌 提示 获取歌手提示；/猜歌 放弃\n"
    "每轮游戏超时未参与将自动结束（超时时间可配置）。"
)

# 各游戏的会话内 key
KEY_GUESS = "guess"
KEY_CHAIN = "chain"
KEY_SONG = "song"
_GAME_KEYS = (KEY_GUESS, KEY_CHAIN, KEY_SONG)


@register(PLUGIN_NAME, PLUGIN_AUTHOR, PLUGIN_DESC, PLUGIN_VERSION)
class GroupGamesPlugin(Star):
    """群聊互动小游戏：猜数字 / 成语接龙 / 猜歌名"""

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        # 每轮游戏超时时间（秒），默认 120 秒
        self.timeout_seconds = self._safe_int(
            self.config.get("game_timeout_seconds"), 120
        )
        # 后台清扫任务的执行间隔（秒）
        self.sweep_interval = self._safe_int(
            self.config.get("sweep_interval_seconds"), 30
        )
        # 接龙是否允许重复使用成语
        self.allow_repeat_idiom = self._safe_bool(
            self.config.get("allow_repeat_idiom"), False
        )
        # 猜数字范围最大值
        self.guess_max = self._safe_int(self.config.get("guess_max"), 100)
        # 游戏状态：session key -> {"guess": state|None, "chain": state|None, "song": state|None}
        self._sessions: dict[str, dict] = {}
        self._cleanup_task: asyncio.Task | None = None
        logger.info(f"【{PLUGIN_NAME}】群聊互动小游戏插件初始化完成")

    # ==================== 工具方法 ====================

    @staticmethod
    def _safe_int(v, default: int) -> int:
        """防御性整数解析：非法输入回退默认值"""
        try:
            n = int(v)
            return n if n > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_bool(v, default: bool) -> bool:
        """防御性布尔解析：字符串 "false"/"0" 等不被误判为 True"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            low = v.strip().lower()
            if low in ("1", "true", "yes", "on"):
                return True
            if low in ("0", "false", "no", "off", ""):
                return False
            return default
        if isinstance(v, (int, float)):
            return bool(v)
        return default

    @staticmethod
    def _rest_of(event: AstrMessageEvent, cmd: str) -> str:
        """提取命令后的参数部分（容忍开头的 / 或 ／）"""
        text = (event.message_str or "").strip()
        m = re.match(r"^[\\/／]?\s*" + re.escape(cmd) + r"\s*(.*)$", text, re.S)
        return m.group(1).strip() if m else text

    @staticmethod
    def _key_of(event: AstrMessageEvent) -> str:
        """按会话唯一标识隔离游戏状态"""
        return str(event.session)

    @staticmethod
    def _sender_name(event: AstrMessageEvent) -> str:
        return str(event.get_sender_name() or "群友")

    @staticmethod
    def _sender_id(event: AstrMessageEvent) -> str:
        return str(event.get_sender_id() or "未知")

    def _reply(self, event: AstrMessageEvent, text: str):
        """构造纯文本回复"""
        return event.chain_result([Plain(text)])

    def _session(self, key: str) -> dict:
        """获取（必要时创建）某会话的游戏状态容器"""
        if key not in self._sessions:
            self._sessions[key] = {KEY_GUESS: None, KEY_CHAIN: None, KEY_SONG: None}
        return self._sessions[key]

    @staticmethod
    def _expired(game: dict, timeout: float) -> bool:
        """判断游戏是否已超时"""
        return time.time() - game.get("last_activity", 0) > timeout

    def _lazy_expire(self, key: str, gkey: str) -> bool:
        """惰性超时检查：游戏超时则就地清除，返回是否被清除"""
        sess = self._sessions.get(key)
        if not sess:
            return False
        game = sess.get(gkey)
        if game is not None and self._expired(game, self.timeout_seconds):
            sess[gkey] = None
            return True
        return False

    # ==================== 猜数字 ====================

    def start_guess(self, key: str, max_num: int = None) -> str:
        """开始猜数字游戏，返回提示文本"""
        sess = self._session(key)
        if sess[KEY_GUESS] and not self._expired(sess[KEY_GUESS], self.timeout_seconds):
            return "⚠️ 已有进行中的猜数字游戏，请先发送「/猜数字 放弃」结束当前游戏。"
        max_num = self._safe_int(max_num, self.guess_max) if max_num else self.guess_max
        sess[KEY_GUESS] = {
            "number": random.randint(1, max_num),
            "max": max_num,  # 本局范围上限（start_guess 可能指定与全局不同的值）
            "counters": {},  # sender_id -> 尝试次数
            "last_activity": time.time(),
        }
        return (
            f"🎯 猜数字开始！范围 1-{max_num}。\n"
            f"发送「/猜数字 <数字>」猜数，发送「/猜数字 放弃」揭晓答案。"
        )

    def do_guess(self, key: str, sender_id: str, sender_name: str, text: str) -> str:
        """处理一次猜数字，返回反馈文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_GUESS):
            return "⏰ 上一轮猜数字已超时结束，发送「/猜数字」重新开始吧。"
        game = sess[KEY_GUESS]
        if not game:
            return "⚠️ 当前没有进行中的猜数字游戏，发送「/猜数字」开始。"
        max_num = game.get("max") or self.guess_max
        guess = self._safe_int(text, 0)
        if guess <= 0:
            return (
                f"❓ 请输入 1-{max_num} 之间的数字，"
                f"或发送「/猜数字 放弃」结束游戏。"
            )
        if guess > max_num:
            return f"❌ 数字超出范围（1-{max_num}），请重新输入。"
        # 统计该玩家的尝试次数
        counters = game["counters"]
        counters[sender_id] = counters.get(sender_id, 0) + 1
        game["last_activity"] = time.time()
        if guess == game["number"]:
            sess[KEY_GUESS] = None
            return (
                f"🎉 恭喜 {sender_name} 猜中啦！答案是 {game['number']}，"
                f"{sender_name} 本轮共猜了 {counters[sender_id]} 次，游戏结束！"
            )
        if guess < game["number"]:
            return "⬆️ 小了，再大一点！"
        return "⬇️ 大了，再小一点！"

    def give_up_guess(self, key: str) -> str:
        """放弃猜数字并揭晓答案，返回提示文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_GUESS):
            return "⏰ 猜数字已超时结束，发送「/猜数字」重新开始吧。"
        game = sess[KEY_GUESS]
        if not game:
            return "⚠️ 当前没有进行中的猜数字游戏。"
        answer = game["number"]
        sess[KEY_GUESS] = None
        return f"🔓 答案揭晓：{answer}，下次加油！"

    # ==================== 成语接龙 ====================

    def start_chain(self, key: str, first: str = None) -> str:
        """开始成语接龙（first 可选指定起始成语），返回提示文本"""
        sess = self._session(key)
        if sess[KEY_CHAIN] and not self._expired(sess[KEY_CHAIN], self.timeout_seconds):
            return "⚠️ 已有进行中的成语接龙，请先发送「/接龙 结束」结束当前游戏。"
        word = first if first in IDIOMS else random.choice(IDIOMS)
        sess[KEY_CHAIN] = {
            "current": word,
            "used": [word],
            "count": 0,  # 已成功接上的条数（不含起始成语）
            "last_activity": time.time(),
        }
        return (
            f"🐉 成语接龙开始！起始成语：{word}。\n"
            f"回复「/接龙 <成语>」接龙（首字需为「{word[-1]}」），"
            f"「/接龙 结束」结算。"
        )

    def do_chain(self, key: str, sender_name: str, text: str) -> str:
        """处理一次接龙，返回反馈文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_CHAIN):
            return "⏰ 成语接龙已超时结束，发送「/接龙」重新开始吧。"
        game = sess[KEY_CHAIN]
        if not game:
            return "⚠️ 当前没有进行中的成语接龙，发送「/接龙」开始。"
        word = (text or "").strip()
        if len(word) != 4:
            return "❌ 接龙失败：请接四字成语。"
        if word[0] != game["current"][-1]:
            return (
                f"❌ 接龙失败：需以「{game['current'][-1]}」开头，"
                f"你以「{word[0]}」开头了。"
            )
        if word not in IDIOMS:
            return f"❌ 接龙失败：「{word}」不在内置成语词库中。"
        if not self.allow_repeat_idiom and word in game["used"]:
            return f"❌ 接龙失败：「{word}」已被使用过，不能重复。"
        game["used"].append(word)
        game["current"] = word
        game["count"] += 1
        game["last_activity"] = time.time()
        return (
            f"✅ {sender_name} 接上！当前成语：{word}（已接 {game['count']} 条），"
            f"下一位需以「{word[-1]}」开头。"
        )

    def end_chain(self, key: str) -> str:
        """结束成语接龙并结算条数，返回提示文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_CHAIN):
            return "⏰ 成语接龙已超时结束。"
        game = sess[KEY_CHAIN]
        if not game:
            return "⚠️ 当前没有进行中的成语接龙。"
        total = game["count"] + 1
        chain_str = " → ".join(game["used"])
        sess[KEY_CHAIN] = None
        return f"🏁 接龙结束！共接 {total} 条：{chain_str}"

    # ==================== 猜歌名 ====================

    def start_song(self, key: str) -> str:
        """开始猜歌游戏，返回提示文本"""
        sess = self._session(key)
        if sess[KEY_SONG] and not self._expired(sess[KEY_SONG], self.timeout_seconds):
            return "⚠️ 已有进行中的猜歌游戏，请先发送「/猜歌 放弃」结束当前游戏。"
        song = random.choice(SONGS)
        sess[KEY_SONG] = {
            "title": song["title"],
            "artist": song["artist"],
            "lyric": song["lyric"],
            "hinted": False,
            "last_activity": time.time(),
        }
        return (
            f"🎵 猜歌名开始！歌词提示：「{song['lyric']}」\n"
            f"发送「/猜歌 <歌名>」回答，「/猜歌 提示」获取歌手提示，"
            f"「/猜歌 放弃」揭晓答案。"
        )

    @staticmethod
    def _normalize_song(text: str) -> str:
        """规范化歌名：去空白与标点，转小写，便于模糊匹配"""
        # 去掉方括号后，用字符类去除空白与常见中英文标点（避免无效转义告警）
        text = (text or "").replace("[", "").replace("]", "")
        return re.sub(
            r"[\s\u3000，。！？、；：""''（）《》_·.!?,;:(){}…~·/\\-]",
            "",
            text,
        ).lower()

    def _song_matches(self, guess: str, title: str) -> bool:
        """模糊匹配：全等 / 互为子串 / 猜测文本中任一 2 字以上片段命中标题"""
        ng, nt = self._normalize_song(guess), self._normalize_song(title)
        if not ng or not nt:
            return False
        if ng == nt:
            return True
        if len(ng) >= 2 and ng in nt:
            return True
        if len(nt) >= 2 and nt in ng:
            return True
        for i in range(len(ng)):
            for j in range(i + 2, len(ng) + 1):
                if ng[i:j] in nt:
                    return True
        return False

    def do_song(self, key: str, sender_name: str, text: str) -> str:
        """处理一次猜歌，返回反馈文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SONG):
            return "⏰ 猜歌游戏已超时结束，发送「/猜歌」重新开始吧。"
        game = sess[KEY_SONG]
        if not game:
            return "⚠️ 当前没有进行中的猜歌游戏，发送「/猜歌」开始。"
        if self._song_matches(text, game["title"]):
            sess[KEY_SONG] = None
            return (
                f"🎉 恭喜 {sender_name} 猜中啦！答案是《{game['title']}》"
                f"- {game['artist']}，游戏结束！"
            )
        game["last_activity"] = time.time()
        return "❌ 不对哦，再猜猜～（发送「/猜歌 提示」获取歌手提示）"

    def song_hint(self, key: str) -> str:
        """获取歌手提示，返回提示文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SONG):
            return "⏰ 猜歌游戏已超时结束，发送「/猜歌」重新开始吧。"
        game = sess[KEY_SONG]
        if not game:
            return "⚠️ 当前没有进行中的猜歌游戏。"
        game["hinted"] = True
        game["last_activity"] = time.time()
        return (
            f"💡 歌手提示：这首歌是「{game['artist']}」演唱的，"
            f"歌名共 {len(game['title'])} 个字。"
        )

    def give_up_song(self, key: str) -> str:
        """放弃猜歌并揭晓答案，返回提示文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SONG):
            return "⏰ 猜歌游戏已超时结束。"
        game = sess[KEY_SONG]
        if not game:
            return "⚠️ 当前没有进行中的猜歌游戏。"
        title, artist = game["title"], game["artist"]
        sess[KEY_SONG] = None
        return f"🔓 答案揭晓：《{title}》- {artist}，下次加油！"

    # ==================== 超时清扫 ====================

    def _sweep_expired(self, now: float = None) -> int:
        """清理所有超时游戏，返回清理的游戏数量；会话清空后一并删除"""
        now = now if now is not None else time.time()
        cleaned = 0
        for key in list(self._sessions):
            sess = self._sessions[key]
            for gkey in _GAME_KEYS:
                game = sess.get(gkey)
                if game is not None and self._expired(game, self.timeout_seconds):
                    sess[gkey] = None
                    cleaned += 1
            if all(sess.get(g) is None for g in _GAME_KEYS):
                del self._sessions[key]
        return cleaned

    async def _cleanup_loop(self):
        """后台清扫任务：定时清理超时游戏"""
        while True:
            try:
                self._sweep_expired()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"【{PLUGIN_NAME}】清扫任务异常: {e}")
            await asyncio.sleep(self.sweep_interval)

    @filter.on_astrbot_loaded()
    async def _on_loaded(self):
        """AstrBot 加载完成后启动后台清扫任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def terminate(self):
        """插件卸载时取消后台清扫任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        self._sessions.clear()
        logger.info(f"【{PLUGIN_NAME}】插件已卸载，游戏状态已清理")

    # ==================== 指令入口 ====================

    @filter.command("游戏", priority=200)
    async def cmd_help(self, event: AstrMessageEvent):
        """查看群聊小游戏玩法列表"""
        return self._reply(event, HELP_TEXT)

    @filter.command("猜数字", priority=200)
    async def cmd_guess_number(self, event: AstrMessageEvent):
        """猜数字：开始 / 猜数 / 放弃"""
        key = self._key_of(event)
        rest = self._rest_of(event, "猜数字")
        if not rest:
            return self._reply(event, self.start_guess(key))
        if rest == "放弃":
            return self._reply(event, self.give_up_guess(key))
        return self._reply(
            event, self.do_guess(key, self._sender_id(event), self._sender_name(event), rest)
        )

    @filter.command("接龙", priority=200)
    async def cmd_chain(self, event: AstrMessageEvent):
        """成语接龙：开始 / 接龙 / 结束"""
        key = self._key_of(event)
        rest = self._rest_of(event, "接龙")
        if not rest:
            return self._reply(event, self.start_chain(key))
        if rest == "结束":
            return self._reply(event, self.end_chain(key))
        return self._reply(event, self.do_chain(key, self._sender_name(event), rest))

    @filter.command("猜歌", priority=200)
    async def cmd_song(self, event: AstrMessageEvent):
        """猜歌名：开始 / 猜歌 / 提示 / 放弃"""
        key = self._key_of(event)
        rest = self._rest_of(event, "猜歌")
        if not rest:
            return self._reply(event, self.start_song(key))
        if rest == "提示":
            return self._reply(event, self.song_hint(key))
        if rest == "放弃":
            return self._reply(event, self.give_up_song(key))
        return self._reply(event, self.do_song(key, self._sender_name(event), rest))
