# 日常问题与解决

面试官常问：「你遇到过什么问题？怎么定位的？怎么解决的？」
下面十个问题，**九个是做这个项目时真的踩到的**（标「真实」），一个是这类系统在生产上的典型事故、用失败对照复现出来的（标「典型」）。
每题都有一段逐行高亮的讲解视频：`docs/videos/problems/<id>.mp4`，教学模式的「日常问题」标签页里也能看。

代码位置写成 `文件`（锚点名）。在教学模式页面里，「看源码」会跳到 GitHub 上固定 commit 的那几行；修复前的写法保存在 `docs/problems/snippets/`，同样有锚点。

## q01 S3 事件丢了，case 永远停在 UPLOADED（真实）

**现象**
```
E   AssertionError: case_eb8ee414a6584c66 stuck in UPLOADED, wanted {'QUEUED'}
```
Lambda 的 CloudWatch 日志里根本没有这个 case 的那一次调用。

**在哪里**：`docverify/bootstrap.py`（锚点 `lambda-deploy`），`docverify/worker.py`（锚点 `sweeper`）

**怎么定位**
- 假设一：Lambda 报错了。看 CloudWatch，前后几次调用都成功，排除。
- 假设二：事件根本没触发。LocalStack 日志里看到测试开头有一次 `UpdateFunctionCode`，紧接着换了一个新的 Lambda 运行容器（容器哈希从 `84e8…` 变成 `52e8…`）。
- 验证：bootstrap 每次都会重新部署代码，换容器的那几秒里到达的 S3 事件丢了。只有测试开头那一个 case 卡住，正好对上。

**怎么解决**：比较代码的 SHA256，没变就不重新部署（zip 用固定时间戳打包，哈希才稳定）；再加一个清扫任务，UPLOADED 超过三十秒就重新调用一次 Lambda。

**怎么证明修好了**：连跑两次 bootstrap，LocalStack 日志里 `UpdateFunctionCode` 出现零次；`tests/test_step03_intake.py` 在全量测试里稳定通过（修复前在全量里红）。

**面试怎么讲**：S 事件驱动的入队偶发丢 case；T 找到丢在哪一步；A 从 LocalStack 日志对上「重新部署换容器」的时间点，改成哈希不变不部署，并加了清扫任务兜底；R 不再丢，而且以后真丢了事件也能自动补上。

## q02 worker 一次预取十条，好好的文档进了死信（真实）

**现象**：混沌测试里有好好的文档最后是 FAILED，审计原因 `dead-letter: retries exhausted`。查投递记录：
```
{'receive_count': 1, ...}, {'receive_count': 2, ...}, ... {'receive_count': 8, ...}
```

**在哪里**：`docverify/worker.py`（锚点 `receive-batch`）

**怎么定位**
- 假设一：文档本身有问题。同样的文档单独跑是 APPROVED，排除。
- 假设二：杀进程太频繁。但每次只杀一个 worker，一份文档不该被杀八次。
- 验证：worker 一次收十条再串行处理。被杀时，手里十条全都算一次投递；排在后面的还在本地等着，就超过了可见性超时，被重投给别人。

**怎么解决**：每次只取能在可见性超时内做完的量，默认一条（`DOCVERIFY_RECEIVE_BATCH`）。

**怎么证明修好了**：`test_duplicates_and_kills_never_double_process` 断言每一份都是 APPROVED；修复前同样的测试里出现过 FAILED。

**面试怎么讲**：S 混沌测试里正常文档进了死信；T 区分是数据问题还是消费方式的问题；A 用投递次数和 worker 记录还原出「预取的消息在本地超时」，把批量改成一；R 混沌测试里不再有误伤，也顺便减少了重复投递。

## q03 别名索引让一家 Inc 满分匹配了另一家 LLC（真实）

**现象**
```
Acme Widgets Inc MatchResult(score=1.0, method='alias', account_value='Acme Widgets LLC')
```

**在哪里**：`docverify/match.py`（锚点 `alias-index`）

**怎么定位**
- 假设：编辑距离算错了。可 `method` 是 alias，根本没走编辑距离。
- 验证：别名索引的 key 是去掉后缀以后的名字，「acme widgets」两边一样，直接命中。

**怎么解决**：key 改成「核心名字 + 规范化后的后缀集合」，inc 统一成 incorporated、ltd 统一成 limited。

**怎么证明修好了**：`test_diacritics_abbreviations_and_suffixes` 断言「Acme Widgets Inc」对「Acme Widgets LLC」低于零点九；修复前是一点零。

**面试怎么讲**：S 名字匹配会把不同法律实体当成同一家；T 找到是哪一层放过去的；A 看匹配方法字段定位到别名索引，把后缀放进 key；R 不同实体不再自动通过，同名的别名照样一次命中。

## q04 评测门禁没过：带变音符号的名字更难自动通过（真实）

**现象**
```
| hispanic | 67% |   | nordic | 67% |
GATE: FAIL
  auto-approve gap between name groups 0.333
```

**在哪里**：`docverify/extract.py`（锚点 `ocr`），`docverify/match.py`（锚点 `normalize`）

**怎么定位**
- 假设一：匹配算法对这些名字不友好。看决策原因，是 `confidence:business_name`，不是匹配分数。
- 假设二：OCR 读错了。打出原始词和置信度：`('Seren', 40)`，Søren 被读成 Seren，置信度零点四。
- 验证：同一张图换成拉丁文字模型：`('Søren', 96)`。

**怎么解决**：OCR 改成 `eng+Latin`；归一化里补上 NFKD 拆不开的 ø、æ、ß、đ、ł。**没有调低阈值**，那等于放宽规则。

**怎么证明修好了**：`python -m evals.run` 门禁通过，分组差距降到零；修复前门禁是 FAIL。

**面试怎么讲**：S 评测集发现非英文名字的商家自动通过率低三分之一；T 找出偏差来自哪一层；A 从决策原因追到 OCR 置信度，换成拉丁文字模型，并且坚持不动阈值；R 分组差距从零点三三降到零，错误自动通过仍然是零。

## q05 对照组的开关没生效，测试「假绿」（真实）

**现象**：两个保护都关掉，结果 `10 passed`。可只关其中一个，就已经有测试会红。

**在哪里**：`scripts/failure_controls.sh`（锚点 `failure-controls`）

**怎么定位**
- 假设：两层保护互相兜底。但「只关条件写」时有测试红，两个都关不可能更绿。
- 验证：在同样的 shell 里让 Python 打印它看到的开关，两个都是 False。
- 原因：循环是在 zsh 里跑的，zsh 不对没加引号的变量分词，`env $flags` 只设了一个变量，名字就是第一个开关，值是「1 加一个空格加第二个开关」。

**怎么解决**：脚本固定用 bash；每一轮先让 Python 打印实际看到的开关值，写进输出。

**怎么证明修好了**：`docs/results/failure_controls.raw.txt` 里每一轮都有 `flags seen by python`，「两个都关」那一轮五个测试红。

**面试怎么讲**：S 对照组给出了不可能的结果；T 先确认测试本身是活的；A 让被测进程自己报告开关值，查到是 zsh 分词问题；R 对照组现在自带证据，不再有假绿。

## q06 混沌测试太宽松，关掉条件写也是绿的（真实）

**现象**：只关条件写，`test_duplicates_and_kills_never_double_process` 照样通过。

**在哪里**：`tests/test_step06_chaos.py`（锚点 `test-chaos`）

**怎么定位**
- 假设一：Redis 锁把并发全挡住了。部分对，但锁有 TTL，不可能永远挡住。
- 验证：查数据库，有些 case 抽取跑了两到四次，说明并发确实发生过；可这些 case 最后都是 FAILED 或 REJECTED。
- 原因：断言只要求「到了终态」，进死信的 FAILED、以及我手写的校验位不对、被正确驳回的 REJECTED，都算终态。真正会暴露重复提交的路径被这些失败吃掉了。

**怎么解决**：用合法的样例文档，断言每一份都是 APPROVED；另加一个确定性场景：抽取固定七秒半、锁两秒就过期，先断言「确实出现了并发副本」，再断言只提交一次。

**怎么证明修好了**：只关条件写时，「锁中途过期」那条测试变红，history 里同一步出现了两个 worker。

**面试怎么讲**：S 对照组显示测试抓不到我想抓的 bug；T 让测试能失败；A 收紧断言、加一个必然产生并发的场景，并在场景里断言「并发确实发生」；R 关掉条件写，测试马上红。

## q07 确认消息时报 InvalidParameterValue（真实）

**现象**
```
error:ClientError:An error occurred (InvalidParameterValue) when calling the DeleteMessage operation: Value ZjM5NTg2…
```

**在哪里**：`docverify/worker.py`（锚点 `ack`）

**怎么定位**
- 假设：队列地址错了。同一个 worker 的其它确认都成功，排除。
- 验证：出错的都是抽取很慢的那几条。处理期间可见性超时到了，消息被重投，旧的 receipt handle 失效。

**怎么解决**：确认失败且错误码是这两种时，返回「过期 receipt」而不是当成处理失败。持有新副本的 worker 看到 done 标记，会把它删掉。

**怎么证明修好了**：混沌日志里这类报错变成 `done+stale-receipt`，不再触发重试退避。

**面试怎么讲**：S 慢消息在确认时报错；T 区分真错误和正常的竞争；A 对上「只在慢消息上出现」推出 receipt 过期，按错误码区分处理；R 不再把做完的工作当失败重试。

## q08 二十个线程同时下结论，二十个都「成功」了（典型）

**现象**：关掉条件写跑并发测试：
```
E   AssertionError: assert (20 == 1)
```

**在哪里**：`docverify/states.py`（锚点 `conditional-write`）

**怎么定位**
- 这是生产上最常见的一类事故：两个进程读到同一个状态、各自写回，后写的覆盖先写的，还没有任何报错。
- 用对照开关复现：二十个线程在 barrier 上同时起跑，各写 APPROVED、REJECTED、IN_REVIEW，二十个全部返回成功，最终状态取决于谁最后写。

**怎么解决**：每次转移都带 `ConditionExpression: state = from 并且 round = 本轮`，条件不成立就是 Conflict，调用方不在别人的结果上再提交。

**怎么证明修好了**：同一个测试，开着条件写是一胜十九冲突，history 只有一条。

**面试怎么讲**：S 并发写状态会静默覆盖；T 保证一个 case 每一步只提交一次；A 用条件写做乐观并发控制，并用对照开关证明测试能抓到；R 二十个并发写只有一个成功，其余明确拿到冲突。

## q09 毒消息测试超时：退避没有上限（真实）

**现象**
```
E   AssertionError: case_a044df5a516c46c9 stuck in QUEUED, wanted {'FAILED'}
```
投递记录显示第八次在 19:20:00，之后再没动静。

**在哪里**：`docverify/worker.py`（锚点 `retry-backoff`）

**怎么定位**
- 假设：死信策略没生效。查队列属性，`maxReceiveCount` 是八，生效了。
- 验证：算一下退避：零点五秒的基数，第八次已经是六十四秒，第九次接收才会移进死信，超过了测试的一百二十秒。

**怎么解决**：退避加一个可配置的上限（`DOCVERIFY_RETRY_CAP`），测试里设成四秒。

**怎么证明修好了**：毒消息测试三十九秒通过，修复前超时失败。

**面试怎么讲**：S 有界重试的测试超时；T 确认是策略没生效还是太慢；A 查队列属性排除前者，算出指数退避的总时长，加上上限；R 坏消息能按时进死信，不会在队列里耗太久。

## q10 单跑能过，放进全量就失败：Scan 只读了第一页（真实）

**现象**：`test_two_reviewers_never_claim_the_same_case` 单独跑六个全过，全量跑就红：
```
+  where 2 = len(['case_f6f90a29b34f4c06', 'case_9f6b22f2db114b15'])
+  and   3 = len({'case_172b714c93f64e22', 'case_5db11cc9eda244e3', 'case_f6f90a29b34f4c06'})
```
十二个审核员同时领取，只领到两个，可明明有三个刚进人审的 case。

**在哪里**：`docverify/cases.py`（锚点 `scan-paginated`）

**怎么定位**
- 假设一：领取的条件写有 bug。单独跑能过，而且没有一次重复发放，排除。
- 假设二：堆里少了 case。堆是从 DynamoDB 刷新来的，刷新用的是 Scan。
- 验证：全量测试之前表里已经有几千个 case。DynamoDB 一次 Scan 最多返回一兆字节，新建的那几个 case 不在第一页，刷新根本看不到它们。

**怎么解决**：Scan 改成分页读完；按状态过滤、只取需要的字段。限制里写明生产上应该用 state 上的 GSI。

**怎么证明修好了**：同一个测试在全量里通过；修复前全量里红、单跑绿。

**面试怎么讲**：S 一个测试只在全量里失败；T 找出和数据量有关的那个差别；A 先存下完整输出，再按「领取逻辑、堆的内容、刷新的来源」一层层排除，定位到 Scan 没分页；R 修好以后与表的大小无关，也写进了「上生产要换成 GSI」。
