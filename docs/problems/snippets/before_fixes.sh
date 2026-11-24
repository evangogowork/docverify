#!/usr/bin/env zsh
# How the failure-control loop looked before the fix (docs/problems.md, q05). Not run anywhere.
# @learn:q05-before
for flags in "" "DOCVERIFY_UNSAFE_NO_CONDITIONAL_WRITES=1" "DOCVERIFY_UNSAFE_NO_DEDUP=1" \
             "DOCVERIFY_UNSAFE_NO_CONDITIONAL_WRITES=1 DOCVERIFY_UNSAFE_NO_DEDUP=1"; do
  echo "=== $flags"
  env $flags .venv/bin/pytest tests/test_step06_chaos.py -q | grep -E "passed|failed"
done
# @learn:end q05-before
