# Deep-Reach 能力契约

> 声明能力，不代表所有网络、账号和页面都实测。  
> `requires`：`none` / `login` / `key`。  
> `tier`：`p0` 原生免费接口 / `p1` OpenCLI / `p2` 第三方采集。多层按顺序自动降级。

## default

| 渠道 | 动作 | requires | tier | 能拿到 | 不能/不保证 |
|---|---|---|---|---|---|
| `bilibili` | `search` | none | p0+p1 | 视频标题、作者、播放/点赞/收藏/弹幕、URL | 公开搜索可能触发 -412，自动降 P1 |
| `bilibili` | `read` | none | p0+p1 | 视频信息 | — |
| `bilibili` | `subtitle` | login | p1 | 字幕 | 需要登录；部分视频无字幕 |
| `bilibili` | `comments` | none | p0+p1 | 已加载评论 | 不保证全部回复 |
| `youtube` | `search` | none | p0+p1 | 视频标题、频道、观看数、URL | p0 需要 YouTube Data API key |
| `youtube` | `read` | none | p0+p1 | 视频信息 | p0 需要 YouTube Data API key |
| `weibo` | `hot` | none | p1 | 热搜词、热度、分类、URL | — |
| `weibo` | `search` | login | p1 | 微博搜索结果 | 需要登录；不保证完整评论树 |
| `weibo` | `read` | none | p1 | 单条微博 | — |
| `weibo` | `comments` | none | p1 | 已加载评论 | 不保证全部回复 |
| `xueqiu` | `quote` | none | p0+p1 | A/HK/US 实时价格、涨跌、成交额 | 不提供历史 K 线 |
| `xueqiu` | `hot` | login | p0+p1 | 热门动态；优先雪球 API | 需要 `xueqiu.cookie` 或 OpenCLI 登录 |
| `xueqiu` | `hot_stocks` | login | p0 | 雪球热搜股 | 需要 `xueqiu.cookie` |
| `xueqiu` | `search` | none | p0+p1 | 股票搜索结果；腾讯 smartbox 优先 | — |
| `xueqiu` | `comments` | none | p1 | 股票讨论 | 不保证全部回复 |
| `amazon` | `search` | none | p1 | 标题、ASIN、价格、评分、评论数、URL | 不保证广告/库存 |
| `amazon` | `product` | none | p1+p2 | 商品页信息 | 价格/库存以页面为准；p2 是网页读文 |
| `amazon` | `bestsellers` | none | p1 | 榜单条目 | 不保证所有类目 |
| `amazon` | `discussion` | none | p1 | 评论摘要/讨论 | 不保证完整评论树 |
| `web` | `read` | none | p0+p2 | URL → 文本；p0 直连，p2 用 Jina | 不能绕过登录墙；无结构化字段 |
| `github` | `search` | none | p0 | 仓库名、描述、stars/forks/issues、URL | 无 token 时额度低；不含代码搜索 |
| `github` | `read` | none | p0 | 仓库信息 | 私有仓库需要 token 权限 |
| `github` | `issues` | none | p0 | issue 标题、正文、作者、评论/反应数 | 不含 PR；不保证完整评论树 |
| `v2ex` | `hot` | none | p0 | 热门主题 | 约 10 条 |
| `v2ex` | `node` | none | p0 | 节点下的主题 | 约 10 条 |
| `v2ex` | `read` | none | p0 | 主题正文 | — |
| `v2ex` | `comments` | none | p0 | 已加载回复 | 不分页 |

> 雪球 `hot` / `hot_stocks` 的 `xueqiu.cookie` 从已登录浏览器复制，通常几小时过期；过期后重新复制，不需要密码。

## optional（登录）

| 渠道 | 动作 | requires | tier | 能拿到 | 不能/不保证 |
|---|---|---|---|---|---|
| `x` | `search` | login | p1 | 推文搜索结果 | 单帖可读不代表完整回复流 |
| `x` | `read` | login | p1 | 推文串 | 不保证完整评论树 |
| `reddit` | `search` | login | p1 | 帖子搜索结果 | 不保证完整评论树 |
| `reddit` | `read` | login | p1 | 帖子 + 已加载评论 | 不保证全部回复 |
| `xiaohongshu` | `search` | login | p1 | 笔记搜索结果 | 不保证全部评论 |
| `xiaohongshu` | `read` | login | p1 | 笔记正文 | 不声称理解图片/视频 |
| `xiaohongshu` | `comments` | login | p1 | 已加载评论 | 不保证全部回复 |
| `zhihu` | `search` | login | p1 | 问题搜索结果 | 不保证完整回答/评论 |
| `zhihu` | `read` | login | p1 | 问题与回答 | 不保证完整评论树 |
| `douyin` | `search` | login | p1 | 视频搜索结果 | 不保证评论 |
| `douyin` | `videos` | login | p1 | 用户视频列表 | 不保证评论 |
| `douyin` | `detail` | login | p1 | 视频详情 | 不声称理解视频内容 |

## optional（免费 key）

| 渠道 | 动作 | requires | tier | 能拿到 | 不能/不保证 |
|---|---|---|---|---|---|
| `ebay` | `search` | key | p0 | 标题、价格、成色、卖家、国家、URL | 无 key 不可用；不含历史成交价 |
| `ebay` | `read` | key | p0 | 商品详情、描述、价格 | 价格/库存以页面为准 |
| `etsy` | `search` | key | p0 | 标题、价格、浏览量、收藏数、URL | 无 key 不可用；不含历史价格 |
| `etsy` | `read` | key | p0 | 商品详情、描述、标签 | 价格/库存以页面为准 |
| `uspto` | `search` | key | p0 | 美国专利申请/授权的标题、申请人、申请号、专利号、状态 | 不含全文权利要求；商标未接 |
| `uspto` | `read` | key | p0 | 按申请号/专利号读取 | 同上 |
| `epo` | `search` | key | p0 | 全球专利（US/CN/JP/EP）标题、申请人、发明人、公开号 | 不含全文批量下载 |
| `epo` | `read` | key | p0 | 按公开号读取 | 同上 |

## experimental

| 渠道 | 动作 | requires | tier | 说明 |
|---|---|---|---|---|
| `producthunt` | `hot` | none | p0+p1 | 有 token 走官方投票榜；无 token 走 OpenCLI 最新发布 |
| `kickstarter` | `read` | none | p0+p2 | 仅给定 URL；没有搜索 |
| `cnipa` | `read` | none | p0+p2 | 仅给定 URL；官方检索需登录+验证码 |
| `copyright` | `read` | none | p0+p2 | 仅给定 URL；无统一全球版权 API |

## 分层语义

- **P0**：平台自己的免费接口。缺 key 只禁用该后端，不影响其他层。
- **P1**：OpenCLI 浏览器桥，复用已登录的 Chrome；不替用户登录、不碰密码。
- **P2**：第三方阅读/采集服务。只在 P0/P1 不可用时使用。

免费额度：

- YouTube 10,000 units/day（search 100，read 1）；eBay 5,000 calls/day；Etsy 10,000 calls/day。
- 额度记在本地 `state.json`；耗尽抛 `QUOTA_EXHAUSTED` 并降层。
- `doctor` / `state` 显示当日用量。

降级条件：

- `QUOTA_EXHAUSTED`、`NEED_LOGIN`、`UPSTREAM_BROKEN`、`TIMEOUT`、`NEED_SETUP` 继续下一层。
- `RATE_LIMITED`、`BUSY`、`PLATFORM_BLOCKED`、`BAD_INPUT`、`NOT_FOUND`、`WRITE_BLOCKED` 终止，不继续撞。

## planned

KIPRIS、EUIPO、Hacker News、贴吧、虎扑、1688、SellerSprite。

这些渠道尚未实现，`deep-reach channels` 不会显示；`deep-reach roadmap` 可见。
