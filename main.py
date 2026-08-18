# -*- coding: utf-8 -*-
"""AstrBot 群聊互动小游戏插件：猜数字 / 成语接龙 / 猜歌名 / 谁是卧底 / 猜成语 / 24点 / 猜价格。

大部分小游戏按群/会话（session umo）隔离状态，互不干扰；
谁是卧底采用全局单局锁（同时只允许一局进行）；
游戏状态纯内存保存，带超时自动清理（后台清扫任务）；
积分持久化到 JSON 文件（tmp + os.replace 原子写）。
"""

import ast
import asyncio
import io
import json
import os
import random
import re
import time
import tokenize
from fractions import Fraction
from itertools import permutations, product

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

# ==================== 谁是卧底：近似词对（共 32 对） ====================
# 每对为 (平民词, 卧底词)，两词相近但不同，靠描述区分
SPY_WORDS: list[tuple[str, str]] = [
    ("手机", "座机"),
    ("咖啡", "奶茶"),
    ("地铁", "公交"),
    ("苹果", "香蕉"),
    ("饺子", "馄饨"),
    ("可乐", "雪碧"),
    ("汉堡", "三明治"),
    ("薯条", "薯片"),
    ("老虎", "狮子"),
    ("大象", "河马"),
    ("鲨鱼", "鲸鱼"),
    ("狼", "狗"),
    ("飞机", "火车"),
    ("汽车", "摩托车"),
    ("自行车", "电动车"),
    ("雨伞", "雨衣"),
    ("帽子", "头盔"),
    ("袜子", "手套"),
    ("眼镜", "墨镜"),
    ("手表", "手环"),
    ("冰箱", "冰柜"),
    ("洗衣机", "烘干机"),
    ("电视", "投影仪"),
    ("空调", "风扇"),
    ("台灯", "手电筒"),
    ("被子", "毯子"),
    ("枕头", "抱枕"),
    ("沙发", "椅子"),
    ("水杯", "保温杯"),
    ("钱包", "背包"),
    ("面条", "米粉"),
    ("米饭", "粥"),
]

# ==================== 猜成语题库（谜面 + 答案 + 解释，共 52 条） ====================
IDIOM_QUIZZES: list[dict] = [
    {"clue": "形容非常高兴、快乐的样子", "answer": "欢天喜地", "explain": "形容非常高兴、快乐。喜、乐：快乐。"},
    {"clue": "形容非常害怕，身子发抖", "answer": "不寒而栗", "explain": "不冷而发抖。形容非常恐惧。"},
    {"clue": "形容十分留恋，舍不得离开", "answer": "恋恋不舍", "explain": "形容舍不得离开。恋恋：留恋。"},
    {"clue": "比喻双方势均力敌，不相上下", "answer": "旗鼓相当", "explain": "双方力量相当，不分上下。旗鼓：古时作战用的旗帜和战鼓。"},
    {"clue": "形容说话算数，说到做到", "answer": "一言九鼎", "explain": "一句话抵得上九鼎重。形容说话极有分量，说到做到。"},
    {"clue": "比喻行动迅速，立刻见效", "answer": "立竿见影", "explain": "在阳光下竖起竹竿，立刻就看到影子。比喻见效迅速。"},
    {"clue": "形容很舍不得离开自己熟悉的地方", "answer": "依依不舍", "explain": "形容舍不得离开。依依：留恋的样子。"},
    {"clue": "比喻局势危急，情况十分紧张", "answer": "千钧一发", "explain": "千钧重物吊在一根发丝上。比喻情况万分危急。"},
    {"clue": "形容时间过得飞快", "answer": "光阴似箭", "explain": "时间像箭一样飞逝。形容时间流逝极快。"},
    {"clue": "比喻做事非常顺利，一举成功", "answer": "马到成功", "explain": "战马一到就取胜。形容事情顺利，很快成功。"},
    {"clue": "形容记忆深刻，永不忘却", "answer": "刻骨铭心", "explain": "铭刻在心灵深处。形容记忆深刻，永远不忘。"},
    {"clue": "比喻互相配合，亲密无间", "answer": "如胶似漆", "explain": "像胶和漆那样粘住。形容感情深厚，难分难舍。"},
    {"clue": "形容说话滔滔不绝，口才好", "answer": "口若悬河", "explain": "说话像瀑布倾泻。形容能说会道，口才极佳。"},
    {"clue": "比喻以小的代价换取大的利益", "answer": "以小博大", "explain": "用小的投入争取大的收益。比喻风险与收益的权衡。"},
    {"clue": "形容做事小心谨慎，毫不马虎", "answer": "一丝不苟", "explain": "连最细微的地方也不马虎。形容做事认真细致。"},
    {"clue": "比喻坚强不屈，坚韧不拔", "answer": "百折不挠", "explain": "无论受多少挫折都不退缩。形容意志坚强。"},
    {"clue": "形容书籍或作品内容精彩，广为流传", "answer": "脍炙人口", "explain": "美味人人都爱吃。比喻好的诗文人人称赞传诵。"},
    {"clue": "比喻忘恩负义，恩将仇报", "answer": "过河拆桥", "explain": "过了河就把桥拆掉。比喻达到目的后忘恩负义。"},
    {"clue": "形容团结一致，力量强大", "answer": "众志成城", "explain": "万众一心，像坚固的城墙。形容团结一致力量无比。"},
    {"clue": "比喻两者差别极大", "answer": "天壤之别", "explain": "像天和地一样差别巨大。比喻事物之间差异悬殊。"},
    {"clue": "形容文章或说话简明扼要", "answer": "言简意赅", "explain": "言辞简练，意思完备。形容说话写文章简明扼要。"},
    {"clue": "形容非常勤奋，坚持不懈", "answer": "持之以恒", "explain": "长久地坚持下去。形容有恒心，不半途而废。"},
    {"clue": "比喻做事有条理，安排得当", "answer": "井井有条", "explain": "形容条理分明，整齐不乱。井井：整齐的样子。"},
    {"clue": "形容数量极多，无法计算", "answer": "数不胜数", "explain": "数都数不过来。形容数量极多。"},
    {"clue": "比喻环境非常安静", "answer": "万籁俱寂", "explain": "形容周围环境非常安静，一点声音都没有。"},
    {"clue": "比喻人多力量大，集思广益", "answer": "集思广益", "explain": "集中众人智慧，广泛吸收有益意见。"},
    {"clue": "形容说话做事很有分寸", "answer": "恰到好处", "explain": "说话做事正好达到最适当的地步。"},
    {"clue": "比喻做事有始有终", "answer": "善始善终", "explain": "做事情有好的开头，也有好的结尾。形容做事能坚持到底。"},
    {"clue": "形容遇事不慌不忙，沉着镇定", "answer": "从容不迫", "explain": "不慌不忙，沉着镇静。形容遇事镇定自若。"},
    {"clue": "比喻互相帮助，共同进步", "answer": "取长补短", "explain": "吸取长处，弥补短处。比喻互相学习，共同提高。"},
    {"clue": "形容兴趣浓厚，乐在其中", "answer": "津津有味", "explain": "形容很有滋味或有兴趣的样子。津：唾液。"},
    {"clue": "比喻事物发展迅速，势不可挡", "answer": "势如破竹", "explain": "劈竹子时头上几节一破，下面就顺着刀口裂开。比喻节节胜利，毫无阻碍。"},
    {"clue": "形容非常疲惫，没有力气", "answer": "筋疲力尽", "explain": "筋疲力竭，力气用尽。形容极度疲劳。"},
    {"clue": "比喻眼光短浅，只看眼前", "answer": "鼠目寸光", "explain": "老鼠的眼光只有一寸远。比喻目光短浅，缺乏远见。"},
    {"clue": "形容彻底失败，无法挽回", "answer": "一败涂地", "explain": "形容败得不可收拾。涂地：肝脑涂地。"},
    {"clue": "比喻恰到好处地补充内容，使整体更完美", "answer": "锦上添花", "explain": "在锦上再绣花。比喻好上加好，美中添美。"},
    {"clue": "形容非常专心，注意力高度集中", "answer": "聚精会神", "explain": "集中精神，专心致志。形容注意力高度集中。"},
    {"clue": "比喻坚决果断，毫不犹豫", "answer": "当机立断", "explain": "抓住时机，立刻决断。形容处事果断。"},
    {"clue": "形容数量少而珍贵", "answer": "凤毛麟角", "explain": "凤凰的毛，麒麟的角。比喻稀少而珍贵的人或事物。"},
    {"clue": "比喻背地里说人坏话，搬弄是非", "answer": "两面三刀", "explain": "当面一套，背后一套。比喻阴险狡猾，耍两面派手法。"},
    {"clue": "形容形势危急，万分紧迫", "answer": "火烧眉毛", "explain": "火都烧到眉毛了。比喻形势非常急迫。"},
    {"clue": "比喻不受拘束，自由自在", "answer": "无拘无束", "explain": "没有拘束，自由自在。形容行动自由，不受限制。"},
    {"clue": "形容两人关系亲密，感情深厚", "answer": "形影不离", "explain": "像形体和影子那样分不开。形容彼此关系密切，经常在一起。"},
    {"clue": "比喻专心致志，不受外界干扰", "answer": "心无旁骛", "explain": "心思没有别的追求。形容专心致志，专心于一件事。"},
    {"clue": "形容自以为是，听不进别人意见", "answer": "刚愎自用", "explain": "固执己见，自以为是。形容十分固执自信，不听取他人意见。"},
    {"clue": "比喻做事有准备，胸有成竹", "answer": "未雨绸缪", "explain": "天还没下雨，先修补好门窗。比喻事先做好准备。"},
    {"clue": "形容景色优美，令人心旷神怡", "answer": "赏心悦目", "explain": "看了使人心情舒畅。形容美好的景色让人心情愉快。"},
    {"clue": "比喻力量悬殊，无法对抗", "answer": "寡不敌众", "explain": "人少的敌不过人多的。形容力量悬殊，难以取胜。"},
    {"clue": "形容坚持不懈，最终成功", "answer": "水滴石穿", "explain": "水滴不断滴落，能把石头滴穿。比喻坚持不懈，终会成功。"},
    {"clue": "比喻反复无常，变化多端", "answer": "变化多端", "explain": "形容变化极多，难以捉摸。端：头绪。"},
    {"clue": "形容非常谦虚，不自高自大", "answer": "虚怀若谷", "explain": "胸怀像山谷一样深广。形容十分谦虚，能容纳各种意见。"},
    {"clue": "比喻事情做到一半就停止", "answer": "半途而废", "explain": "走到半路就停下来。比喻做事不能坚持到底。"},
]

# ==================== 猜价格：商品表（名称 + 参考价，共 24 件） ====================
PRICE_ITEMS: list[dict] = [
    {"name": "苹果手机（一台）", "price": 5999},
    {"name": "华为手机（一台）", "price": 5499},
    {"name": "小米手机（一台）", "price": 1999},
    {"name": "无线蓝牙耳机（一副）", "price": 399},
    {"name": "机械键盘（一把）", "price": 299},
    {"name": "电竞鼠标（一个）", "price": 199},
    {"name": "27 寸显示器（一台）", "price": 1299},
    {"name": "笔记本电脑（一台）", "price": 5499},
    {"name": "平板电脑（一台）", "price": 2999},
    {"name": "智能手表（一块）", "price": 1499},
    {"name": "咖啡（一杯）", "price": 25},
    {"name": "奶茶（一杯）", "price": 18},
    {"name": "电影票（一张）", "price": 45},
    {"name": "地铁单程票（一张）", "price": 4},
    {"name": "羽毛球拍（一副）", "price": 350},
    {"name": "篮球（一个）", "price": 120},
    {"name": "电动牙刷（一支）", "price": 199},
    {"name": "保温杯（一个）", "price": 89},
    {"name": "行李箱（一个）", "price": 399},
    {"name": "山地自行车（一辆）", "price": 1599},
    {"name": "电饭煲（一个）", "price": 299},
    {"name": "空气炸锅（一个）", "price": 399},
    {"name": "扫地机器人（一台）", "price": 1999},
    {"name": "加湿器（一台）", "price": 129},
]

# ==================== 帮助文本 ====================
HELP_TEXT = (
    "🎮 群聊互动小游戏玩法\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "🎯 猜数字：/猜数字 开始；/猜数字 <数字> 猜数；/猜数字 放弃 揭晓答案\n"
    "🐉 成语接龙：/接龙 开始；/接龙 <成语> 接龙；/接龙 结束 结算\n"
    "🎵 猜歌名：/猜歌 开始；/猜歌 <歌名> 猜歌（支持模糊匹配）；"
    "/猜歌 提示 获取歌手提示；/猜歌 放弃\n"
    "🕵️ 谁是卧底：/卧底 加入 进房；/卧底 开始 开局（4-8 人）；"
    "/卧底 描述 <内容> 描述；/卧底 投票 <序号> 投票；/卧底 退出 / 结束\n"
    "📖 猜成语：/猜成语 开始；/猜成语 <成语> 抢答（答对得分）；/猜成语 放弃\n"
    "🔢 24 点：/24点 开始；/24点 <算式> 提交（仅 + - * / 与括号）；/24点 放弃\n"
    "💰 猜价格：/猜价格 开始；/猜价格 <价格> 猜价（提示高低）；/猜价格 放弃\n"
    "🏆 积分：/积分 查看积分排行榜\n"
    "每轮游戏限时进行、超时自动结束（时长可配置）。"
)

# 各游戏的会话内 key
KEY_GUESS = "guess"
KEY_CHAIN = "chain"
KEY_SONG = "song"
KEY_SPY = "spy"
KEY_IDIOM_QUIZ = "idiom_quiz"
KEY_24 = "game24"
KEY_PRICE = "price"
_GAME_KEYS = (KEY_GUESS, KEY_CHAIN, KEY_SONG, KEY_SPY, KEY_IDIOM_QUIZ, KEY_24, KEY_PRICE)


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
        # 谁是卧底：最少/最多参与人数、每轮描述与投票限时（秒）
        self.spy_min_players = self._safe_int(
            self.config.get("spy_min_players"), 4
        )
        self.spy_max_players = self._safe_int(
            self.config.get("spy_max_players"), 8
        )
        self.spy_describe_seconds = self._safe_int(
            self.config.get("spy_describe_seconds"), 60
        )
        self.spy_vote_seconds = self._safe_int(
            self.config.get("spy_vote_seconds"), 30
        )
        # 猜成语：单题限时与答错冷却（秒）
        self.idiom_quiz_seconds = self._safe_int(
            self.config.get("idiom_quiz_seconds"), 60
        )
        self.idiom_quiz_cooldown = self._safe_int(
            self.config.get("idiom_quiz_cooldown_seconds"), 5
        )
        # 24 点：单局限时与每人提交冷却（秒）
        self.game24_seconds = self._safe_int(
            self.config.get("game24_seconds"), 90
        )
        self.game24_cooldown = self._safe_int(
            self.config.get("game24_cooldown_seconds"), 3
        )
        # 猜价格：单局限时与每人猜测冷却（秒）
        self.price_seconds = self._safe_int(
            self.config.get("price_seconds"), 120
        )
        self.price_cooldown = self._safe_int(
            self.config.get("price_cooldown_seconds"), 3
        )
        # 积分持久化文件（相对路径基于插件目录解析）
        default_scores = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "scores.json"
        )
        scores_cfg = self.config.get("scores_file") or default_scores
        self.scores_path = (
            scores_cfg
            if os.path.isabs(scores_cfg)
            else os.path.join(
                os.path.dirname(os.path.abspath(__file__)), scores_cfg
            )
        )
        # 游戏状态：session key -> {"guess": ..., "chain": ..., "song": ..., ...}
        self._sessions: dict[str, dict] = {}
        self._cleanup_task: asyncio.Task | None = None
        # 谁是卧底全局单局锁：记录当前进行中卧底局所在的会话 key
        self._spy_owner: str | None = None
        # 积分表：sender_id -> {"name": 最近昵称, "points": 累计得分}
        self._scores: dict[str, dict] = {}
        self._load_scores()
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
            self._sessions[key] = {g: None for g in _GAME_KEYS}
        return self._sessions[key]

    def _expired(self, game: dict, timeout: float = None, now: float = None) -> bool:
        """判断游戏是否已超时；timeout 缺省时优先用游戏自带 seconds，否则用全局值"""
        if timeout is None:
            timeout = game.get("seconds") or self.timeout_seconds
        now = now if now is not None else time.time()
        return now - game.get("last_activity", 0) > timeout

    def _lazy_expire(self, key: str, gkey: str) -> bool:
        """惰性超时检查：游戏超时则就地清除（谁是卧底同时释放全局锁），返回是否被清除"""
        sess = self._sessions.get(key)
        if not sess:
            return False
        game = sess.get(gkey)
        if game is not None and self._expired(game):
            sess[gkey] = None
            if gkey == KEY_SPY:
                self._release_spy_lock(key)
            return True
        return False

    # ==================== 积分持久化（JSON 原子写） ====================

    def _load_scores(self):
        """从磁盘加载积分表（文件缺失/损坏时静默回退为空表）"""
        try:
            with open(self.scores_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._scores = data
        except (OSError, ValueError, TypeError):
            self._scores = {}

    def _save_scores(self):
        """积分表写入磁盘：先写 tmp 再 os.replace 原子替换，避免写一半损坏"""
        try:
            tmp = self.scores_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._scores, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.scores_path)
        except OSError as e:
            logger.warning(f"【{PLUGIN_NAME}】积分保存失败: {e}")

    def _add_score(self, sender_id: str, name: str, points: int) -> int:
        """为玩家增加积分并原子持久化，返回其累计总分"""
        points = self._safe_int(points, 0)
        if sender_id == "未知" or not sender_id:
            return 0
        entry = self._scores.setdefault(sender_id, {"name": name or "群友", "points": 0})
        entry["points"] = entry.get("points", 0) + points
        if name:
            entry["name"] = name
        self._save_scores()
        return entry["points"]

    def _release_spy_lock(self, key: str):
        """释放谁是卧底全局单局锁（若锁属于该会话）"""
        if self._spy_owner == key:
            self._spy_owner = None

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
        """模糊匹配：全等 / 互为子串 / 猜测文本中任一 2 字以上片段命中标题。

        片段命中判定可等价收敛为「任一 2 字片段命中」：若存在长度≥2 的
        子串命中标题，其首 2 字片段必然也命中；反之 2 字片段本身即为命中
        片段。因此只需检查全部 bigram，复杂度 O(len·len) 而非 O(len³)。
        """
        ng, nt = self._normalize_song(guess), self._normalize_song(title)
        if not ng or not nt:
            return False
        if ng == nt:
            return True
        if len(ng) >= 2 and ng in nt:
            return True
        if len(nt) >= 2 and nt in ng:
            return True
        for i in range(len(ng) - 1):
            if ng[i : i + 2] in nt:
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

    # ==================== 谁是卧底（全局单局锁） ====================

    @staticmethod
    def _spy_phase_name(game: dict) -> str:
        """卧底局阶段的中文名"""
        return {
            "joining": "加入中",
            "describing": "描述中",
            "voting": "投票中",
        }.get(game.get("phase"), str(game.get("phase")))

    @staticmethod
    def _spy_alive_list(game: dict) -> list:
        """存活玩家列表（按加入顺序），每项 (sender_id, player_dict)"""
        return [
            (pid, p) for pid, p in game["players"].items() if p.get("alive")
        ]

    def _spy_vote_prompt(self, game: dict) -> str:
        """生成投票阶段的提示文本（含存活玩家编号名单）"""
        lines = [
            f"🗳️ 投票阶段开始（限时 {game.get('vote_seconds', 30)} 秒）！"
            "存活玩家请发送「/卧底 投票 <序号>」（每人 1 票）："
        ]
        for i, (_, p) in enumerate(self._spy_alive_list(game), 1):
            lines.append(f"{i}. {p['name']}")
        return "\n".join(lines)

    def _spy_finish(self, key: str, game: dict, winner: str) -> str:
        """谁是卧底结束：揭晓身份、结算积分、清理状态并释放全局锁"""
        lines = []
        if winner == "平民":
            lines.append("🎉 平民获胜！卧底已被揪出。")
            for pid, p in game["players"].items():
                if p.get("alive"):
                    self._add_score(pid, p["name"], 3)
        elif winner == "卧底":
            lines.append("🎉 卧底获胜！成功潜伏到最后。")
            for pid, p in game["players"].items():
                if p.get("is_spy"):
                    self._add_score(pid, p["name"], 5)
        else:
            lines.append(f"🏁 {winner}")
        spy_name = next(
            (p["name"] for p in game["players"].values() if p.get("is_spy")),
            "未知",
        )
        lines.append(
            f"🔓 本局词对：平民「{game.get('civilian_word')}」/ "
            f"卧底「{game.get('spy_word')}」，卧底是 {spy_name}。"
        )
        sess = self._sessions.get(key)
        if sess:
            sess[KEY_SPY] = None
        self._release_spy_lock(key)
        return "\n".join(lines)

    def _spy_resolve(self, key: str, game: dict, now: float = None) -> str:
        """结算当前投票：票最多者出局；卧底出局平民胜，卧底存活至剩 2 人卧底胜"""
        now = now if now is not None else time.time()
        votes = game.get("votes") or {}
        alive = self._spy_alive_list(game)
        if not alive:
            return self._spy_finish(key, game, "所有玩家均已出局，游戏结束。")
        if votes:
            tally: dict[str, int] = {}
            for v in votes.values():
                tally[v] = tally.get(v, 0) + 1
            top = max(tally.values())
            top_ids = [pid for pid, c in tally.items() if c == top]
            # 平票时从最高票者中随机淘汰一人，保证游戏继续推进
            target = random.choice(top_ids) if len(top_ids) > 1 else top_ids[0]
            lines = [f"🗳️ 投票结果：最高 {top} 票。"]
        else:
            # 无人投票：随机淘汰一名存活玩家，保证游戏有进展
            target = random.choice([pid for pid, _ in alive])
            lines = ["🗳️ 本轮无人投票，随机淘汰一名玩家。"]
        game["players"][target]["alive"] = False
        lines.append(f"💀 {game['players'][target]['name']} 被淘汰出局！")
        # 胜负判定：先看卧底是否出局（平民胜），再看存活人数（卧底胜）
        alive_now = [p for p in game["players"].values() if p["alive"]]
        spy_alive = [p for p in alive_now if p.get("is_spy")]
        if not spy_alive:
            lines.append(self._spy_finish(key, game, "平民"))
            return "\n".join(lines)
        if len(alive_now) <= 2:
            lines.append(self._spy_finish(key, game, "卧底"))
            return "\n".join(lines)
        # 进入下一轮描述
        game["round"] += 1
        game["phase"] = "describing"
        game["phase_start"] = now
        game["described"] = set()
        game["votes"] = {}
        game["last_activity"] = now
        lines.append(
            f"🔁 卧底仍在场上！进入第 {game['round']} 轮描述，"
            f"存活 {len(alive_now)} 人，每人限描述 1 次（限时 "
            f"{game.get('describe_seconds', 60)} 秒）。"
        )
        return "\n".join(lines)

    def _spy_poll(self, key: str, game: dict, now: float = None) -> str:
        """惰性推进谁是卧底阶段；返回需要播报的文本（无阶段变化返回空串）"""
        now = now if now is not None else time.time()
        phase = game.get("phase")
        if phase == "describing":
            if now - game.get("phase_start", 0) > game.get("describe_seconds", 60):
                game["phase"] = "voting"
                game["phase_start"] = now
                game["votes"] = {}
                game["last_activity"] = now
                return "⏰ 描述时间到，进入投票阶段！\n" + self._spy_vote_prompt(game)
        elif phase == "voting":
            if now - game.get("phase_start", 0) > game.get("vote_seconds", 30):
                game["last_activity"] = now
                return "⏰ 投票时间到，开始结算！\n" + self._spy_resolve(key, game)
        return ""

    def spy_status(self, key: str) -> str:
        """查看当前谁是卧底局状态，返回提示文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SPY):
            return "⏰ 上一局谁是卧底已超时结束，发送「/卧底 加入」重新开局吧。"
        game = sess[KEY_SPY]
        if not game:
            if self._spy_owner and self._spy_owner != key:
                return "⚠️ 其他群正在进行谁是卧底（全局单局限制），请稍后再试。"
            return "⚠️ 当前没有进行中的谁是卧底。发送「/卧底 加入」参与（4-8 人开局）。"
        poll_text = self._spy_poll(key, game)
        if poll_text:
            return poll_text
        lines = [
            f"🕵️ 谁是卧底（第 {game['round']} 轮 · {self._spy_phase_name(game)}）"
        ]
        for i, (_, p) in enumerate(self._spy_alive_list(game), 1):
            lines.append(f"{i}. {p['name']}")
        lines.append(
            f"共 {len(self._spy_alive_list(game))} 名存活玩家，"
            "发送「/卧底 加入」加入、「/卧底 开始」开局、「/卧底 退出」退出。"
        )
        return "\n".join(lines)

    def do_spy_join(self, key: str, sender_id: str, sender_name: str) -> str:
        """加入谁是卧底（无局时创建并占用全局单局锁），返回提示文本"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SPY):
            return "⏰ 上一局谁是卧底已超时结束，请重新加入。"
        game = sess[KEY_SPY]
        if not game:
            # 全局单局锁检查：其他群有活跃卧底局则拒绝
            if self._spy_owner and self._spy_owner != key:
                other = self._sessions.get(self._spy_owner)
                if other and other.get(KEY_SPY):
                    return "⚠️ 全局单局限制：其他群正在进行谁是卧底，请稍后再试。"
                self._spy_owner = None  # 旧局已不存在，抢占锁
            game = {
                "phase": "joining",
                "players": {},
                "round": 1,
                "phase_start": time.time(),
                "describe_seconds": self.spy_describe_seconds,
                "vote_seconds": self.spy_vote_seconds,
                "seconds": 600,  # 整局无活动兜底超时；阶段推进由各自时限负责
                "last_activity": time.time(),
            }
            sess[KEY_SPY] = game
            self._spy_owner = key
        if game["phase"] != "joining":
            return "⚠️ 游戏已开始，不能中途加入。"
        if len(game["players"]) >= self.spy_max_players:
            return f"⚠️ 人数已满（上限 {self.spy_max_players} 人）。"
        if sender_id in game["players"]:
            return "⚠️ 你已经加入本局了。"
        game["players"][sender_id] = {"name": sender_name or "群友", "alive": True}
        game["last_activity"] = time.time()
        n = len(game["players"])
        return (
            f"✅ {sender_name or '群友'} 加入成功！当前 {n}/{self.spy_max_players} 人。\n"
            f"发送「/卧底 开始」开局（需 {self.spy_min_players}-"
            f"{self.spy_max_players} 人），「/卧底 退出」退出。"
        )

    def start_spy(self, key: str) -> str:
        """开始谁是卧底：发词、随机指定卧底、进入描述阶段"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SPY):
            return "⏰ 上一局谁是卧底已超时结束，请重新加入。"
        game = sess[KEY_SPY]
        if not game:
            return "⚠️ 当前没有进行中的谁是卧底，请先发送「/卧底 加入」。"
        if game["phase"] != "joining":
            return "⚠️ 游戏已开始，不能重复开局。"
        n = len(game["players"])
        if n < self.spy_min_players:
            return (
                f"⚠️ 人数不足：当前 {n} 人，至少需要 {self.spy_min_players} 人。"
                "请邀请更多群友「/卧底 加入」。"
            )
        civilian, spy_word = random.choice(SPY_WORDS)
        player_ids = list(game["players"].keys())
        spy_id = random.choice(player_ids)
        for pid in player_ids:
            is_spy = pid == spy_id
            game["players"][pid]["word"] = spy_word if is_spy else civilian
            game["players"][pid]["is_spy"] = is_spy
        game["civilian_word"] = civilian
        game["spy_word"] = spy_word
        game["round"] = 1
        game["phase"] = "describing"
        game["phase_start"] = time.time()
        game["described"] = set()
        game["votes"] = {}
        game["last_activity"] = time.time()
        return (
            f"🕵️ 谁是卧底开局！本局 {n} 人，其中 1 人是卧底。\n"
            f"🔑 本局词对：平民「{civilian}」/ 卧底「{spy_word}」"
            f"（卧底请假装平民词描述哦～）\n"
            f"💬 请存活玩家依次发送「/卧底 描述 <内容>」描述自己的词，"
            f"每人每轮限 1 次，限时 {self.spy_describe_seconds} 秒；"
            f"描述完毕后进入投票「/卧底 投票 <序号>」。"
        )

    def do_spy_desc(self, key: str, sender_id: str, sender_name: str, text: str) -> str:
        """卧底描述：每轮每人限 1 次；全部描述完毕后自动进入投票"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SPY):
            return "⏰ 谁是卧底已超时结束。"
        game = sess[KEY_SPY]
        if not game:
            return "⚠️ 当前没有进行中的谁是卧底。"
        poll_text = self._spy_poll(key, game)
        if poll_text:
            return poll_text
        if game["phase"] == "joining":
            return "⚠️ 游戏还未开始，请发送「/卧底 开始」。"
        if game["phase"] != "describing":
            return "⚠️ 当前是投票阶段，请发送「/卧底 投票 <序号>」。"
        player = game["players"].get(sender_id)
        if not player or not player.get("alive"):
            return "⚠️ 你已经出局，不能描述。"
        if sender_id in game["described"]:
            return "⚠️ 你本轮已经描述过了（每人每轮限 1 次）。"
        text = (text or "").strip()
        if not text:
            return "❓ 描述内容不能为空，格式：/卧底 描述 <内容>"
        game["described"].add(sender_id)
        game["last_activity"] = time.time()
        lines = [f"💬 {sender_name}：{text[:100]}"]  # 截断超长消息防刷屏
        alive_n = len(self._spy_alive_list(game))
        if len(game["described"]) >= alive_n:
            # 所有存活玩家均已描述：进入投票
            game["phase"] = "voting"
            game["phase_start"] = time.time()
            game["votes"] = {}
            lines.append(self._spy_vote_prompt(game))
        else:
            lines.append(
                f"⏳ 本轮还剩 {alive_n - len(game['described'])} 人未描述。"
            )
        return "\n".join(lines)

    def do_spy_vote(self, key: str, sender_id: str, idx_text: str) -> str:
        """卧底投票：每人 1 票；全部投完后立即结算淘汰"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SPY):
            return "⏰ 谁是卧底已超时结束。"
        game = sess[KEY_SPY]
        if not game:
            return "⚠️ 当前没有进行中的谁是卧底。"
        poll_text = self._spy_poll(key, game)
        if poll_text:
            return poll_text
        if game["phase"] == "joining":
            return "⚠️ 游戏还未开始。"
        if game["phase"] != "voting":
            return "⚠️ 当前是描述阶段，请发送「/卧底 描述 <内容>」。"
        player = game["players"].get(sender_id)
        if not player or not player.get("alive"):
            return "⚠️ 只有存活的玩家可以投票。"
        if sender_id in game["votes"]:
            return "⚠️ 你本轮已经投过票了（每人 1 票）。"
        idx = self._safe_int(idx_text, 0)
        alive = self._spy_alive_list(game)
        if idx < 1 or idx > len(alive):
            return (
                f"❌ 无效序号，请输入 1-{len(alive)}"
                "（发送「/卧底 状态」查看存活名单）。"
            )
        target_id = alive[idx - 1][0]
        if target_id == sender_id:
            return "❌ 不能投自己哦。"
        game["votes"][sender_id] = target_id
        game["last_activity"] = time.time()
        voted = len(game["votes"])
        total = len(alive)
        if voted >= total:
            # 全员投票完毕：立即结算
            return self._spy_resolve(key, game)
        return (
            f"🗳️ {player['name']} 投票成功（{voted}/{total}），"
            "等待其他人投票或超时自动结算。"
        )

    def do_spy_quit(self, key: str, sender_id: str) -> str:
        """退出谁是卧底；退出后存活人数不足时按规则结算"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SPY):
            return "⏰ 谁是卧底已超时结束。"
        game = sess[KEY_SPY]
        if not game:
            return "⚠️ 当前没有进行中的谁是卧底。"
        if sender_id not in game["players"]:
            return "⚠️ 你不在本局玩家中。"
        name = game["players"][sender_id]["name"]
        del game["players"][sender_id]
        game["last_activity"] = time.time()
        if game["phase"] == "joining":
            if not game["players"]:
                sess[KEY_SPY] = None
                self._release_spy_lock(key)
                return "🏁 所有玩家已退出，本局解散。"
            return f"✅ {name} 已退出。当前 {len(game['players'])} 人，仍可「/卧底 开始」。"
        # 游戏进行中：退出视同离场，检查胜负
        alive = self._spy_alive_list(game)
        spy_alive = [p for p in game["players"].values() if p.get("is_spy")]
        if not alive:
            return self._spy_finish(key, game, "所有玩家均已退出，游戏结束。")
        if not spy_alive:
            return f"✅ {name} 已退出。" + self._spy_finish(key, game, "平民")
        if len(alive) <= 2:
            return f"✅ {name} 已退出。" + self._spy_finish(key, game, "卧底")
        if game["phase"] == "voting":
            # 投票阶段有人退出：按当前已有票数立即结算
            return f"✅ {name} 已退出。" + self._spy_resolve(key, game)
        return f"✅ {name} 已退出，游戏继续。"

    def end_spy(self, key: str) -> str:
        """强制结束谁是卧底并揭晓答案"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_SPY):
            return "⏰ 谁是卧底已超时结束。"
        game = sess[KEY_SPY]
        if not game:
            return "⚠️ 当前没有进行中的谁是卧底。"
        return self._spy_finish(key, game, "本局由房主提前结束")

    # ==================== 猜成语（限时抢答 + 冷却防刷） ====================

    def start_idiom_quiz(self, key: str) -> str:
        """开始猜成语，返回提示文本"""
        sess = self._session(key)
        if sess[KEY_IDIOM_QUIZ] and not self._expired(sess[KEY_IDIOM_QUIZ]):
            return "⚠️ 已有进行中的猜成语，请先发送「/猜成语 放弃」结束当前题目。"
        quiz = random.choice(IDIOM_QUIZZES)
        sess[KEY_IDIOM_QUIZ] = {
            "quiz": quiz,
            "cooldown_until": 0.0,  # 答错后的冷却截止时间（防刷屏）
            "seconds": self.idiom_quiz_seconds,
            "last_activity": time.time(),
        }
        return (
            f"📖 猜成语开始！谜面：\n「{quiz['clue']}」\n"
            f"回复「/猜成语 <成语>」抢答（限时 {self.idiom_quiz_seconds} 秒，"
            "答对得 2 分），「/猜成语 放弃」揭晓答案。"
        )

    def do_idiom_quiz(self, key: str, sender_id: str, sender_name: str, text: str) -> str:
        """抢答猜成语：答错进入冷却防刷；答对得分并展示解释"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_IDIOM_QUIZ):
            return "⏰ 猜成语已超时结束，发送「/猜成语」重新开始吧。"
        game = sess[KEY_IDIOM_QUIZ]
        if not game:
            return "⚠️ 当前没有进行中的猜成语，发送「/猜成语」开始。"
        guess = re.sub(r"\s+", "", text or "")
        if not guess:
            return "❓ 请输入答案，格式：/猜成语 <成语>"
        now = time.time()
        if now < game.get("cooldown_until", 0):
            left = int(game["cooldown_until"] - now) + 1
            return f"⏳ 冷却中，请 {left} 秒后再试（防止刷屏）。"
        answer = game["quiz"]["answer"]
        if guess == answer:
            total = self._add_score(sender_id, sender_name, 2)
            sess[KEY_IDIOM_QUIZ] = None
            return (
                f"🎉 恭喜 {sender_name} 答对！答案是「{answer}」。\n"
                f"📚 解释：{game['quiz']['explain']}\n"
                f"🏆 {sender_name} 当前积分：{total}。"
            )
        # 答错：进入冷却防刷
        game["cooldown_until"] = now + self.idiom_quiz_cooldown
        game["last_activity"] = now
        return (
            f"❌ 不对哦，再想想～（{self.idiom_quiz_cooldown} 秒冷却防刷）"
        )

    def give_up_idiom_quiz(self, key: str) -> str:
        """放弃猜成语并揭晓答案"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_IDIOM_QUIZ):
            return "⏰ 猜成语已超时结束。"
        game = sess[KEY_IDIOM_QUIZ]
        if not game:
            return "⚠️ 当前没有进行中的猜成语。"
        answer = game["quiz"]["answer"]
        explain = game["quiz"]["explain"]
        sess[KEY_IDIOM_QUIZ] = None
        return f"🔓 答案揭晓：「{answer}」\n📚 {explain}，下次加油！"

    # ==================== 24 点（安全表达式校验器） ====================

    _24_TOKEN_OPS = {"+", "-", "*", "/", "(", ")"}

    @staticmethod
    def _try_24_op(a: Fraction, b: Fraction, op: str):
        """24 点求解辅助：单步四则运算，除零返回 None"""
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b if b != 0 else None
        return None

    @classmethod
    def _cards_solvable(cls, cards: list[int]) -> bool:
        """判断 4 张牌能否通过 + - * / 算出 24。

        枚举全部数字排列 × 运算符组合 × 5 种括号结构，用 Fraction 精确计算。
        """
        for a, b, c, d in permutations(cards):
            # 先转 Fraction，避免 int/int 的浮点误差导致精确性判断失误
            a, b, c, d = Fraction(a), Fraction(b), Fraction(c), Fraction(d)
            for o1, o2, o3 in product("+-*/", repeat=3):
                r_ab = cls._try_24_op(a, b, o1)
                r_bc = cls._try_24_op(b, c, o2)
                r_cd = cls._try_24_op(c, d, o3)
                # ((a∘b)∘c)∘d
                if r_ab is not None:
                    r = cls._try_24_op(r_ab, c, o2)
                    if r is not None and cls._try_24_op(r, d, o3) == 24:
                        return True
                # (a∘(b∘c))∘d
                if r_bc is not None:
                    r = cls._try_24_op(a, r_bc, o1)
                    if r is not None and cls._try_24_op(r, d, o3) == 24:
                        return True
                # a∘((b∘c)∘d)
                if r_bc is not None:
                    r = cls._try_24_op(r_bc, d, o3)
                    if r is not None and cls._try_24_op(a, r, o1) == 24:
                        return True
                # a∘(b∘(c∘d))
                if r_cd is not None:
                    r = cls._try_24_op(b, r_cd, o2)
                    if r is not None and cls._try_24_op(a, r, o1) == 24:
                        return True
                # (a∘b)∘(c∘d)
                if r_ab is not None and r_cd is not None:
                    if cls._try_24_op(r_ab, r_cd, o2) == 24:
                        return True
        return False

    @classmethod
    def _safe_eval_24(cls, node) -> Fraction:
        """仅允许「整数常量 + - * / 二元运算」的安全求值器（绝不执行任意代码）"""
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, int):
                raise ValueError("仅允许整数")
            return Fraction(node.value)
        if isinstance(node, ast.BinOp):
            opname = type(node.op).__name__
            if opname not in ("Add", "Sub", "Mult", "Div"):
                raise ValueError(f"非法运算符：{opname}")
            left = cls._safe_eval_24(node.left)
            right = cls._safe_eval_24(node.right)
            if opname == "Add":
                return left + right
            if opname == "Sub":
                return left - right
            if opname == "Mult":
                return left * right
            if right == 0:
                raise ZeroDivisionError("除数不能为 0")
            return left / right
        raise ValueError("仅支持四则运算与括号")

    @classmethod
    def _validate_24_expr(cls, expr: str, cards: list[int]) -> tuple:
        """严格校验 24 点算式，返回 (是否合法, 说明文本)。

        规则：仅允许 + - * / 与括号；数字必须恰好为给定的 4 张牌
        （每个数字的使用次数与牌面一致）；tokenize 词法白名单 + AST
        白名单双重防线，杜绝幂运算/函数调用/属性访问等注入；
        Fraction 精确求值（无浮点误差），结果必须精确等于 24。
        """
        text = (expr or "").strip()
        if not text:
            return False, "算式为空"
        # 第一道防线：tokenize 词法白名单
        used: list[int] = []
        try:
            tokens = tokenize.generate_tokens(io.StringIO(text).readline)
            for tok in tokens:
                if tok.type in (
                    tokenize.ENDMARKER,
                    tokenize.NL,
                    tokenize.NEWLINE,
                    tokenize.INDENT,
                    tokenize.DEDENT,
                ):
                    continue
                if tok.type == tokenize.NUMBER:
                    # 仅接受十进制整数（拒绝 1.5 / 1e3 / 0x10 / 1_000 等）
                    if re.fullmatch(r"\d+", tok.string) is None:
                        return False, f"非法数字字面量：{tok.string}"
                    used.append(int(tok.string))
                elif tok.type == tokenize.OP:
                    if tok.string not in cls._24_TOKEN_OPS:
                        return False, f"非法运算符：{tok.string}"
                else:
                    return False, f"非法内容：{tok.string}"
        except (tokenize.TokenError, IndentationError) as e:
            return False, f"表达式无法解析：{e}"
        # 数字必须恰好等于给定的 4 张牌（多重集合一致）
        if sorted(used) != sorted(cards):
            return False, "数字必须恰好使用给定的 4 张牌（每个数字只能使用对应次数）"
        # 第二道防线：AST 白名单 + Fraction 精确求值
        try:
            tree = ast.parse(text, mode="eval")
            value = cls._safe_eval_24(tree.body)
        except (SyntaxError, ValueError, ZeroDivisionError) as e:
            return False, f"表达式不合法：{e}"
        if value == 24:
            return True, "正确！"
        return False, f"计算结果为 {value}，不等于 24"

    @staticmethod
    def _deal_24_cards() -> list[int]:
        """随机发 4 张 1-13 的牌，重试直到确认有解（上限 50 次兜底）"""
        for _ in range(50):
            cards = sorted(random.choices(range(1, 14), k=4))
            if GroupGamesPlugin._cards_solvable(cards):
                return cards
        return sorted(random.choices(range(1, 14), k=4))

    def start_24(self, key: str) -> str:
        """开始 24 点：随机发 4 张有解的牌，返回提示文本"""
        sess = self._session(key)
        if sess[KEY_24] and not self._expired(sess[KEY_24]):
            return "⚠️ 已有进行中的 24 点，请先发送「/24点 放弃」结束当前一局。"
        cards = self._deal_24_cards()
        sess[KEY_24] = {
            "cards": cards,
            "cooldown": {},  # sender_id -> 上次提交时间（防刷）
            "seconds": self.game24_seconds,
            "last_activity": time.time(),
        }
        return (
            f"🔢 24 点挑战开始！牌面：{' '.join(map(str, cards))}\n"
            f"发送「/24点 <算式>」提交（仅 + - * / 与括号，恰好使用 4 张牌），"
            f"限时 {self.game24_seconds} 秒，答对得 3 分。"
        )

    def do_24(self, key: str, sender_id: str, sender_name: str, text: str) -> str:
        """提交 24 点算式：防刷冷却 + 严格校验 + 精确求值"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_24):
            return "⏰ 24 点已超时结束，发送「/24点」重新开始吧。"
        game = sess[KEY_24]
        if not game:
            return "⚠️ 当前没有进行中的 24 点，发送「/24点」开始。"
        now = time.time()
        last = game["cooldown"].get(sender_id, 0)
        if now - last < self.game24_cooldown:
            left = int(self.game24_cooldown - (now - last)) + 1
            return f"⏳ 提交太频繁，请 {left} 秒后再试。"
        ok, msg = self._validate_24_expr(text, game["cards"])
        game["cooldown"][sender_id] = now
        if not ok:
            game["last_activity"] = now
            return f"❌ {msg}"
        # 校验通过且结果精确等于 24：得分并结束
        total = self._add_score(sender_id, sender_name, 3)
        sess[KEY_24] = None
        return (
            f"🎉 恭喜 {sender_name} 算出 24！算式：{text.strip()}\n"
            f"🏆 {sender_name} 当前积分：{total}。"
        )

    def give_up_24(self, key: str) -> str:
        """放弃 24 点并揭晓本局牌面"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_24):
            return "⏰ 24 点已超时结束。"
        game = sess[KEY_24]
        if not game:
            return "⚠️ 当前没有进行中的 24 点。"
        cards = game["cards"]
        sess[KEY_24] = None
        return f"🔓 本局牌面：{' '.join(map(str, cards))}，下次加油！"

    # ==================== 猜价格（高低提示 + 冷却防刷） ====================

    def start_price(self, key: str) -> str:
        """开始猜价格：随机抽取商品，返回提示文本"""
        sess = self._session(key)
        if sess[KEY_PRICE] and not self._expired(sess[KEY_PRICE]):
            return "⚠️ 已有进行中的猜价格，请先发送「/猜价格 放弃」结束当前一局。"
        item = random.choice(PRICE_ITEMS)
        sess[KEY_PRICE] = {
            "item": item,
            "last_guess": {},  # sender_id -> 上次猜测时间（防刷）
            "seconds": self.price_seconds,
            "last_activity": time.time(),
        }
        return (
            f"💰 猜价格开始！请猜这件商品的价格：\n「{item['name']}」\n"
            f"发送「/猜价格 <数字>」猜价（会提示高了/低了），"
            f"限时 {self.price_seconds} 秒，猜中得 2 分。"
        )

    def do_price(self, key: str, sender_id: str, sender_name: str, text: str) -> str:
        """猜价格：每人 3 秒冷却防刷；高了/低了提示；猜中得分"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_PRICE):
            return "⏰ 猜价格已超时结束，发送「/猜价格」重新开始吧。"
        game = sess[KEY_PRICE]
        if not game:
            return "⚠️ 当前没有进行中的猜价格，发送「/猜价格」开始。"
        now = time.time()
        last = game["last_guess"].get(sender_id, 0)
        if now - last < self.price_cooldown:
            left = int(self.price_cooldown - (now - last)) + 1
            return f"⏳ 猜得太快啦，请 {left} 秒后再猜。"
        guess = self._safe_int(text, 0)
        if guess <= 0:
            return "❓ 请输入正整数价格，格式：/猜价格 <数字>"
        game["last_guess"][sender_id] = now
        game["last_activity"] = now
        price = game["item"]["price"]
        if guess == price:
            total = self._add_score(sender_id, sender_name, 2)
            name = game["item"]["name"]
            sess[KEY_PRICE] = None
            return (
                f"🎉 恭喜 {sender_name} 猜中！「{name}」的价格正是 {price} 元！\n"
                f"🏆 {sender_name} 当前积分：{total}。"
            )
        diff = abs(guess - price)
        hint = "低了" if guess < price else "高了"
        if diff <= 10:
            hint += "（很接近了！）"
        return f"{hint}！继续猜～"

    def give_up_price(self, key: str) -> str:
        """放弃猜价格并揭晓答案"""
        sess = self._session(key)
        if self._lazy_expire(key, KEY_PRICE):
            return "⏰ 猜价格已超时结束。"
        game = sess[KEY_PRICE]
        if not game:
            return "⚠️ 当前没有进行中的猜价格。"
        item = game["item"]
        sess[KEY_PRICE] = None
        return (
            f"🔓 答案揭晓：「{item['name']}」的价格是 {item['price']} 元，下次加油！"
        )

    # ==================== 积分排行榜 ====================

    def show_scores(self) -> str:
        """展示积分排行榜 Top 10"""
        if not self._scores:
            return "🏆 积分榜空空如也，快来参与小游戏赚积分吧！"
        top = sorted(
            self._scores.items(),
            key=lambda kv: kv[1].get("points", 0),
            reverse=True,
        )[:10]
        lines = ["🏆 积分排行榜 Top 10："]
        for i, (_, entry) in enumerate(top, 1):
            name = entry.get("name") or "群友"
            lines.append(f"{i}. {name}：{entry.get('points', 0)} 分")
        return "\n".join(lines)

    # ==================== 超时清扫 ====================

    def _sweep_expired(self, now: float = None) -> int:
        """清理所有超时游戏，返回清理的游戏数量；会话清空后一并删除"""
        now = now if now is not None else time.time()
        cleaned = 0
        for key in list(self._sessions):
            sess = self._sessions[key]
            for gkey in _GAME_KEYS:
                game = sess.get(gkey)
                if game is not None and self._expired(game, now=now):
                    sess[gkey] = None
                    if gkey == KEY_SPY:
                        self._release_spy_lock(key)
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
        self.initialize()

    def initialize(self):
        """插件热重载后启动后台清扫任务（on_astrbot_loaded 热重载不触发；幂等）"""
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

    @filter.command("卧底", priority=200)
    async def cmd_spy(self, event: AstrMessageEvent):
        """谁是卧底：加入 / 开始 / 描述 / 投票 / 退出 / 结束"""
        key = self._key_of(event)
        rest = self._rest_of(event, "卧底")
        sid, sname = self._sender_id(event), self._sender_name(event)
        if not rest or rest == "状态":
            return self._reply(event, self.spy_status(key))
        if rest == "加入":
            return self._reply(event, self.do_spy_join(key, sid, sname))
        if rest == "开始":
            return self._reply(event, self.start_spy(key))
        if rest == "退出":
            return self._reply(event, self.do_spy_quit(key, sid))
        if rest == "结束":
            return self._reply(event, self.end_spy(key))
        m = re.match(r"^(描述|投票)\s*(.*)$", rest)
        if m:
            act, arg = m.group(1), m.group(2).strip()
            if act == "描述":
                return self._reply(event, self.do_spy_desc(key, sid, sname, arg))
            return self._reply(event, self.do_spy_vote(key, sid, arg))
        return self._reply(event, self.spy_status(key))

    @filter.command("猜成语", priority=200)
    async def cmd_idiom_quiz(self, event: AstrMessageEvent):
        """猜成语：开始 / 抢答 / 放弃"""
        key = self._key_of(event)
        rest = self._rest_of(event, "猜成语")
        if not rest:
            return self._reply(event, self.start_idiom_quiz(key))
        if rest == "放弃":
            return self._reply(event, self.give_up_idiom_quiz(key))
        return self._reply(
            event,
            self.do_idiom_quiz(
                key, self._sender_id(event), self._sender_name(event), rest
            ),
        )

    @filter.command("24点", priority=200)
    async def cmd_24(self, event: AstrMessageEvent):
        """24 点：开始 / 提交算式 / 放弃"""
        key = self._key_of(event)
        rest = self._rest_of(event, "24点")
        if not rest:
            return self._reply(event, self.start_24(key))
        if rest == "放弃":
            return self._reply(event, self.give_up_24(key))
        return self._reply(
            event,
            self.do_24(key, self._sender_id(event), self._sender_name(event), rest),
        )

    @filter.command("猜价格", priority=200)
    async def cmd_price(self, event: AstrMessageEvent):
        """猜价格：开始 / 猜价 / 放弃"""
        key = self._key_of(event)
        rest = self._rest_of(event, "猜价格")
        if not rest:
            return self._reply(event, self.start_price(key))
        if rest == "放弃":
            return self._reply(event, self.give_up_price(key))
        return self._reply(
            event,
            self.do_price(
                key, self._sender_id(event), self._sender_name(event), rest
            ),
        )

    @filter.command("积分", priority=200)
    async def cmd_scores(self, event: AstrMessageEvent):
        """查看积分排行榜"""
        return self._reply(event, self.show_scores())
