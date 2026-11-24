import pytest

from docverify import bootstrap


@pytest.fixture(scope="session", autouse=True)
def aws_resources():
    bootstrap.main()
    yield
