# 07 人审：不确定的交给人

> 视频：[p07-review.mp4](../videos/p07-review.mp4) · tag：`step-07`

## 这一章解决什么问题？

第 05 章的策略把所有「不确定」都送进了 IN_REVIEW。现在要回答三个问题：

1. 谁有资格审？（鉴权）
2. 先审哪个？（排队）
3. 两个审核员会不会抢到同一个 case？（并发）

顺带还有一条流程：审核员要求重新提交以后，平台怎么重新交。

## 鉴权：两种身份

- **平台**用 API client 登录：`client_id + client_secret` 换一个一小时有效的 JWT，里面带着平台名。数据库里只存 secret 的 PBKDF2 加盐哈希，明文只在创建时出现一次。
- **审核员**用用户名和密码登录，JWT 里的角色是 reviewer。

平台之间是隔离的：ads 平台去查 ecommerce 平台的 case，拿到的是 404 而不是 403，不暴露「这个 case 存在」。平台也不能替别的平台的账户交材料（403）。

## 排队：一个不会随时间变的堆

想要的优先级是：**风险分 × 60 秒 + 已等待秒数**，值大的先审。

问题是「已等待秒数」每秒都在变，堆的 key 总不能每秒重算一遍吧？

不用。所有 case 的等待时间都在以同样的速度增长，所以两个 case 之间的先后顺序永远不变：

```
argmax(risk·K + now − t)  ==  argmin(t − risk·K)
```

于是堆的 key 在入队时算一次就够了：`enqueued_at − risk × 60`，用最小堆。

假设：一个风险零分、等了三千秒的 case，和一个风险四十分、刚到的 case，谁先？
四十分折合两千四百秒，比不过三千秒，所以老的先。`test_aging_lets_a_low_risk_case_overtake` 就是这个例子。

删除用的是懒删除：`remove` 只把它从「活着的」字典里拿掉，堆里的旧条目等它浮到堆顶时再丢掉。

## 并发：领取也是一次条件写

`POST /v1/review/claim` 从堆里弹出一个，然后：

```
SET claimed_by = 我, claim_expires = 现在 + 15 分钟
条件：state = IN_REVIEW 并且（没人领 或 领取已过期）
```

条件不成立，说明在「弹出」和「写入」之间别人领走了，那就弹下一个。
提交结论时，再加一个条件：`claimed_by = 我`。别人领的 case 你下不了结论（409）。

`test_two_reviewers_never_claim_the_same_case` 让十二个线程同时领，断言没有一个 case 被发出去两次。

## 重新提交

审核员选「要求重新提交」，case 进 RESUBMIT_REQUESTED，回调会通知平台。
平台调 `POST /v1/cases/{id}/resubmit`：轮次加一，新文件放在 `r2/` 下面，状态回到 UPLOADED，然后整条流水线再跑一遍。
history 里两轮的记录都在，第一轮的结论不会被覆盖。

## 真实跑一次：两轮的 history

e2e 里那个「低分辨率扫描件 → 人审 → 要求重新提交 → 平台重传」的 case，DynamoDB 里的 history 是：

```
  r1  NEW                -> UPLOADED            api:ecommerce-demo
  r1  UPLOADED           -> QUEUED              lambda:intake
  r1  QUEUED             -> EXTRACTED           worker:worker-1
  r1  EXTRACTED          -> VALIDATED           worker:worker-1
  r1  VALIDATED          -> IN_REVIEW           worker:worker-1
  r1  IN_REVIEW          -> RESUBMIT_REQUESTED  reviewer:reviewer
  r1  RESUBMIT_REQUESTED -> UPLOADED            api:ecommerce-demo
  r2  UPLOADED           -> QUEUED              lambda:intake
  r2  QUEUED             -> EXTRACTED           worker:worker-1
  r2  EXTRACTED          -> VALIDATED           worker:worker-1
  r2  VALIDATED          -> APPROVED            worker:worker-1
```

每一行的 actor 都是真正做这一步的那个身份：API 代表哪个平台、哪个 worker、哪个审核员。

## 代码

- `docverify/auth.py`（锚点 `@learn:auth`）
- `docverify/review.py`（锚点 `@learn:review-heap`）
- `docverify/api/main.py`（锚点 `@learn:claim`、`@learn:resubmit`）

## 怎么跑到这一步

```bash
git checkout step-07
DOCVERIFY_SEED_DEMO=1 .venv/bin/python -m docverify.bootstrap
.venv/bin/pytest tests/test_step07_review.py
```
