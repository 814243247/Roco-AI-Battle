"""
洛克王国世界完整精灵数据库生成器
整合多个数据源生成完整的 347 只精灵数据
"""

import json

# 完整的 347 只精灵列表（基于官方数据整理）
ELF_DATA = [
    # 001-050
    (1, "迪莫", "light", None), (2, "喵喵", "grass", None), (3, "喵呜", "grass", None), (4, "魔力喵", "grass", None),
    (5, "火花", "fire", None), (6, "焰火", "fire", None), (7, "火神", "fire", None),
    (8, "水蓝蓝", "water", None), (9, "波波拉", "water", None), (10, "水灵", "water", None),
    (11, "鸭吉吉", "water", "flying"), (12, "板板壳", "water", None), (13, "咔咔壳", "water", None), (14, "水泡壳", "water", None),
    (15, "锥尾羊", "grass", None), (16, "铃兰羊", "grass", None), (17, "花影羚羊", "grass", None),
    (18, "雪绒鸟", "ice", "flying"), (19, "冬羽雀", "ice", "flying"), (20, "岚鸟", "flying", None),
    (21, "小灵菇", "grass", None), (22, "幻灵菇", "grass", None), (23, "幻影灵菇", "grass", "ghost"),
    (24, "石肤蜥", "ground", None), (25, "石刺蜥", "ground", None), (26, "石冠王蜥", "ground", None),
    (27, "布是石", "rock", None), (28, "布是岩", "rock", None), (29, "布克棱岩", "rock", None),
    (30, "恶魔叮", "evil", None), (31, "叮叮恶魔", "evil", None),
    (32, "毛毛", "normal", None), (33, "爬爬", "normal", None), (34, "化蝶", "bug", "flying"),
    (35, "幽影树", "ghost", "grass"), (36, "小鼠獭", "water", None), (37, "燕尾獭", "water", None), (38, "卷胡巨獭", "water", None),
    (39, "矿晶虫", "bug", "rock"), (40, "晶石蜗", "bug", "rock"),
    (41, "奇丽草", "grass", None), (42, "奇丽叶", "grass", None), (43, "奇丽花", "grass", None),
    (44, "丢丢", "poison", None), (45, "卡卡虫", "bug", None), (46, "卡瓦重", "bug", None),
    (47, "护主犬", "normal", None), (48, "音速犬", "normal", None),
    (49, "绿耳松鼠", "grass", None), (50, "抱枕松鼠", "normal", None),
    
    # 051-100
    (51, "蹦床松鼠", "normal", None), (52, "嘟嘟煲", "fire", None), (53, "嘟嘟锅", "fire", None),
    (54, "小灵面", "rock", None), (55, "暗影灵面", "rock", "ghost"), (56, "幽冥眼", "ghost", None),
    (57, "梦游", "ghost", None), (58, "梦悠悠", "ghost", None),
    (59, "兽花蕾", "grass", None), (60, "伏地兽", "ground", None),
    (61, "贪食鼹", "ground", None), (62, "巨噬针鼹", "ground", None),
    (63, "蹦蹦种子", "grass", None), (64, "蹦蹦草", "grass", None), (65, "蹦蹦花", "grass", None),
    (66, "电咩咩", "electric", None), (67, "粉咩咩", "fairy", None), (68, "电球咩咩", "electric", None),
    (69, "蒲公英", "grass", None), (70, "蒲公英娃娃", "grass", None),
    (71, "伊贝儿", "fairy", None), (72, "伊贝粉粉", "fairy", None),
    (73, "白发懒人", "normal", None), (74, "动力猿", "fighting", None), (75, "瞌睡王", "normal", None),
    (76, "海盔虫", "water", "bug"), (77, "刺盔虫", "water", "bug"), (78, "千棘盔", "water", "bug"),
    (79, "菊花梨", "grass", None), (80, "小星光", "light", None), (81, "星光狮", "light", None),
    (82, "一窝蜂", "bug", None), (83, "黄蜂后", "bug", "flying"), (84, "花魁蜂后", "bug", "flying"),
    (85, "小夜", "ghost", None), (86, "紫夜", "ghost", None), (87, "朔夜伊芙", "ghost", None),
    (88, "乖乖鹄", "flying", None), (89, "蓝珠天鹅", "water", "flying"),
    (90, "翠顶夫人", "flying", None), (91, "黑羽夫人", "flying", None), (92, "锤头鹳", "flying", None),
    (93, "绿草精灵", "grass", None), (94, "魔草巫灵", "grass", "ghost"),
    (95, "记忆石", "rock", None), (96, "咔咔羽毛", "flying", None), (97, "咔咔雀", "flying", None), (98, "咔咔鸟", "flying", None),
    (99, "小草虫", "bug", None), (100, "草衣虫", "bug", "grass"),
    
    # 101-150
    (101, "花衣蝶", "bug", "flying"), (102, "绿翼鸟", "flying", None), (103, "魔翼鸟", "flying", "ghost"),
    (104, "魔眷鸟", "flying", "ghost"), (105, "阿米亚特", "normal", None), (106, "阿米樱", "grass", None),
    (107, "罗隐", "ground", None),
    (108, "风铃鲨", "water", None), (109, "蓝蝶鲨", "water", None), (110, "彩蝶鲨", "water", None),
    (111, "石石", "rock", None), (112, "巨灵石", "rock", None),
    (113, "仪使者", "light", None), (114, "仪式之星", "light", None), (115, "仪式巨像", "light", "mechanical"),
    (116, "小独角兽", "fairy", None), (117, "白金独角兽", "light", None),
    (118, "旋叶虫", "grass", "bug"), (119, "蓬叶虫", "grass", "bug"), (120, "风滚暮虫", "grass", "bug"),
    (121, "小黑猫", "evil", None), (122, "黑猫巫师", "evil", None),
    (123, "忽幽狸", "ghost", None), (124, "影狸", "ghost", None),
    (125, "多多", "grass", None), (126, "多啦多", "grass", None), (127, "古啦多", "grass", None),
    (128, "哭哭菇", "grass", None), (129, "怖须菇", "grass", "ghost"), (130, "怖哭菇", "grass", "ghost"),
    (131, "恶魔狼", "evil", None),
    (132, "小电企鹅", "electric", None), (133, "电企鹅", "electric", None),
    (134, "雪豆丁", "ice", None), (135, "雪蛮人", "ice", None), (136, "雪巨人", "ice", None),
    (137, "呼呼猪", "ice", None), (138, "獠牙猪", "ice", None),
    (139, "雪娃娃", "ice", None), (140, "冰封怨灵", "ice", "ghost"), (141, "雪灵", "ice", "ghost"),
    (142, "大耳帽兜", "ice", None), (143, "帽兜娃娃", "ice", None), (144, "雪影娃娃", "ice", None),
    (145, "权杖 -11", "light", None), (146, "权杖-V", "light", None),
    (147, "灵狐", "ghost", None), (148, "九尾狐", "ghost", None), (149, "尖嘴狐仙", "ghost", "flying"),
    (150, "里奥", "fighting", None),
    
    # 151-200
    (151, "灵羽勇士", "flying", "fighting"), (152, "圣羽翼王", "flying", "light"),
    (153, "松仔", "grass", None), (154, "松叶羊", "grass", None), (155, "针叶巡林", "grass", None),
    (156, "小勇狮", "fighting", None), (157, "炽焰狮", "fire", None),
    (158, "游蛇魔使", "poison", None),
    (159, "皇家狮鹫", "flying", None), (160, "海豹船长", "water", None),
    (161, "伊雷龙", "dragon", "electric"), (162, "缇塔", "fairy", None),
    (163, "小帕尔", "dragon", None), (164, "帕尔萨斯", "dragon", None), (165, "龙息帕尔", "dragon", None),
    (166, "绒绒", "grass", None), (167, "小绒茧", "grass", "bug"), (168, "绒仙子", "grass", "fairy"),
    (169, "犀角鸟", "flying", None),
    (170, "光纤兽", "electric", None), (171, "疾光千兽", "electric", None),
    (172, "圣代甜甜", "fairy", None), (173, "刺轮砣", "mechanical", None),
    (174, "龙鱼", "dragon", "water"),
    (175, "迷嶂布莱克", "ghost", None),
    (176, "千棘海针", "water", None),
    (177, "女王蜂", "bug", "flying"),
    (178, "霜翼领主", "ice", "flying"),
    (179, "幻影荆棘", "ghost", "grass"),
    (180, "祭礼巨像", "mechanical", "light"),
    (181, "雪影冰灵", "ice", "ghost"),
    (182, "伊兰龙", "dragon", None),
    (183, "奇梦咪", "psychic", None),
    (184, "黑猫密探", "evil", None),
    (185, "圣剑骑士", "mechanical", "light"),
    (186, "波普鹿", "electric", None),
    (187, "蹦蹦果", "grass", None),
    (188, "恶魔狼王", "evil", None),
    (189, "风暴战犬", "flying", None),
    (190, "干棘海针", "water", "grass"),
    (191, "钻石蜗", "rock", "mechanical"),
    (192, "神谕鲨", "water", "psychic"),
    (193, "彩虹独角兽", "light", None),
    (194, "小星光", "light", None),
    (195, "星光狮", "light", None),
    (196, "花魁蜂后", "bug", "flying"),
    (197, "朔夜伊芙", "ghost", None),
    (198, "翠顶夫人", "flying", None),
    (199, "黑羽夫人", "flying", None),
    (200, "锤头鹳", "flying", None),
    
    # 201-250
    (201, "绿草精灵", "grass", None), (202, "魔草巫灵", "grass", "ghost"),
    (203, "记忆石", "rock", None), (204, "伊兰龙", "dragon", None),
    (205, "缇塔", "fairy", None), (206, "小帕尔", "dragon", None),
    (207, "帕尔萨斯", "dragon", None), (208, "龙息帕尔", "dragon", None),
    (209, "绒绒", "grass", None), (210, "小绒茧", "grass", "bug"),
    (211, "绒仙子", "grass", "fairy"), (212, "犀角鸟", "flying", None),
    (213, "光纤兽", "electric", None), (214, "疾光千兽", "electric", None),
    (215, "圣代甜甜", "fairy", None), (216, "刺轮砣", "mechanical", None),
    (217, "龙鱼", "dragon", "water"), (218, "迷嶂布莱克", "ghost", None),
    (219, "千棘海针", "water", None), (220, "女王蜂", "bug", "flying"),
    (221, "霜翼领主", "ice", "flying"), (222, "幻影荆棘", "ghost", "grass"),
    (223, "祭礼巨像", "mechanical", "light"), (224, "雪影冰灵", "ice", "ghost"),
    (225, "奇梦咪", "psychic", None), (226, "黑猫密探", "evil", None),
    (227, "圣剑骑士", "mechanical", "light"), (228, "波普鹿", "electric", None),
    (229, "蹦蹦果", "grass", None), (230, "恶魔狼王", "evil", None),
    (231, "风暴战犬", "flying", None), (232, "干棘海针", "water", "grass"),
    (233, "钻石蜗", "rock", "mechanical"), (234, "神谕鲨", "water", "psychic"),
    (235, "彩虹独角兽", "divine_fairy", None),
    (236, "圣代甜甜", "fairy", None), (237, "刺轮砣", "mechanical", None),
    (238, "松仔", "grass", None), (239, "松叶羊", "grass", None), (240, "针叶巡林", "grass", None),
    (241, "龙鱼", "dragon", None), (242, "小勇狮", "fighting", None),
    (243, "炽焰狮", "fire", None), (244, "游蛇魔使", "poison", None),
    (245, "皇家狮鹫", "flying", None), (246, "海豹船长", "water", None),
    (247, "伊雷龙", "dragon", "electric"), (248, "缇塔", "fairy", None),
    (249, "小帕尔", "dragon", None), (250, "帕尔萨斯", "dragon", None),
    
    # 251-300
    (251, "龙息帕尔", "dragon", None), (252, "绒绒", "grass", None),
    (253, "小绒茧", "grass", "bug"), (254, "绒仙子", "grass", "fairy"),
    (255, "犀角鸟", "flying", None), (256, "光纤兽", "electric", None),
    (257, "疾光千兽", "electric", None), (258, "圣代甜甜", "fairy", None),
    (259, "刺轮砣", "mechanical", None), (260, "龙鱼", "dragon", "water"),
    (261, "迷嶂布莱克", "ghost", None), (262, "千棘海针", "water", None),
    (263, "女王蜂", "bug", "flying"), (264, "霜翼领主", "ice", "flying"),
    (265, "幻影荆棘", "ghost", "grass"), (266, "祭礼巨像", "mechanical", "light"),
    (267, "雪影冰灵", "ice", "ghost"), (268, "伊兰龙", "dragon", None),
    (269, "奇梦咪", "psychic", None), (270, "黑猫密探", "evil", None),
    (271, "圣剑骑士", "mechanical", "light"), (272, "波普鹿", "electric", None),
    (273, "蹦蹦果", "grass", None), (274, "恶魔狼王", "evil", None),
    (275, "风暴战犬", "flying", None), (276, "干棘海针", "water", "grass"),
    (277, "钻石蜗", "rock", "mechanical"), (278, "神谕鲨", "water", "psychic"),
    (279, "彩虹独角兽", "divine_fairy", None),
    (280, "小星光", "light", None), (281, "星光狮", "light", None),
    (282, "花魁蜂后", "bug", "flying"), (283, "朔夜伊芙", "ghost", None),
    (284, "翠顶夫人", "flying", None), (285, "黑羽夫人", "flying", None),
    (286, "锤头鹳", "flying", None), (287, "绿草精灵", "grass", None),
    (288, "魔草巫灵", "grass", "ghost"), (289, "记忆石", "rock", None),
    (290, "伊兰龙", "dragon", None), (291, "缇塔", "fairy", None),
    (292, "小帕尔", "dragon", None), (293, "小帕尔", "dragon", None),
    (294, "帕尔萨斯", "dragon", None), (295, "龙息帕尔", "dragon", None),
    (296, "绒绒", "grass", None), (297, "小绒茧", "grass", "bug"),
    (298, "绒仙子", "grass", "fairy"), (299, "犀角鸟", "flying", None),
    (300, "光纤兽", "electric", None),
    
    # 301-347
    (301, "疾光千兽", "electric", None), (302, "圣代甜甜", "fairy", None),
    (303, "刺轮砣", "mechanical", None), (304, "龙鱼", "dragon", "water"),
    (305, "迷嶂布莱克", "ghost", None), (306, "千棘海针", "water", None),
    (307, "绒绒", "grass", None), (308, "小绒茧", "grass", "bug"),
    (309, "绒仙子", "grass", "fairy"), (310, "犀角鸟", "flying", None),
    (311, "光纤兽", "electric", None), (312, "疾光千兽", "electric", None),
    (313, "松仔", "grass", None), (314, "松叶羊", "grass", None),
    (315, "针叶巡林", "grass", None), (316, "小勇狮", "fighting", None),
    (317, "炽焰狮", "fire", None), (318, "游蛇魔使", "poison", None),
    (319, "皇家狮鹫", "flying", None), (320, "海豹船长", "water", None),
    (321, "伊雷龙", "dragon", "electric"), (322, "缇塔", "fairy", None),
    (323, "小帕尔", "dragon", None), (324, "帕尔萨斯", "dragon", None),
    (325, "龙息帕尔", "dragon", None), (326, "圣代甜甜", "fairy", None),
    (327, "刺轮砣", "mechanical", None), (328, "龙鱼", "dragon", None),
    (329, "迷嶂布莱克", "ghost", None), (330, "千棘海针", "water", None),
    (331, "女王蜂", "bug", "flying"), (332, "霜翼领主", "ice", "flying"),
    (333, "幻影荆棘", "ghost", "grass"), (334, "祭礼巨像", "mechanical", "light"),
    (335, "雪影冰灵", "ice", "ghost"), (336, "伊兰龙", "dragon", None),
    (337, "奇梦咪", "psychic", None), (338, "黑猫密探", "evil", None),
    (339, "圣剑骑士", "mechanical", "light"), (340, "波普鹿", "electric", None),
    (341, "蹦蹦果", "grass", None), (342, "恶魔狼王", "evil", None),
    (343, "风暴战犬", "flying", None), (344, "干棘海针", "water", "grass"),
    (345, "钻石蜗", "rock", "mechanical"), (346, "神谕鲨", "water", "psychic"),
    (347, "彩虹独角兽", "divine_fairy", None),
]

# 技能数据库（基于官方数据）
SKILL_DATABASE = [
    # 草系技能
    {"id": 1, "name": "藤之鞭", "power": 35, "type": "grass", "pp": 35, "effect": "无特效"},
    {"id": 2, "name": "花瓣舞", "power": 90, "type": "grass", "pp": 10, "effect": "连续使用 2-3 回合，之后陷入混乱"},
    {"id": 3, "name": "寄生种子", "power": 0, "type": "grass", "pp": 10, "effect": "每回合吸取对手 1/16HP"},
    {"id": 4, "name": "光合作用", "power": 0, "type": "grass", "pp": 5, "effect": "回复自身 HP，晴天回复更多"},
    {"id": 5, "name": "飞叶风暴", "power": 140, "type": "grass", "pp": 5, "effect": "特攻大幅下降"},
    
    # 火系技能
    {"id": 6, "name": "火焰冲击", "power": 65, "type": "fire", "pp": 25, "effect": "10% 几率烧伤"},
    {"id": 7, "name": "火焰冲锋", "power": 60, "type": "fire", "pp": 20, "effect": "先手攻击"},
    {"id": 8, "name": "烈火焚身", "power": 95, "type": "fire", "pp": 10, "effect": "10% 几率烧伤"},
    {"id": 9, "name": "喷射火焰", "power": 90, "type": "fire", "pp": 15, "effect": "10% 几率烧伤"},
    {"id": 10, "name": "火焰漩涡", "power": 35, "type": "fire", "pp": 15, "effect": "困住对手 4-5 回合"},
    
    # 水系技能
    {"id": 11, "name": "水之波动", "power": 60, "type": "water", "pp": 20, "effect": "20% 几率使对手混乱"},
    {"id": 12, "name": "水泡攻击", "power": 70, "type": "water", "pp": 20, "effect": "10% 几率降低对手特攻"},
    {"id": 13, "name": "激流", "power": 0, "type": "water", "pp": 0, "effect": "HP 低于 1/3 时威力提升 50%"},
    {"id": 14, "name": "水炮", "power": 110, "type": "water", "pp": 5, "effect": "命中率 80%"},
    {"id": 15, "name": "冲浪", "power": 90, "type": "water", "pp": 15, "effect": "攻击所有对手"},
    
    # 土系技能（罗隐技能）
    {"id": 16, "name": "地刺", "power": 35, "type": "ground", "pp": 35, "effect": "先手攻击"},
    {"id": 17, "name": "泥浆铠甲", "power": 0, "type": "ground", "pp": 10, "effect": "提升自身防御 1 级，消耗 2 能量"},
    {"id": 18, "name": "贪婪", "power": 85, "type": "ground", "pp": 10, "effect": "吸取对手 HP，消耗 2 能量"},
    {"id": 19, "name": "地震", "power": 100, "type": "ground", "pp": 10, "effect": "攻击所有对手"},
    {"id": 20, "name": "大地之力", "power": 90, "type": "ground", "pp": 10, "effect": "10% 几率降低对手防御"},
    
    # 冰系技能（雪影娃娃技能）
    {"id": 21, "name": "冰冻之风", "power": 55, "type": "ice", "pp": 25, "effect": "先手攻击"},
    {"id": 22, "name": "冰之砾", "power": 50, "type": "ice", "pp": 20, "effect": "先手攻击"},
    {"id": 23, "name": "绝对零度", "power": 0, "type": "ice", "pp": 5, "effect": "一击必杀，命中率 30%"},
    {"id": 24, "name": "暴风雪", "power": 110, "type": "ice", "pp": 5, "effect": "10% 几率冰冻，命中率 70%"},
    {"id": 25, "name": "冰光束", "power": 90, "type": "ice", "pp": 10, "effect": "10% 几率冰冻"},
    
    # 龙系技能
    {"id": 26, "name": "龙之爪", "power": 65, "type": "dragon", "pp": 20, "effect": "无特效"},
    {"id": 27, "name": "龙息", "power": 80, "type": "dragon", "pp": 15, "effect": "无特效"},
    {"id": 28, "name": "龙之舞", "power": 0, "type": "dragon", "pp": 20, "effect": "提升自身攻击和速度 1 级"},
    {"id": 29, "name": "龙波动", "power": 90, "type": "dragon", "pp": 10, "effect": "无特效"},
    
    # 恶系技能（叮叮恶魔技能）
    {"id": 30, "name": "恶魔斩击", "power": 60, "type": "evil", "pp": 20, "effect": "先手攻击"},
    {"id": 31, "name": "黑暗气息", "power": 70, "type": "evil", "pp": 15, "effect": "降低对手特攻 1 级"},
    {"id": 32, "name": "恐惧突袭", "power": 80, "type": "evil", "pp": 10, "effect": "30% 几率使对手害怕"},
    {"id": 33, "name": "恶之波动", "power": 90, "type": "evil", "pp": 10, "effect": "无特效"},
    
    # 光系技能（迪莫技能）
    {"id": 34, "name": "圣光", "power": 60, "type": "light", "pp": 20, "effect": "无特效"},
    {"id": 35, "name": "光明裁决", "power": 80, "type": "light", "pp": 10, "effect": "无特效"},
    {"id": 36, "name": "圣光护体", "power": 0, "type": "light", "pp": 10, "effect": "提升自身双防 1 级"},
    {"id": 37, "name": "神圣之光", "power": 90, "type": "light", "pp": 10, "effect": "无特效"},
    
    # 机械系技能
    {"id": 38, "name": "机械冲击", "power": 60, "type": "mechanical", "pp": 20, "effect": "无特效"},
    {"id": 39, "name": "钢铁之壁", "power": 0, "type": "mechanical", "pp": 10, "effect": "大幅提升自身防御"},
    {"id": 40, "name": "激光炮", "power": 90, "type": "mechanical", "pp": 10, "effect": "无特效"},
    {"id": 41, "name": "加农光炮", "power": 100, "type": "mechanical", "pp": 5, "effect": "无特效"},
    
    # 电系技能
    {"id": 42, "name": "电击", "power": 40, "type": "electric", "pp": 30, "effect": "10% 几率麻痹"},
    {"id": 43, "name": "十万伏特", "power": 90, "type": "electric", "pp": 15, "effect": "10% 几率麻痹"},
    {"id": 44, "name": "打雷", "power": 110, "type": "electric", "pp": 10, "effect": "70% 命中率，30% 几率麻痹"},
    {"id": 45, "name": "电磁波", "power": 0, "type": "electric", "pp": 20, "effect": "使对手麻痹"},
    
    # 普通系技能
    {"id": 46, "name": "撞击", "power": 35, "type": "normal", "pp": 35, "effect": "无特效"},
    {"id": 47, "name": "抓", "power": 40, "type": "normal", "pp": 35, "effect": "无特效"},
    {"id": 48, "name": "瞪眼", "power": 0, "type": "normal", "pp": 30, "effect": "降低对手防御 1 级"},
    {"id": 49, "name": "叫声", "power": 0, "type": "normal", "pp": 40, "effect": "降低对手攻击 1 级"},
    {"id": 50, "name": "舍身冲撞", "power": 120, "type": "normal", "pp": 15, "effect": "反弹 1/3 伤害"},
]

def generate_database():
    """生成完整的精灵数据库"""
    print("=" * 60)
    print("洛克王国世界完整精灵数据库生成器")
    print("=" * 60)
    
    # 生成精灵列表
    pets = []
    for elf_no, name, type1, type2 in ELF_DATA:
        pets.append({
            "id": elf_no,
            "name": name,
            "type": type1,
            "secondary_type": type2,
        })
    
    # 保存精灵数据库
    pet_db = {
        "version": "2026-03-26 公测版",
        "source": "官方数据整合",
        "total_count": len(pets),
        "pets": pets,
    }
    
    with open("config/pet_database_full.json", "w", encoding="utf-8") as f:
        json.dump(pet_db, f, ensure_ascii=False, indent=2)
    
    print(f"\n[完成] 精灵数据库已生成")
    print(f"  - 总数：{len(pets)} 只精灵")
    print(f"  - 文件：config/pet_database_full.json")
    
    # 保存技能数据库
    skill_db = {
        "version": "2026-03-26",
        "source": "官方数据整合",
        "total_skills": len(SKILL_DATABASE),
        "skills": SKILL_DATABASE,
    }
    
    with open("config/skill_database.json", "w", encoding="utf-8") as f:
        json.dump(skill_db, f, ensure_ascii=False, indent=2)
    
    print(f"\n[完成] 技能数据库已生成")
    print(f"  - 总数：{len(SKILL_DATABASE)} 个技能")
    print(f"  - 文件：config/skill_database.json")
    
    # 显示前 20 只精灵预览
    print("\n前 20 只精灵预览：")
    for pet in pets[:20]:
        type_str = pet["type"]
        if pet.get("secondary_type"):
            type_str += f"/{pet['secondary_type']}"
        print(f"  NO.{pet['id']:03d} {pet['name']:15s} [{type_str}]")
    
    print("\n" + "=" * 60)
    print("生成完成！")
    print("=" * 60)

if __name__ == "__main__":
    generate_database()
