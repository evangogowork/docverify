# 02 状态机：只让合法的转移提交

> 视频：[p02-state.mp4](../videos/p02-state.mp4) · tag：`step-02`

## 这一章解决什么问题？

一个 case 会被很多进程碰：API、Lambda、好几个 worker、审核员。
如果谁都能直接写 `state = APPROVED`，两个进程同时改，后写的就会覆盖先写的，而且没有人知道发生过什么。

所以要两样东西：

- 一张**合法转移表**：`UPLOADED → QUEUED` 可以，`APPROVED → UPLOADED` 不行。
- 一个**只在「我读到的状态还没变」时才提交**的写法。

## 假设：二十个线程同时给同一个 case 下结论，会怎样？

只有一个能成功，其余十九个都拿到 Conflict。
这不是靠锁做到的，是靠 DynamoDB 的条件写：`ConditionExpression: state = :from AND round = :round`。

## 真实跑一次

`tests/test_step02_states.py::test_concurrent_decisions_exactly_one_wins` 让二十个线程在 barrier 上同时起跑，各自试 APPROVED / REJECTED / IN_REVIEW：

```
wins = 1, conflicts = 19, len(history) == 1, audit rows == 1
```

把条件写关掉（`DOCVERIFY_UNSAFE_NO_CONDITIONAL_WRITES=1`）再跑同一个测试：

```
E   AssertionError: assert (20 == 1)
```

二十个全都「成功」了，最后的状态取决于谁最后写。这就是测试能失败的证据。

## 审计为什么放 MySQL，又为什么不怕丢？

审计要能按时间、按 actor、按原因查，放关系库合适。
但 DynamoDB 和 MySQL 之间没有分布式事务。进程恰好死在两次写中间怎么办？

做法是：**同一次条件写里，往 case 自己的 `history` 列表追加一条**（带唯一的 `write_id`）。
这样 DynamoDB 里的 history 才是权威记录，MySQL 只是它的投影。
`states.reconcile()` 把 history 里有、MySQL 里没有的行补上，`write_id` 唯一，所以补多少次都只有一行。

`test_reconcile_backfills_missing_audit` 模拟了「提交后、写审计前崩溃」：第一次 reconcile 补 1 行，第二次补 0 行。

## 代码

- 转移表：`docverify/states.py` 的 `TRANSITIONS`（锚点 `@learn:state-machine`）
- 条件写：`transition()`（锚点 `@learn:transition`）

## 怎么跑到这一步

```bash
git checkout step-02
.venv/bin/python -m docverify.bootstrap && .venv/bin/pytest tests/test_step02_states.py
```
