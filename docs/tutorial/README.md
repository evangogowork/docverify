# docverify 分章教程

从一个最小能跑的版本开始，一章加一个能力。每一章对应一个 git tag，可以 checkout 到那一步亲手跑。

| 章 | tag | 这一章解决什么 | 视频 |
|---|---|---|---|
| [01 上传](01-upload.md) | `step-01` | 文件进 S3，case 进 DynamoDB | [p01-upload](../videos/p01-upload.mp4) |
| [02 状态机](02-state-machine.md) | `step-02` | 只让合法的状态转移提交，并留下审计 | [p02-state](../videos/p02-state.mp4) |
| [03 S3 触发 Lambda，进 FIFO](03-intake-lambda-fifo.md) | `step-03` | 上传和处理解耦，同一账户有序 | [p03-intake](../videos/p03-intake.mp4) |
| [04 抽取和校验](04-extract-validate.md) | `step-04` | 读出字段，每个字段带置信度 | [p04-extract](../videos/p04-extract.mp4) |
| [05 匹配和决策](05-match-decide.md) | `step-05` | 文档上的商家是不是账户上的商家；谁有权下结论 | [p05-decide](../videos/p05-decide.mp4) |
| [06 幂等和故障](06-idempotency.md) | `step-06` | 重复消息、杀进程、超时都不会处理两次 | [p06-idempotency](../videos/p06-idempotency.mp4) |
| [07 人审](07-human-review.md) | `step-07` | 不确定的交给人，按风险和等待时间排队 | [p07-review](../videos/p07-review.mp4) |
| [08 回调](08-callbacks.md) | `step-08` | 四个平台共用一份契约，签名、重试 | [p08-callback](../videos/p08-callback.mp4) |
| [09 前端和教学模式](09-frontend-learn-mode.md) | `step-09` | 把每一步摊开给人看 | [p09-learn](../videos/p09-learn.mp4) |
| [10 评测集和发布门禁](10-evaluation.md) | `step-10` | 证明它在难的输入上也不乱下结论 | [p10-eval](../videos/p10-eval.mp4) |

每章的写法都一样：先说这一章要解决的问题，提出一个假设，然后放一次真实运行的输出，最后才看代码。

跑任何一章之前，先把依赖服务起起来：

```bash
docker-compose up -d            # LocalStack 4.9 / MySQL 8.4 / Redis 7
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m docverify.bootstrap
```
