# 08 回调：四个平台，一份契约

> 视频：[p08-callback.mp4](../videos/p08-callback.mp4) · tag：`step-08`

## 这一章解决什么问题？

电商、广告、直播、支付开户，四个业务平台都要用这套验证。
如果每个平台各接一套接口，改一次字段要改四遍。所以只有一份 v1 契约：同样的提交接口、同样的状态、同样的回调格式。

结果是异步的：验证可能要几秒（自动），也可能要几小时（人审）。平台不该一直轮询，所以用回调通知。

## 回调为什么要先写发件箱？

最直接的写法是：状态一变，马上 POST 给平台。
问题是，POST 失败了怎么办？进程在 POST 之前死了怎么办？

做法是 outbox：

1. 状态变化（IN_REVIEW、APPROVED、REJECTED、RESUBMIT_REQUESTED、FAILED）写一行到 MySQL 的 `callback_outbox`。唯一键是 `(case, 轮次, 状态)`，同一次转移被重放，也只有一行。
2. 一个独立的分发器进程，用 `SELECT ... FOR UPDATE SKIP LOCKED` 取到期的行去投递。开几个分发器都行，它们不会抢同一行。
3. 失败了，按指数退避（带抖动）安排下次时间；六次都失败就标成 dead。

## 签名怎么做？

```
X-DocVerify-Signature: t=<unix 秒>,v1=<hex(HMAC-SHA256(secret, "<t>." + body))>
X-DocVerify-Event-Id: evt_<outbox id>
```

- 时间戳签进去了，所以五分钟以前的签名不能重放。
- 比较用 `hmac.compare_digest`，防时序攻击。
- 每次重试用同一个 event id。投递是「至少一次」，平台按 event id 去重。

secret 是平台调 `PUT /v1/webhooks` 时生成的，只返回这一次。

## 假设：平台挂了两次，第三次才好

`test_outbox_delivers_with_backoff_after_failures` 起一个本地 HTTP 服务，前两次返回 503：

```
attempt  http_status  signature
1        503          t=1795559596,v1=339235337d694e1190ae160c64c4d49ac1718d342833…
2        503          t=1795559596,v1=339235337d694e1190ae160c64c4d49ac1718d342833…
3        200          t=1795559596,v1=339235337d694e1190ae160c64c4d49ac1718d342833…
```

三次投递 event id 相同，每一次的签名都能用平台拿到的 secret 验过。同一个状态被 `enqueue` 两次，发件箱里也只有一行。
（测试里退避基数设成 0.2 秒，所以三次落在同一秒，签名也就相同；默认基数是一秒。）

## mock 平台

`mockplatform/app.py` 是四个平台的替身。启动时用演示 client 登录 API，给每个平台注册 webhook，拿到 secret。
收到回调先验签，再按 event id 去重，界面「平台回调」页能看到每一条和它的验签结果。
页面上有个按钮能让接下来两次投递失败，用来亲眼看重试。

## 代码

- `docverify/callbacks.py`（锚点 `@learn:sign`、`@learn:dispatch`）
- `mockplatform/app.py`

## 怎么跑到这一步

```bash
git checkout step-08
.venv/bin/pytest tests/test_step08_callbacks.py
```
