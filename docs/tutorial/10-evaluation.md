# 10 评测集和发布门禁

> 视频：[p10-eval.mp4](../videos/p10-eval.mp4) · tag：`step-10`

## 这一章解决什么问题？

单元测试证明「代码照我想的那样运行」。但我想的对不对？
模糊的图会不会被误判通过？被改过的执照能不能抓住？名字是越南语、波兰语、丹麦语的商家，会不会比英文名字更难自动通过？

这些问题要用一组**有标注的、刻意刁钻的输入**来回答，而且每次发布前都要回答一遍。

## 评测集长什么样？

`evals/run.py` 用脚本生成，十二个账户乘以五类，一共一百四十七份：

| 类别 | 内容 | 可接受的结论 |
|---|---|---|
| clean | 干净扫描件、PDF | APPROVED |
| poor_quality | 模糊、噪点、低分辨率、旋转 | IN_REVIEW 或 RESUBMIT_REQUESTED（**不能**自动通过） |
| altered | 校验位被改、已过期 | REJECTED |
| altered | 名字不对、地址不对 | IN_REVIEW 或 REJECTED |
| unsupported_format | docx、gif、heic、没有文字层的 PDF | RESUBMIT_REQUESTED |
| demographic | 同一家商家的另一种写法：去掉变音符号、名字倒序、音译、后缀写全 | APPROVED |

跑的是真实的流水线（OCR、校验、匹配、决策），只是不经过 AWS，所以几十秒就跑完，适合放进 CI。

## 门禁

`evals/thresholds.json`：

- **错误自动通过必须是零。** 这是最重要的一条。
- 每类的决策准确率有下限。
- 不同名字来源之间，干净文档的自动通过率差距不能超过 0.25。

任何一条不满足，`python -m evals.run` 就以非零退出，CI 变红。

## 假设：门禁第一次就能过

没过。第一次跑的真实输出：

```
| clean | 24 | 91.7% | 0 | 91.7% |
| poor_quality | 48 | 100.0% | 0 | 0.0% |
| altered | 48 | 100.0% | 0 | 0.0% |
| unsupported_format | 15 | 100.0% | 0 | 0.0% |
| demographic | 12 | 100.0% | 0 | 100.0% |

Auto-match rate on readable genuine documents: 94.4%
| hispanic | 67% |   | nordic | 67% |      （其余九组都是 100%）
Misses: clean: acct_1005:clean->IN_REVIEW, acct_1010:clean->IN_REVIEW
GATE: FAIL
  auto-approve gap between name groups 0.333
```

两个西班牙语和北欧的干净扫描件没能自动通过。查 OCR 的原始输出：

```
acct_1005 eng [('José', 95), ('Garcia', 90)]           # García 的 í 丢了，Construcción 读成 Construccién，置信度 0.78
acct_1010 eng [('Seren', 40), ('Ostergaard', 87)]      # Søren 读成 Seren，置信度 0.40
```

英文 OCR 模型不认识 ø、í、ă 这些字母，带它们的名字置信度掉到阈值以下，于是进了人审。
**这正是评测集该抓的偏差**：同样干净的文档，名字不是英文的商家更难自动通过。

## 怎么修？不能调低阈值

调低名字的置信度阈值，等于放宽了规则：别的读错的名字也会混过去。
真正的问题在 OCR，所以修 OCR：

1. 加上 Tesseract 的拉丁文字模型（`script/Latin`），和英文模型一起用：`lang = eng+Latin`。同一张图：

   ```
   acct_1010 eng+Latin [('Søren', 96), ('Østergaard', 96)]
   acct_1005 Latin     [('José', 96), ('García', 95)]
   ```

2. 归一化里补上 NFKD 拆不开的字母：ø → o、æ → ae、ß → ss、đ → d、ł → l。

修完再跑：

| 类别 | 份数 | 决策准确率 | 错误自动通过 | 自动通过率 |
|---|---|---|---|---|
| clean | 24 | 100.0% | 0 | 100.0% |
| poor_quality | 48 | 100.0% | 0 | 0.0% |
| altered | 48 | 100.0% | 0 | 0.0% |
| unsupported_format | 15 | 100.0% | 0 | 0.0% |
| demographic | 12 | 100.0% | 0 | 100.0% |

可读的真实文档（干净 + 名字变体，三十六份）自动通过率 **100.0%**，十一个名字分组全部 100%，分组差距 0，错误自动通过 0，门禁 PASS。

> 这个 100% 是在**仓库自己生成的合成文档**上测的，文档是我按已知的规则造的，所以它说明的是「这些已知的写法差异都被处理了」，不说明真实世界的准确率。

## 朴素匹配作对照

同一份评测集，把名字匹配换成「忽略大小写的完全相等」：

| 类别 | 份数 | 决策准确率 | 错误自动通过 | 自动通过率 |
|---|---|---|---|---|
| clean | 24 | 83.3% | 0 | 83.3% |
| poor_quality | 48 | 100.0% | 0 | 0.0% |
| altered | 48 | 100.0% | 0 | 0.0% |
| unsupported_format | 15 | 100.0% | 0 | 0.0% |
| demographic | 12 | 0.0% | 0 | 0.0% |

朴素匹配下，可读真实文档的自动通过率是 **55.6%**（完整匹配器 100.0%），名字变体那一类全部进了人审，错误自动通过同样是 0。门禁在朴素匹配下 FAIL（分组差距 0.333）。

拒绝规则一条没改，变的只是名字匹配。

## 代码

- `evals/run.py`（锚点 `eval-run`、`eval-gate`）
- `evals/thresholds.json`
- `scripts/fetch_tessdata.sh`

## 怎么跑到这一步

```bash
git checkout step-10
./scripts/fetch_tessdata.sh
.venv/bin/python -m evals.run                 # 写 evals/report.json 和 report.md
.venv/bin/python -m evals.run --matcher exact # 朴素基线
```
