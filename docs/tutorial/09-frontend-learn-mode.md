# 09 前端和教学模式：把每一步摊开给人看

> 视频：[p09-learn.mp4](../videos/p09-learn.mp4) · tag：`step-09`

## 这一章解决什么问题？

到第 08 章，后端已经完整了，但只有测试和日志能证明它在工作。
这一章做两件事：

1. 一个能用的前端：平台提交和重新提交、审核员的队列和审核页、平台收到的回调。
2. 一个教学模式 `/learn`：提交一个样例，页面一步步亮出请求现在走到了哪一步，旁边是那一步留下的真实数据，还能跳到 GitHub 上对应的源码行。

## 教学模式的状态从哪来？

不是前端定时器。前端每七百毫秒调一次 `GET /v1/learn/runs/{case_id}`，后端 `docverify/learn.py`（锚点 `learn-trace`）从真实的存储里重建每一步：

| 阶段 | 「完成」的判据 | 旁边显示的数据 |
|---|---|---|
| 上传 | history 里有 NEW → UPLOADED | S3 key、哈希、审计行 |
| S3 | `head_object` 成功 | 对象大小、ETag、元数据 |
| Lambda | history 里有 UPLOADED → QUEUED | 审计行 + **这次调用在 CloudWatch 里的日志** |
| SQS | `queue_receipts` 里有行 | 消息体、分组、序列号、第几次投递、哪个 worker、结果 |
| 抽取 / 校验 / 决策 | 对应的转移 | 字段和置信度、每条检查、匹配分数和决策 |
| 人审 | IN_REVIEW → 结论（没进人审就是「跳过」） | 风险分、领取人、审核结论 |
| 回调 | 最终状态的发件箱行已送达 | 发件箱、每次尝试的签名、平台的验签结果 |

第一个还没完成的阶段就是「进行中」，会高亮。

## 源码链接为什么不会错位？

链接的格式是 `https://github.com/evangogowork/docverify/blob/<commit>/<文件>#L<起>-L<止>`。两个关键点：

1. **行号不手写。** 源码里用注释圈出关键代码：

   ```python
   # @learn:transition
   def transition(...):
       ...
   # @learn:end transition
   ```

   `scripts/learn_anchors.mjs` 扫出每个锚点的文件和行号，写进 `frontend/src/generated/anchors.json`。`npm run build` 和 `npm run dev` 都会先跑它。

2. **链接钉在 commit 上，不用 main。** 构建时 vite 读 `git rev-parse HEAD`（或者 `VITE_GIT_SHA`）注入页面。代码以后改了，旧页面上的链接还是指向它构建时的那一版，行号不会错。

`scripts/check_anchors.mjs` 在 CI 里检查三件事：生成文件没过期、前端引用的每个锚点都存在、每个锚点的起止行上确实还有那个注释。

## 每一步都配一段讲解视频

每个阶段旁边有「看讲解视频」，播放 `/videos/<part>.mp4`。part 的清单在 `video/parts.json`，和这份教程的章节一一对应。
视频不存在时显示「视频待生成」，不会报错。

视频是用 `video/record.mjs` 录的：它驱动真实的教学页面，按 `video/narration.json` 一段一段执行动作、给讲到的元素加红框，输出一个 webm 和每段开始时间的 `video/timeline.json`，配音和切片在仓库外做。

## 怎么证明界面真的能用？

`e2e/app.spec.ts` 用 Playwright 从界面点通四条流程：

1. 平台登录、用样例提交、看到 APPROVED、在「平台回调」页看到验签通过的回调。
2. 模糊扫描件进人审，审核员在另一个浏览器上下文里领取、要求重新提交，平台重新上传，第二轮 APPROVED。
3. 教学模式：阶段依次亮起、Lambda 的 CloudWatch 日志和 SQS 分组真的出现、当审核员点通过、回调完成、重放一条重复消息看到 `dedup:done`；源码链接的 href 和 `anchors.json` 一致，而且那一行真的有锚点注释。
4. 面试题标签页：点开一题能看到答案。

真实跑一次（`./scripts/demo.sh` 起着）：

```
$ cd e2e && npx playwright test
  5 passed
```

第一次跑的时候教学模式那条是红的：页面报 `v.replace is not a function`。`learn.py` 里写的是 `receipts and receipts[0]...`，列表为空时 Python 返回的是 `[]` 而不是 `None`，前端拿一个数组去当时间格式化，整个页面就崩了。后端改成显式的 `x if cond else None`，前端的时间格式化也加了类型判断。
这个 bug 只有从界面点才看得到：直接调 API 返回 200，数据也都在。

## 怎么跑到这一步

```bash
git checkout step-09
./scripts/demo.sh                      # 另开一个终端：
cd e2e && npm install && npx playwright test
```
