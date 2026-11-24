#!/usr/bin/env bash
# Run the correctness tests with each protection switched off, to show the tests can fail.
# Expected: everything green with protections on; specific tests red with each one off.
# (bash on purpose: zsh does not word-split "$flags", which silently turns a two-flag run into a no-flag run.)
set -uo pipefail
cd "$(dirname "$0")/.."
TESTS="tests/test_step02_states.py tests/test_step06_chaos.py"
# @learn:failure-controls
for flags in "" "DOCVERIFY_UNSAFE_NO_CONDITIONAL_WRITES=1" "DOCVERIFY_UNSAFE_NO_DEDUP=1" \
             "DOCVERIFY_UNSAFE_NO_CONDITIONAL_WRITES=1 DOCVERIFY_UNSAFE_NO_DEDUP=1"; do
  echo "=== ${flags:-all protections on}"
  # shellcheck disable=SC2086
  env $flags .venv/bin/python -c "from docverify.config import settings as s; x=s(); print('  flags seen by python: no_conditional_writes=%s no_dedup=%s' % (x.unsafe_no_conditional_writes, x.unsafe_no_dedup))"
  # shellcheck disable=SC2086
  env $flags .venv/bin/pytest $TESTS -p no:warnings 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/^/  /'
done
# @learn:end failure-controls
