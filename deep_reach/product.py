"""Product-level constants and promises.

Keep these in one place so CLI, doctor, and docs tell the same story.
"""

from __future__ import annotations

from .channels.base import TIER_ACCESS, TIER_LABELS, TIERS

NAME = "deep-reach"
TAGLINE = "给 AI agent 一个免费优先、按层降级、可读可写的通用上网入口。"

PROMISES = [
    "一个动词表：search / read / comments / product / bestsellers / quote",
    "可读可写：写操作由动作声明；P3 bsk 可写，需确认用户意图",
    "按层降级：P0 官方接口 → P1 公开网页 → P2 第三方引擎 → P3 bsk UI 回退",
    "没有 key 也能跑：缺 key / 缺登录只降级对应渠道",
    "说人话：错误码之外，告诉用户下一步",
    "列出的渠道必须能用；没实现的只出现在 roadmap",
    "本地优先：配置、状态、浏览器 profile 都在本机",
    "证据可追溯：source / url / backend / tier / fetched_at",
    "不互相踩：同站并发槽、搜索间隔、限流冷却、失败后端暂停",
]

NON_GOALS = [
    "不自建爬虫集群；P2 只调用第三方公开服务",
    "不接付费 API",
    "不做多用户 / 云服务",
    "不承诺完整评论树或图片/视频理解",
]

LEVELS = {
    "default": "装好就能跑",
    "optional": "需要登录或免费 key",
    "experimental": "可能受反爬/页面改版影响",
    "planned": "尚未实现，只在 roadmap",
}

TIER_TABLE = {
    tier: {"label": TIER_LABELS[tier], "access": TIER_ACCESS[tier]} for tier in TIERS
}
