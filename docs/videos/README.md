# 讲解视频

每个教学阶段一段短片，`/learn` 页面里每个阶段旁边的「看讲解视频」播放的就是这里的文件。清单见 [`video/parts.json`](../../video/parts.json)：

| 文件 | 内容 | 对应教程 |
|---|---|---|
| [`p01-upload.mp4`](p01-upload.mp4) | 上传：先有 S3 对象和 DynamoDB 里的一条 case | [01](../tutorial/01-upload.md) |
| [`p02-state.mp4`](p02-state.mp4) | 状态机：条件写只让合法的转移提交 | [02](../tutorial/02-state-machine.md) |
| [`p03-intake.mp4`](p03-intake.mp4) | S3 触发 Lambda，按账户进 SQS FIFO | [03](../tutorial/03-intake-lambda-fifo.md) |
| [`p04-extract.mp4`](p04-extract.mp4) | 抽取和校验：每个字段都带置信度 | [04](../tutorial/04-extract-validate.md) |
| [`p05-decide.mp4`](p05-decide.mp4) | 字段匹配和决策：不确定的 AI 输出不能单独定结果 | [05](../tutorial/05-match-decide.md) |
| [`p06-idempotency.mp4`](p06-idempotency.mp4) | 幂等：重复消息和重启都不会处理两次 | [06](../tutorial/06-idempotency.md) |
| [`p07-review.mp4`](p07-review.mp4) | 人审：最小堆按风险和等待时间排队 | [07](../tutorial/07-human-review.md) |
| [`p08-callback.mp4`](p08-callback.mp4) | 回调：一份契约、HMAC 签名、退避重试 | [08](../tutorial/08-callbacks.md) |
| [`p09-learn.mp4`](p09-learn.mp4) | 教学模式本身：源码锚点和固定链接 | [09](../tutorial/09-frontend-learn-mode.md) |
| [`p10-eval.mp4`](p10-eval.mp4) | 评测集和发布门禁 | [10](../tutorial/10-evaluation.md) |

画面由 `video/record.mjs` 在真实页面上录制（会话里的数据都是这次真实请求产生的），红框标出每一步该看的地方；旁白来自 `video/narration.json`。旁白是用作者本人声音在本地克隆合成的（CosyVoice 2，不调任何云端 API），成片用本地 whisper 逐段回验过念的是稿子上的话。

## 日常问题（`problems/`）

每个问题一段代码讲解：先看修复前的写法和现象，再看修复后的写法，讲到哪几行就用红框框出哪几行。内容来自 [`video/problems.walk.json`](../../video/problems.walk.json)（由 `scripts/build_problem_videos.py` 按锚点从源码生成），问题的来龙去脉见 [`docs/problems.md`](../problems.md)。

- [`q01-lambda-lost-event.mp4`](problems/q01-lambda-lost-event.mp4) — S3 事件丢了，case 停在 UPLOADED
- [`q02-prefetch-batch.mp4`](problems/q02-prefetch-batch.mp4) — worker 一次预取十条，好文档进了死信
- [`q03-alias-suffix.mp4`](problems/q03-alias-suffix.mp4) — Inc 满分匹配了另一家 LLC
- [`q04-ocr-diacritics.mp4`](problems/q04-ocr-diacritics.mp4) — 评测门禁没过：变音符号的名字更难通过
- [`q05-zsh-flags.mp4`](problems/q05-zsh-flags.mp4) — 对照组的开关没生效，测试假绿
- [`q06-loose-chaos-assert.mp4`](problems/q06-loose-chaos-assert.mp4) — 混沌测试太宽松，关掉条件写也是绿的
- [`q07-stale-receipt.mp4`](problems/q07-stale-receipt.mp4) — 确认消息时报参数无效
- [`q08-concurrent-decisions.mp4`](problems/q08-concurrent-decisions.mp4) — 二十个线程同时下结论，二十个都成功了
- [`q09-uncapped-backoff.mp4`](problems/q09-uncapped-backoff.mp4) — 毒消息测试超时：退避没有上限
- [`q10-scan-pagination.mp4`](problems/q10-scan-pagination.mp4) — 单跑能过，全量就失败
