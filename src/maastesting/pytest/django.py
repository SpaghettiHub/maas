import os
import pathlib

from django.db import reset_queries, transaction
import pytest

from maasserver.djangosettings import development
from maasserver.sqlalchemy import service_layer
from maasserver.testing.resources import close_all_connections
from maasserver.utils.orm import enable_all_database_connections
from maastesting.pytest.database import cluster_stash


def read_test_data(filename: str) -> bytes:
    with open(
        pathlib.Path(f"src/maastesting/pytest/test_data/{filename}"), "rb"
    ) as f:
        return f.read()


@pytest.hookimpl(tryfirst=False)
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allow_transactions: Allow a test to use transaction.commit()",
    )
    config.addinivalue_line(
        "markers",
        "recreate_db: re-create database before each test run",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args):
    if os.environ.get("DJANGO_SETTINGS_MODULE") is None:
        os.environ["DJANGO_SETTINGS_MODULE"] = (
            "maasserver.djangosettings.development"
        )

    import django
    from django.conf import settings

    database = settings.DATABASES["default"]
    database["NAME"] = "no_such_db"
    django.setup()


@pytest.fixture
def ensuremaasdjangodb(request, ensuremaasdb, pytestconfig, worker_id):
    from maasserver.djangosettings import development

    database = development.DATABASES["default"]
    database["NAME"] = ensuremaasdb
    yield
    database["NAME"] = "no_such_db"


@pytest.fixture
def maasdb(ensuremaasdjangodb, request, pytestconfig):
    enable_all_database_connections()
    # reset counters
    reset_queries()
    # Start a transaction.
    transaction.set_autocommit(False)
    allow_transactions = (
        request.node.get_closest_marker("allow_transactions") is not None
    )
    service_layer.init()

    if allow_transactions:
        yield
        close_all_connections()
        # Since transactions are allowed, we assume a commit has been
        # made, so we can't simply do rollback to clean up the DB.
        dbname = development.DATABASES["default"]["NAME"]
        cluster = pytestconfig.stash[cluster_stash]
        cluster.dropdb(dbname)
    else:
        # Wrap the test in an atomic() block in order to prevent commits.
        with transaction.atomic():
            yield
        # Since we don't allow commits, we can safely rollback and don't
        # have to recreate the DB.
        transaction.rollback()
        close_all_connections()

    service_layer.close()


@pytest.fixture
def factory(maasdb, mocker):
    mocker.patch("maasserver.utils.orm.post_commit_hooks")
    mocker.patch("maasserver.utils.orm.post_commit_do")

    # Local imports from maasserver so that pytest --help works
    from maasserver.testing.factory import factory as maasserver_factory

    return maasserver_factory


@pytest.fixture
def admin(factory):
    return factory.make_admin()


@pytest.fixture
def maas_user(factory):
    return factory.make_User()


@pytest.fixture
def api_client(maas_user):
    # Local imports from maasserver so that pytest --help works
    from maasserver.models.user import get_auth_tokens
    from maasserver.testing.testclient import MAASSensibleOAuthClient

    return MAASSensibleOAuthClient(
        user=maas_user, token=get_auth_tokens(maas_user)[0]
    )


@pytest.fixture
def admin_api_client(admin):
    # Local imports from maasserver so that pytest --help works
    from maasserver.models.user import get_auth_tokens
    from maasserver.testing.testclient import MAASSensibleOAuthClient

    return MAASSensibleOAuthClient(user=admin, token=get_auth_tokens(admin)[0])
