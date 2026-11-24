# 01 上传：先让一份文件有地方落脚

> 视频：[p01-upload.mp4](../videos/p01-upload.mp4) · tag：`step-01`

## 这一章解决什么问题？

平台要交一份营业执照。在做任何「验证」之前，这份文件得先有个安全的地方放，系统也得有一条记录说「有这么一个 case」。
所以第一步只做两件事：文件进 S3，case 进 DynamoDB。

## 为什么文件和 case 分两处放？

文件是大块的、只写一次的二进制，适合放对象存储。
case 是小的、会反复改状态的记录，适合放 key-value 库。
把它们分开放，后面每一步只改 case，不用碰文件。

## 假设：同一个请求重试两次，会不会建出两个 case？

不会。case_id 是服务端生成的，建 case 用的是 `attribute_not_exists(case_id)` 条件写。
就算同一个 id 被写两次，第二次也会被 DynamoDB 拒掉，不会覆盖第一次。

## 真实跑一次

```bash
curl -s -F account_id=acct_1001 -F doc_type=business_license -F file=@lic.txt localhost:8501/v1/cases
```

```json
{"case_id":"case_aeef9e1cdaec4cf0","state":"UPLOADED","s3_key":"acct_1001/case_aeef9e1cdaec4cf0/r1/lic.txt"}
```

注意 key 的形状：`账户/case/轮次/文件名`。
轮次（r1）现在看着多余，到第 07 章要求重新提交的时候就用上了：同一个 case 的第二份文件放在 r2 下面，不会覆盖第一份。

## 代码怎么写？

接口在 `docverify/api/main.py` 的 `create_case`（锚点 `@learn:upload`）。顺序是故意的：

1. 先在 DynamoDB 里建 case。
2. 再往 S3 放对象。

为什么不反过来？到第 03 章，S3 一落地就会触发 Lambda。
如果先放 S3，Lambda 可能在 case 还不存在的时候就跑起来了。

## 怎么跑到这一步

```bash
git checkout step-01
docker-compose up -d && .venv/bin/python -m docverify.bootstrap
.venv/bin/pytest tests/test_step01_upload.py
```
