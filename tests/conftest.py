import os

# Short timeouts so retry/redelivery scenarios finish in seconds. Set before anything reads settings().
os.environ.setdefault("DOCVERIFY_VISIBILITY_TIMEOUT", "6")
os.environ.setdefault("DOCVERIFY_SEED_DEMO", "1")
os.environ.setdefault("DOCVERIFY_RETRY_BASE", "0.5")
os.environ.setdefault("DOCVERIFY_RETRY_CAP", "4")
os.environ.setdefault("DOCVERIFY_STUCK_AFTER", "20")
# Chaos tests SIGKILL workers mid-message; each kill burns a receive, so allow more than prod-like 4.
os.environ.setdefault("DOCVERIFY_MAX_RECEIVES", "8")

import pytest  # noqa: E402

from docverify import bootstrap  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def aws_resources():
    bootstrap.main()
    yield
