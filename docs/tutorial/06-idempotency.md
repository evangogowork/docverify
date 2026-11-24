# 06 幂等和故障：重复消息、杀进程、超时

> 视频：[p06-idempotency.mp4](../videos/p06-idempotency.mp4) · tag：`step-06`

## 这一章解决什么问题？

SQS 是「至少投递一次」：同一条消息可能被收到两次。worker 会被杀，会卡住，网络会超时。
目标是一句话：**无论发生什么，一个 case 的每一步只提交一次，而且最终走到正确的结论。**

## 三层保护，各管一段

| 层 | 在哪 | 挡住什么 |
|---|---|---|
| FIFO message group | SQS | 同一账户的消息一次只处理一条，重放的副本排在后面 |
| Redis `done` 标记 + 处理锁 | `docverify/dedup.py` | 做完的副本直接丢；正在处理的副本退让，不重复跑 OCR |
| DynamoDB 条件写 | `states.transition()` | 真的有两个 worker 同时做同一步时，只有一个能提交 |

Redis 是**省力层**：它让重复的工作根本不发生。
条件写是**正确性层**：Redis 锁只是一个有 TTL 的租约，worker 停顿超过 TTL，锁就没了，这时只有条件写能兜住。

另外还有：

- **有界重试**：处理失败不确认，用 `ChangeMessageVisibility` 做指数退避（有上限）；收到次数超过 `maxReceiveCount`，SQS 自己把消息移进死信队列，worker 把 case 标成 FAILED，原因写进审计。
- **清扫任务**（锚点 `@learn:sweeper`）：UPLOADED 超过三十秒的 case 重新调用一次 Lambda，补上丢掉的 S3 事件；同时跑 `reconcile()` 补审计。用 Redis `SET NX EX` 保证同一时刻只有一个 worker 在扫。

## 假设：随机杀 worker、重放消息、让一部分抽取慢过可见性超时，每一步仍然只提交一次

`tests/test_step06_chaos.py` 里有四个场景：

1. **混沌**：五个 worker，十六份真实文档，每份再重放两条重复消息；抽取耗时随机 0.2～8 秒（可见性超时是 6 秒，所以有些消息会在第一个 worker 还没做完时被投给第二个）；二十秒里每隔一秒左右 `SIGKILL` 一个 worker 并重启。
   断言：每个 `(case, 轮次, from, to)` 在审计里只有一行；history 和审计一一对应；**每份文档最后都是 APPROVED**，没有一份进死信。
2. **锁中途过期**：抽取固定 7.5 秒，锁 TTL 2 秒，六个 worker。这一定会让两个 worker 同时做同一步。测试先断言「确实出现了并发副本」（证明场景是活的），再断言没有重复提交。
3. **副本不重做抽取**：抽取 8 秒，五个 worker。断言每个 case 只跑了一次 OCR。
4. **毒消息**：一张坏 PNG，每次都抛异常。断言它被收了 `maxReceiveCount` 次，然后 case 进 FAILED，审计原因是 `dead-letter: retries exhausted`。

## 能失败的对照

`scripts/failure_controls.sh` 把每层保护单独关掉，跑同一组测试。实测结果：

| 关掉的保护 | 变红的测试 |
|---|---|
| 无（全部打开） | 无，十个全过 |
| 条件写 | `test_concurrent_decisions_exactly_one_wins`（二十个线程全「成功」）、`test_stale_from_state_is_a_conflict`、`test_lock_expiring_mid_extraction_still_commits_once` |
| Redis 去重 | `test_concurrent_copies_do_not_redo_extraction`（同一份文档跑了两次 OCR） |
| 两个都关 | 上面全部，再加 `test_duplicates_and_kills_never_double_process`（每一步都被提交两次） |

锁中途过期那个场景，关掉条件写时的真实输出（同一个 case 的 history）：

```
('QUEUED','EXTRACTED','worker:exp-0'), ('EXTRACTED','VALIDATED','worker:exp-0'), ('VALIDATED','APPROVED','worker:exp-0'),
('QUEUED','EXTRACTED','worker:exp-1'), ('EXTRACTED','VALIDATED','worker:exp-1'), ('VALIDATED','APPROVED','worker:exp-1')
```

读法：

- **只关条件写**：直接并发下结论的测试马上红（二十个线程全都「成功」）。锁中途过期的场景也红了：两个 worker 各提交了一遍抽取、校验和决策。普通混沌场景大多还是绿的，因为 Redis 锁和 FIFO 顺序把并发挡在了前面。这正说明 Redis 不能当正确性保证：它只在租约有效的时候管用。
- **只关 Redis 去重**：状态仍然正确（条件写兜住了），但「副本不重做抽取」红了：同一份文档跑了两次 OCR。
- **两个都关**：重复提交到处都是。

## 三个我踩过的坑

1. **测试太宽松。** 第一版混沌测试只断言「case 到了某个终态」。结果把条件写关掉也是绿的。查数据库才发现，很多 case 根本是进了死信（FAILED），也算「终态」；还有一些是我手写的注册号校验位本来就不对，被正确地驳回了。改成用合法样例、断言每一份都 APPROVED 之后，测试才真的能区分对错。
2. **worker 一次预取十条。** 混沌测试里有好好的文档进了死信。原因是 worker 一次收十条、再一条条串行处理：排在后面的消息在本地等着就超过了可见性超时，被重投给别人；worker 被杀时，手里十条全都白白耗掉一次投递次数。改成每次只取一条（`DOCVERIFY_RECEIVE_BATCH`，默认一）。
3. **对照组的开关没生效。** 第一次跑「两个都关」用的是 zsh 循环 `env $flags pytest`。zsh 不会拆分没加引号的变量，于是两个开关变成了一个名字很怪的变量，两个保护其实都开着，结果全绿。现在脚本用 bash，而且每一轮先让 Python 打印它实际看到的开关值。

## 代码

- `docverify/dedup.py`（锚点 `@learn:dedup`）
- `docverify/worker.py`（锚点 `@learn:worker-handle`、`@learn:dlq`、`@learn:sweeper`）
- `tests/test_step06_chaos.py`（锚点 `@learn:test-chaos`）

## 怎么跑到这一步

```bash
git checkout step-06
.venv/bin/python -m docverify.bootstrap
.venv/bin/pytest tests/test_step06_chaos.py      # 约三分钟
./scripts/failure_controls.sh                    # 约十分钟
```
