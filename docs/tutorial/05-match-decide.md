# 05 匹配和决策：谁有权下结论

> 视频：[p05-decide.mp4](../videos/p05-decide.mp4) · tag：`step-05`

## 这一章解决什么问题？

两个问题：

1. 文档上写的「Nguyen Van An Trading Co.」，是不是账户上的「Nguyễn Văn An Trading Company」？
2. 有了检查结果和匹配分数，**谁有权给账户下结论**？

## 匹配：先归一化，再比较

归一化做了这些事：

- 去掉变音符号：Nguyễn → nguyen
- 统一缩写：Co → company，St → street，& → and
- 把法律后缀单独拿出来：inc → incorporated，ltd → limited
- 统一常见的音译：Muhammad / Mohamed → mohammed

然后按顺序比较：

1. **别名索引**：一张哈希表，key 是归一化后的名字加上后缀集合，value 是账户 id。DBA 名和已知的音译写法放在这里，O(1) 精确命中。
2. **编辑距离比例**：`1 - levenshtein / 较长的长度`
3. **token-set 相似度**：不在乎词序和重复。「Wei Zhang Imports」和「Zhang Wei Imports」得 1.0。

两个后缀都存在但不一样（LLC 和 Inc），扣 0.15 分：它们是不同的法律实体。

## 一个当场抓到的 bug

第一版的别名索引只用了去掉后缀的名字做 key。结果：

```
Acme Widgets Inc  MatchResult(score=1.0, method='alias')     # 账户是 Acme Widgets LLC
```

一家 Inc 被当成了另一家 LLC，而且是满分。修法是把规范化之后的后缀集合也放进 key。修完再跑：

```
Acme Widgets Inc  0.85 edit      # 低于 0.90，进人审
Acme Widgets      1.0  edit      # 文档上没写后缀，可以
```

## 决策：一条规则

**不确定的 AI 输出不能单独决定账户状态。** 落到代码里是三句话：

- 自动通过：所有检查都通过，商家名匹配 ≥ 0.90，地址匹配 ≥ 0.85。
- 自动驳回：只有当一条确定性规则失败、而且那个字段是以 ≥ 0.90 的置信度读出来的时候。比如校验位不对、已过期。这是关于文档本身的事实，不是模型在猜。
- 三个以上必填字段缺失：要求重新提交（读不出来）。
- 其余一律进人审，并算一个风险分，给第 07 章的队列排序用。

地址里的门牌号和邮编必须完全一致，相似度再高也不能盖过它们。

## 假设：随便组合检查结果，策略也永远不会在「有一项失败」时自动通过

`test_policy_never_auto_approves_uncertain_output` 用 hypothesis 生成五百组随机的检查结果和匹配分数，断言两件事：

- 只要结论是 APPROVED，所有检查都通过，而且两个匹配分都过线；
- 只要结论是 REJECTED，一定有一条以高置信度读出的确定性规则失败。

## 真实跑一次

worker 端到端跑三份材料：

```
干净扫描件              → APPROVED
校验位被改的 PDF        → REJECTED   (rule:registration_checksum, confidence 0.98)
低分辨率扫描件          → IN_REVIEW  (risk 83)
```

## 代码

- `docverify/match.py`（锚点 `@learn:normalize`、`@learn:similarity`、`@learn:alias-index`）
- `docverify/decide.py`（锚点 `@learn:decide`）

## 怎么跑到这一步

```bash
git checkout step-05
.venv/bin/python -m docverify.bootstrap && .venv/bin/pytest tests/test_step05_match_decide.py
```
