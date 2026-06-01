"""
astrbot_plugin_cultivation - 修仙修炼插件
群聊修仙修炼系统，支持玩家注册、属性修炼、背包系统。
管理员可通过 WebUI 管理所有玩家数据。
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, List

from quart import jsonify, request

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import At

PLUGIN_NAME = "astrbot_plugin_cultivation"

# ---------- 数据文件路径辅助 ----------

def _get_data_dir() -> Path:
    """获取插件数据目录，兼容不同 AstrBot 版本。"""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path
        return Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
    except ImportError:
        # 兜底：使用当前工作目录下的 data 目录
        return Path(os.getcwd()) / "data" / "plugin_data" / PLUGIN_NAME


# ---------- 插件主类 ----------

@register(PLUGIN_NAME, "Copilot", "群聊修仙修炼插件，支持注册、修炼、背包与 WebUI 管理", "1.0.0")
class CultivationPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config
        self._lock = asyncio.Lock()
        self._players: Dict[str, Dict[str, Dict[str, Any]]] = {"players": {}}
        self._data_path: Path = None

    # ==================== 初始化 / 销毁 ====================

    async def initialize(self):
        """插件初始化：创建数据目录、加载数据、注册 Web API。"""
        self._data_path = _get_data_dir() / "players.json"
        self._data_path.parent.mkdir(parents=True, exist_ok=True)

        if self._data_path.exists():
            await self._load_data()
        else:
            await self._save_data()

        # ---- 注册 Web API（供管理页面使用） ----
        ctx = self.context
        ctx.register_web_api(f"/{PLUGIN_NAME}/players", self._api_players, ["GET"], "获取所有玩家数据")
        ctx.register_web_api(f"/{PLUGIN_NAME}/player/update", self._api_player_update, ["POST"], "更新单个玩家属性")
        ctx.register_web_api(f"/{PLUGIN_NAME}/player/delete", self._api_player_delete, ["POST"], "删除玩家")
        ctx.register_web_api(f"/{PLUGIN_NAME}/whitelist/get", self._api_whitelist_get, ["GET"], "获取群白名单")
        ctx.register_web_api(f"/{PLUGIN_NAME}/whitelist/update", self._api_whitelist_update, ["POST"], "更新群白名单")

        logger.info(f"[{PLUGIN_NAME}] 修仙修炼插件已初始化，数据路径: {self._data_path}")

    async def terminate(self):
        """插件卸载时保存数据。"""
        await self._save_data()
        logger.info(f"[{PLUGIN_NAME}] 修仙修炼插件已卸载，数据已保存。")

    # ==================== 数据读写 ====================

    async def _load_data(self):
        """从磁盘加载玩家数据到内存。"""
        try:
            async with self._lock:
                with open(self._data_path, "r", encoding="utf-8") as f:
                    self._players = json.load(f)
            if "players" not in self._players:
                self._players["players"] = {}
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"[{PLUGIN_NAME}] 加载数据失败，使用空数据。错误: {e}")
            self._players = {"players": {}}

    async def _save_data(self):
        """将内存中的玩家数据写入磁盘。"""
        try:
            async with self._lock:
                with open(self._data_path, "w", encoding="utf-8") as f:
                    json.dump(self._players, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"[{PLUGIN_NAME}] 保存数据失败: {e}")

    # ==================== 工具方法 ====================

    def _check_whitelist(self, event: AstrMessageEvent) -> bool:
        """检查当前群聊是否在白名单中。私聊返回 False。"""
        group_id = event.message_obj.group_id
        if not group_id:
            return False
        whitelist = self.config.get("group_whitelist", []) if self.config else []
        return str(group_id) in [str(g) for g in whitelist]

    def _get_player(self, group_id: str, user_id: str) -> dict | None:
        """获取指定群内指定用户的玩家数据，不存在返回 None。"""
        return self._players["players"].get(str(group_id), {}).get(str(user_id))

    def _ensure_player(self, group_id: str, user_id: str) -> dict:
        """获取或创建玩家数据（仅创建结构，不填充默认值）。"""
        gid = str(group_id)
        uid = str(user_id)
        if gid not in self._players["players"]:
            self._players["players"][gid] = {}
        if uid not in self._players["players"][gid]:
            self._players["players"][gid][uid] = {}
        return self._players["players"][gid][uid]

    def _get_base_values(self) -> dict:
        """从配置中读取各项基础值。"""
        if not self.config:
            return {
                "cultivation": 0, "attack": 10, "defense": 10,
                "speed": 10, "mind": 10, "spirit_stones": 0, "backpack": [],
            }
        return {
            "cultivation": self.config.get("base_cultivation", 0),
            "attack": self.config.get("base_attack", 10),
            "defense": self.config.get("base_defense", 10),
            "speed": self.config.get("base_speed", 10),
            "mind": self.config.get("base_mind", 10),
            "spirit_stones": self.config.get("base_spirit_stones", 0),
            "backpack": list(self.config.get("base_backpack", [])),
        }

    async def _add_cultivation(self, group_id: str, user_id: str) -> int:
        """为指定玩家增加修为（发言触发），返回增加后的修为值。"""
        per_msg = self.config.get("cultivation_per_message", 1) if self.config else 1
        player = self._ensure_player(group_id, user_id)
        current = player.get("cultivation", self._get_base_values()["cultivation"])
        player["cultivation"] = current + per_msg
        await self._save_data()
        return player["cultivation"]

    # ==================== 自动修炼（消息监听） ====================

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """监听所有群消息，为已注册且在白名单群内的玩家自动增加修为。"""
        if not self._check_whitelist(event):
            return  # 非白名单群，静默忽略

        group_id = event.message_obj.group_id
        user_id = event.get_sender_id()
        player = self._get_player(group_id, user_id)
        if player is None or not player.get("name"):
            return  # 未注册或数据不完整，忽略

        await self._add_cultivation(group_id, user_id)

    # ==================== 指令：注册 ====================

    @filter.command_group("修炼")
    def cultivation(self):
        """修仙修炼指令组"""
        pass

    @cultivation.command("注册")
    async def cmd_register(self, event: AstrMessageEvent, name: str = ""):
        """注册修炼身份 —— /修炼 注册 <道号>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return

        if not name or not name.strip():
            yield event.plain_result("❌ 请提供道号。用法：/修炼 注册 <道号>\n示例：/修炼 注册 太虚真人")
            return

        name = name.strip()
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())

        existing = self._get_player(group_id, user_id)
        if existing and existing.get("name"):
            yield event.plain_result(f"❌ 你已注册为「{existing['name']}」，无需重复注册。如需改名请使用 /修炼 设置 姓名 <新道号>")
            return

        base = self._get_base_values()
        player = self._ensure_player(group_id, user_id)
        player["name"] = name
        for key in ["cultivation", "attack", "defense", "speed", "mind", "spirit_stones"]:
            if key not in player:
                player[key] = base[key]
        if "backpack" not in player:
            player["backpack"] = list(base["backpack"])

        await self._save_data()

        yield event.plain_result(
            f"✨ 注册成功！\n"
            f"道号：{name}\n"
            f"修为：{player['cultivation']} | 攻击：{player['attack']} | 防御：{player['defense']}\n"
            f"速度：{player['speed']} | 心性：{player['mind']} | 灵石：{player['spirit_stones']}\n"
            f"背包：{'空' if not player['backpack'] else '、'.join(str(i) for i in player['backpack'])}"
        )

    # ==================== 指令：状态 ====================

    @cultivation.command("状态")
    async def cmd_status(self, event: AstrMessageEvent):
        """查看自己或他人的修炼状态 —— /修炼 状态 [@某人]"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return

        group_id = str(event.message_obj.group_id)
        message_chain = event.get_messages()

        # 检查是否 @ 了某人
        target_user_id = None
        target_name_hint = ""
        for comp in message_chain:
            if isinstance(comp, At):
                target_user_id = str(comp.qq)
                break

        if target_user_id:
            player = self._get_player(group_id, target_user_id)
            if not player:
                yield event.plain_result("❌ 该用户尚未注册修炼。")
                return
            target_name_hint = f"「{player.get('name', '未知')}」的"
        else:
            user_id = str(event.get_sender_id())
            player = self._get_player(group_id, user_id)
            if not player:
                yield event.plain_result("❌ 你尚未注册修炼。请使用 /修炼 注册 <道号> 进行注册。")
                return
            target_name_hint = "你的"

        bp = player.get("backpack", [])
        bp_str = "空" if not bp else "、".join(str(i) for i in bp)

        yield event.plain_result(
            f"📜 {target_name_hint}修炼状态\n"
            f"═══════════════════\n"
            f"道号：{player.get('name', '未知')}\n"
            f"修为：{player.get('cultivation', 0)}\n"
            f"攻击：{player.get('attack', 0)}\n"
            f"防御：{player.get('defense', 0)}\n"
            f"速度：{player.get('speed', 0)}\n"
            f"心性：{player.get('mind', 0)}\n"
            f"灵石：{player.get('spirit_stones', 0)}\n"
            f"背包：{bp_str}"
        )

    # ==================== 指令：设置属性 ====================

    @cultivation.group("设置")
    def settings(self):
        """修炼属性设置"""
        pass

    @settings.command("姓名")
    async def cmd_set_name(self, event: AstrMessageEvent, name: str = ""):
        """修改道号 —— /修炼 设置 姓名 <新道号>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        if not name or not name.strip():
            yield event.plain_result("❌ 请提供新道号。用法：/修炼 设置 姓名 <新道号>")
            return

        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return

        old_name = player.get("name", "未知")
        player["name"] = name.strip()
        await self._save_data()
        yield event.plain_result(f"✅ 道号已从「{old_name}」修改为「{player['name']}」。")

    @settings.command("修为")
    async def cmd_set_cultivation(self, event: AstrMessageEvent, value: int = 0):
        """修改修为 —— /修炼 设置 修为 <数值>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return
        player["cultivation"] = value
        await self._save_data()
        yield event.plain_result(f"✅ 修为已修改为 {value}。")

    @settings.command("攻击")
    async def cmd_set_attack(self, event: AstrMessageEvent, value: int = 0):
        """修改攻击 —— /修炼 设置 攻击 <数值>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return
        player["attack"] = value
        await self._save_data()
        yield event.plain_result(f"✅ 攻击已修改为 {value}。")

    @settings.command("防御")
    async def cmd_set_defense(self, event: AstrMessageEvent, value: int = 0):
        """修改防御 —— /修炼 设置 防御 <数值>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return
        player["defense"] = value
        await self._save_data()
        yield event.plain_result(f"✅ 防御已修改为 {value}。")

    @settings.command("速度")
    async def cmd_set_speed(self, event: AstrMessageEvent, value: int = 0):
        """修改速度 —— /修炼 设置 速度 <数值>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return
        player["speed"] = value
        await self._save_data()
        yield event.plain_result(f"✅ 速度已修改为 {value}。")

    @settings.command("心性")
    async def cmd_set_mind(self, event: AstrMessageEvent, value: int = 0):
        """修改心性 —— /修炼 设置 心性 <数值>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return
        player["mind"] = value
        await self._save_data()
        yield event.plain_result(f"✅ 心性已修改为 {value}。")

    @settings.command("灵石")
    async def cmd_set_spirit_stones(self, event: AstrMessageEvent, value: int = 0):
        """修改灵石 —— /修炼 设置 灵石 <数值>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return
        player["spirit_stones"] = value
        await self._save_data()
        yield event.plain_result(f"✅ 灵石已修改为 {value}。")

    # ==================== 指令：背包 ====================

    @cultivation.group("背包")
    def backpack(self):
        """修炼背包管理"""
        pass

    @backpack.command("添加")
    async def cmd_bp_add(self, event: AstrMessageEvent, item: str = ""):
        """添加背包物品 —— /修炼 背包 添加 <物品名>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        if not item or not item.strip():
            yield event.plain_result("❌ 请提供物品名。用法：/修炼 背包 添加 <物品名>")
            return

        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return

        if "backpack" not in player:
            player["backpack"] = []
        player["backpack"].append(item.strip())
        await self._save_data()
        yield event.plain_result(f"✅ 已将「{item.strip()}」放入背包。")

    @backpack.command("移除")
    async def cmd_bp_remove(self, event: AstrMessageEvent, item: str = ""):
        """移除背包物品 —— /修炼 背包 移除 <物品名>"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return
        if not item or not item.strip():
            yield event.plain_result("❌ 请提供物品名。用法：/修炼 背包 移除 <物品名>")
            return

        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return

        bp = player.get("backpack", [])
        item_stripped = item.strip()
        if item_stripped in bp:
            bp.remove(item_stripped)
            await self._save_data()
            yield event.plain_result(f"✅ 已将「{item_stripped}」从背包移除。")
        else:
            yield event.plain_result(f"❌ 背包中没有「{item_stripped}」。")

    @backpack.command("列表")
    async def cmd_bp_list(self, event: AstrMessageEvent):
        """查看背包 —— /修炼 背包 列表"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return

        group_id = str(event.message_obj.group_id)
        user_id = str(event.get_sender_id())
        player = self._get_player(group_id, user_id)
        if not player:
            yield event.plain_result("❌ 你尚未注册修炼，请先使用 /修炼 注册 <道号> 注册。")
            return

        bp = player.get("backpack", [])
        if not bp:
            yield event.plain_result("🎒 你的背包空空如也。")
        else:
            items = "\n".join(f"  • {i}" for i in bp)
            yield event.plain_result(f"🎒 {player.get('name', '修士')} 的背包：\n{items}")

    # ==================== 指令：排行 ====================

    @cultivation.command("排行")
    async def cmd_leaderboard(self, event: AstrMessageEvent, page: int = 1):
        """查看本群修为排行 —— /修炼 排行 [页码]"""
        if not self._check_whitelist(event):
            yield event.plain_result("❌ 本群未在修炼白名单中，无法使用修炼功能。")
            return

        group_id = str(event.message_obj.group_id)
        group_players = self._players["players"].get(group_id, {})
        if not group_players:
            yield event.plain_result("📊 本群暂无修炼者。")
            return

        # 按修为降序排列
        sorted_players = sorted(
            group_players.items(),
            key=lambda kv: kv[1].get("cultivation", 0),
            reverse=True,
        )

        page_size = 10
        total_pages = max(1, (len(sorted_players) + page_size - 1) // page_size)
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages

        start = (page - 1) * page_size
        end = start + page_size
        page_players = sorted_players[start:end]

        lines = [f"🏆 修炼排行榜 (第 {page}/{total_pages} 页)", "═══════════════════"]
        for rank, (uid, pdata) in enumerate(page_players, start=start + 1):
            name = pdata.get("name", "无名修士")
            cult = pdata.get("cultivation", 0)
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")
            lines.append(f"{medal} {name} —— 修为 {cult}")

        yield event.plain_result("\n".join(lines))

    # ==================== 指令：白名单管理（管理员） ====================

    @cultivation.group("白名单")
    def whitelist_group(self):
        """修炼白名单管理（仅管理员）"""
        pass

    @whitelist_group.command("添加")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_wl_add(self, event: AstrMessageEvent, group_id: str = ""):
        """添加群聊白名单 —— /修炼 白名单 添加 <群号>"""
        if not group_id or not group_id.strip():
            yield event.plain_result("❌ 请提供群号。用法：/修炼 白名单 添加 <群号>")
            return

        group_id = group_id.strip()
        whitelist: list = list(self.config.get("group_whitelist", [])) if self.config else []
        if group_id in [str(g) for g in whitelist]:
            yield event.plain_result(f"⚠️ 群 {group_id} 已在白名单中。")
            return

        whitelist.append(group_id)
        if self.config:
            self.config["group_whitelist"] = whitelist
            self.config.save_config()
        yield event.plain_result(f"✅ 已将群 {group_id} 加入修炼白名单。当前白名单: {', '.join(str(g) for g in whitelist)}")

    @whitelist_group.command("移除")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_wl_remove(self, event: AstrMessageEvent, group_id: str = ""):
        """移除群聊白名单 —— /修炼 白名单 移除 <群号>"""
        if not group_id or not group_id.strip():
            yield event.plain_result("❌ 请提供群号。用法：/修炼 白名单 移除 <群号>")
            return

        group_id = group_id.strip()
        whitelist: list = list(self.config.get("group_whitelist", [])) if self.config else []
        str_wl = [str(g) for g in whitelist]
        if group_id not in str_wl:
            yield event.plain_result(f"⚠️ 群 {group_id} 不在白名单中。")
            return

        whitelist = [g for g in whitelist if str(g) != group_id]
        if self.config:
            self.config["group_whitelist"] = whitelist
            self.config.save_config()
        yield event.plain_result(f"✅ 已将群 {group_id} 从修炼白名单移除。当前白名单: {', '.join(str(g) for g in whitelist) if whitelist else '空'}")

    @whitelist_group.command("列表")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_wl_list(self, event: AstrMessageEvent):
        """查看白名单 —— /修炼 白名单 列表"""
        whitelist = self.config.get("group_whitelist", []) if self.config else []
        if not whitelist:
            yield event.plain_result("📋 当前修炼白名单为空。")
        else:
            yield event.plain_result(f"📋 当前修炼白名单:\n" + "\n".join(f"  • {g}" for g in whitelist))

    # ==================== Web API：管理页面后端 ====================

    async def _api_players(self):
        """GET /api/plug/astrbot_plugin_cultivation/players
        返回所有玩家数据，结构: { "players": { "group_id": { "user_id": {...} } } }
        """
        return jsonify(self._players)

    async def _api_player_update(self):
        """POST /api/plug/astrbot_plugin_cultivation/player/update
        请求体 JSON: { "group_id": "...", "user_id": "...", "field": "属性名", "value": 新值 }
        修改单个玩家的某个属性。
        """
        try:
            data = await request.get_json()
            group_id = str(data.get("group_id", ""))
            user_id = str(data.get("user_id", ""))
            field = data.get("field", "")
            value = data.get("value")

            if not group_id or not user_id or not field:
                return jsonify({"ok": False, "msg": "参数不完整"}), 400

            allowed_fields = ["name", "cultivation", "attack", "defense", "speed", "mind", "spirit_stones", "backpack"]
            if field not in allowed_fields:
                return jsonify({"ok": False, "msg": f"不允许的字段: {field}"}), 400

            # 若玩家不存在，先用基础值初始化，防止产生数据不完整的"幽灵玩家"
            existing = self._get_player(group_id, user_id)
            if existing is None:
                base = self._get_base_values()
                player = self._ensure_player(group_id, user_id)
                player["name"] = ""
                player["cultivation"] = base["cultivation"]
                player["attack"] = base["attack"]
                player["defense"] = base["defense"]
                player["speed"] = base["speed"]
                player["mind"] = base["mind"]
                player["spirit_stones"] = base["spirit_stones"]
                player["backpack"] = list(base["backpack"])
            else:
                player = existing

            # 类型转换
            if field == "backpack":
                if isinstance(value, list):
                    player[field] = value
                elif isinstance(value, str):
                    # 尝试解析 JSON 或按逗号分割
                    try:
                        player[field] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        player[field] = [v.strip() for v in value.split(",") if v.strip()]
                else:
                    return jsonify({"ok": False, "msg": "背包值格式不正确"}), 400
            elif field == "name":
                player[field] = str(value)
            else:
                player[field] = int(value)

            await self._save_data()
            return jsonify({"ok": True, "msg": "更新成功", "player": player})

        except Exception as e:
            logger.error(f"[{PLUGIN_NAME}] API player/update 错误: {e}")
            return jsonify({"ok": False, "msg": str(e)}), 500

    async def _api_player_delete(self):
        """POST /api/plug/astrbot_plugin_cultivation/player/delete
        请求体 JSON: { "group_id": "...", "user_id": "..." }
        删除指定玩家。
        """
        try:
            data = await request.get_json()
            group_id = str(data.get("group_id", ""))
            user_id = str(data.get("user_id", ""))

            if not group_id or not user_id:
                return jsonify({"ok": False, "msg": "参数不完整"}), 400

            gid = str(group_id)
            uid = str(user_id)
            if gid in self._players["players"] and uid in self._players["players"][gid]:
                del self._players["players"][gid][uid]
                if not self._players["players"][gid]:
                    del self._players["players"][gid]
                await self._save_data()
                return jsonify({"ok": True, "msg": "删除成功"})
            else:
                return jsonify({"ok": False, "msg": "玩家不存在"}), 404

        except Exception as e:
            logger.error(f"[{PLUGIN_NAME}] API player/delete 错误: {e}")
            return jsonify({"ok": False, "msg": str(e)}), 500

    async def _api_whitelist_get(self):
        """GET /api/plug/astrbot_plugin_cultivation/whitelist/get
        返回当前白名单列表。
        """
        whitelist = self.config.get("group_whitelist", []) if self.config else []
        return jsonify({"whitelist": whitelist})

    async def _api_whitelist_update(self):
        """POST /api/plug/astrbot_plugin_cultivation/whitelist/update
        请求体 JSON: { "whitelist": ["群号1", "群号2", ...] }
        覆盖更新白名单。
        """
        try:
            data = await request.get_json()
            new_wl = data.get("whitelist", [])
            if not isinstance(new_wl, list):
                return jsonify({"ok": False, "msg": "whitelist 必须是列表"}), 400

            if self.config:
                self.config["group_whitelist"] = [str(g) for g in new_wl]
                self.config.save_config()

            return jsonify({"ok": True, "msg": "白名单更新成功", "whitelist": self.config["group_whitelist"] if self.config else []})

        except Exception as e:
            logger.error(f"[{PLUGIN_NAME}] API whitelist/update 错误: {e}")
            return jsonify({"ok": False, "msg": str(e)}), 500
