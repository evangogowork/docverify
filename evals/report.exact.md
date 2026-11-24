# Evaluation report (exact matcher, 147 documents, 2026-11-24T14:38:41)

| category | n | decision accuracy | incorrect auto-approvals | auto-approve rate |
|---|---|---|---|---|
| clean | 24 | 83.3% | 0 | 83.3% |
| poor_quality | 48 | 100.0% | 0 | 0.0% |
| altered | 48 | 100.0% | 0 | 0.0% |
| unsupported_format | 15 | 100.0% | 0 | 0.0% |
| demographic | 12 | 0.0% | 0 | 0.0% |

Auto-match rate on readable genuine documents: **55.6%**

| name group | auto-approve rate |
|---|---|
| anglo | 67% |
| arabic | 67% |
| chinese | 67% |
| hispanic | 33% |
| indian | 67% |
| japanese | 33% |
| nigerian | 67% |
| nordic | 67% |
| polish | 67% |
| russian | 67% |
| vietnamese | 33% |

Misses:

- clean: acct_1002:clean->IN_REVIEW, acct_1005:clean->IN_REVIEW, acct_1006:clean->IN_REVIEW, acct_1012:clean->IN_REVIEW
- poor_quality: none
- altered: none
- unsupported_format: none
- demographic: acct_1001:variant_name->IN_REVIEW, acct_1002:variant_name->IN_REVIEW, acct_1003:variant_name->IN_REVIEW, acct_1004:variant_name->IN_REVIEW, acct_1005:variant_name->IN_REVIEW, acct_1006:variant_name->IN_REVIEW, acct_1007:variant_name->IN_REVIEW, acct_1008:variant_name->IN_REVIEW, acct_1009:variant_name->IN_REVIEW, acct_1010:variant_name->IN_REVIEW, acct_1011:variant_name->IN_REVIEW, acct_1012:variant_name->IN_REVIEW
