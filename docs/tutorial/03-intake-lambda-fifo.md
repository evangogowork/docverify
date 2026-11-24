# 03 S3 触发 Lambda，按账户进 SQS FIFO

> 视频：[p03-intake.mp4](../videos/p03-intake.mp4) · tag：`step-03`

## 这一章解决什么问题？

上传接口不该自己去做 OCR：一天几万份文件，上传请求不能等抽取跑完。
所以在上传和处理之间放一个队列。谁把消息放进去？让 S3 自己通知：文件落地，触发一个 Lambda，由它入队。

## 为什么是 FIFO，为什么按账户分组？

同一个账户可能连着交两份材料（比如先交了一份，又补了一份）。它们必须按顺序处理，否则旧的结论可能盖掉新的。
但不同账户之间没必要排队。

SQS FIFO 的 `MessageGroupId` 正好是这个语义：**同一组严格有序，不同组并行**。
组 id 就用 account_id。worker 想加几个加几个，同一账户永远一次只有一条在处理。

## 假设：S3 事件重放一次，会不会入队两条？

不会，有两层保护：

1. Lambda 先做条件转移 `UPLOADED → QUEUED`；重放的那次会拿到 Conflict。看到 case 已经是 QUEUED，它照样再发一次消息（防止上一次「转移成功但发送失败」）。
2. 再发的那条消息用的是确定性的 `MessageDeduplicationId = case_id-r轮次`，SQS 在五分钟窗口内会直接丢掉它。

## 真实跑一次

上传一份文件，两秒后 case 变成 QUEUED。从队列里收到的消息属性是：

```json
"MessageGroupId": "acct_1001",
"MessageDeduplicationId": "case_f93df84816fb4d48-r1",
"SequenceNumber": "15423619209413787648"
```

审计里多了一行，actor 是 Lambda：

```
[('NEW', 'UPLOADED', 'api'), ('UPLOADED', 'QUEUED', 'lambda:intake')]
```

这个 Lambda 是真的在 LocalStack 里跑的：`docker ps` 能看到一个 `public.ecr.aws/lambda/python:3.11` 容器。
它挂在 compose 网络里（`LAMBDA_DOCKER_NETWORK`），所以能直接连 MySQL 写审计。

## 一个踩过的坑

测试刚开始的时候，bootstrap 会重新部署 Lambda 代码。部署的那一瞬间，LocalStack 会换掉运行容器，这期间到达的 S3 事件**丢了**，case 永远停在 UPLOADED。

修了两处：

- bootstrap 先比较代码的 SHA256，没变就不重新部署（zip 打包用固定时间戳，哈希才稳定）。
- 第 06 章加了一个清扫任务：UPLOADED 超过三十秒的 case，重新调用一次 Lambda。

事件驱动的系统里，「事件可能丢」要当成常态来设计。

## 代码

- `lambdas/intake/handler.py`（锚点 `@learn:lambda-intake`）
- 资源创建：`docverify/bootstrap.py`（锚点 `@learn:s3-notification`）

## 怎么跑到这一步

```bash
git checkout step-03
.venv/bin/python -m docverify.bootstrap && .venv/bin/pytest tests/test_step03_intake.py
```
