# Copyright 2013-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).


from collections import namedtuple
import http.client
from unittest.mock import call, Mock, sentinel

from django.core.exceptions import PermissionDenied
from django.urls import reverse
from piston3.authentication import NoAuthentication

from maasserver.api.doc import get_api_description
from maasserver.api.support import (
    admin_method,
    AdminRestrictedResource,
    deprecated,
    Emitter,
    OperationsHandlerMixin,
    OperationsResource,
    RestrictedResource,
)
from maasserver.models.config import Config, ConfigManager
from maasserver.testing.api import APITestCase
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maastesting.testcase import MAASTestCase


class TestEmitterOnlyJSON(MAASTestCase):
    def test_emitters(self):
        self.assertEqual(Emitter.EMITTERS.keys(), {"json"})


class StubHandler:
    """A stub handler class that breaks when called."""

    def __call__(self, request):
        raise AssertionError("Do not call the stub handler.")


class TestOperationsResource(APITestCase.ForUser):
    def test_type_error_is_not_hidden(self):
        # This tests that bug #1228205 is fixed (i.e. that a
        # TypeError is properly reported and not swallowed by
        # piston).

        # Create a valid configuration item.
        name = "maas_name"
        value = factory.make_string()
        Config.objects.set_config(name, value)

        # Patch ConfigManager.get_config so that it will raise a
        # TypeError exception.
        def mock_get_config(config):
            if config == name:
                raise TypeError()

        self.patch(
            ConfigManager, "get_config", Mock(side_effect=mock_get_config)
        )
        self.become_admin()
        response = self.client.get(
            reverse("maas_handler"), {"op": "get_config", "name": name}
        )
        self.assertEqual(
            http.client.INTERNAL_SERVER_ERROR,
            response.status_code,
            response.content,
        )

    def test_api_hash_is_set_in_headers(self):
        Config.objects.set_config("maas_name", factory.make_name("name"))
        self.become_admin()
        response = self.client.get(
            reverse("maas_handler"), {"op": "get_config", "name": "maas_name"}
        )
        self.assertEqual(
            response["X-MAAS-API-Hash"], get_api_description()["hash"]
        )

    def test_call_op_in_path(self):
        Config.objects.set_config("maas_name", factory.make_name("name"))
        self.become_admin()
        response = self.client.get(
            reverse("maas_handler-op-get_config"), {"name": "maas_name"}
        )
        self.assertEqual(http.client.OK, response.status_code)

    def test_authenticated_is_False_when_no_authentication_provided(self):
        resource = OperationsResource(StubHandler)
        self.assertFalse(resource.is_authentication_attempted)

    def test_authenticated_is_False_when_authentication_is_empty(self):
        resource = OperationsResource(StubHandler, authentication=[])
        self.assertFalse(resource.is_authentication_attempted)

    def test_authenticated_is_False_when_authentication_is_NoAuthn(self):
        resource = OperationsResource(
            StubHandler, authentication=NoAuthentication()
        )
        self.assertFalse(resource.is_authentication_attempted)

    def test_authenticated_is_True_when_authentication_is_provided(self):
        resource = OperationsResource(
            StubHandler, authentication=sentinel.authentication
        )
        self.assertTrue(resource.is_authentication_attempted)


class TestRestrictedResources(MAASTestCase):
    """Tests for `RestrictedResource` and `AdminRestrictedResource`."""

    scenarios = (
        ("user", dict(resource_type=RestrictedResource)),
        ("admin", dict(resource_type=AdminRestrictedResource)),
    )

    def test_authentication_must_not_be_None(self):
        error = self.assertRaises(
            AssertionError,
            self.resource_type,
            StubHandler,
            authentication=None,
        )
        self.assertEqual("Authentication must be attempted.", str(error))

    def test_authentication_must_be_non_empty(self):
        error = self.assertRaises(
            AssertionError, self.resource_type, StubHandler, authentication=[]
        )
        self.assertEqual("Authentication must be attempted.", str(error))

    def test_authentication_must_be_meaningful(self):
        error = self.assertRaises(
            AssertionError,
            self.resource_type,
            StubHandler,
            authentication=NoAuthentication(),
        )
        self.assertEqual("Authentication must be attempted.", str(error))

    def test_authentication_is_okay(self):
        resource = self.resource_type(
            StubHandler, authentication=sentinel.authentication
        )
        self.assertTrue(resource.is_authentication_attempted)


class TestAdminMethodDecorator(MAASServerTestCase):
    def test_non_admin_are_rejected(self):
        FakeRequest = namedtuple("FakeRequest", ["user"])
        request = FakeRequest(user=factory.make_User())
        mock = Mock()

        @admin_method
        def api_method(self, request):
            return mock()

        self.assertRaises(PermissionDenied, api_method, "self", request)
        self.assertEqual([], mock.mock_calls)

    def test_admin_can_call_method(self):
        FakeRequest = namedtuple("FakeRequest", ["user"])
        request = FakeRequest(user=factory.make_admin())
        return_value = factory.make_name("return")
        mock = Mock(return_value=return_value)

        @admin_method
        def api_method(self, request):
            return mock()

        response = api_method("self", request)
        self.assertEqual((return_value, [call()]), (response, mock.mock_calls))


class TestDeprecatedMethodDecorator(MAASServerTestCase):
    def test_function_marked_as_deprecated(self):
        def api_replacement_method(self, request):
            pass

        @deprecated(use=api_replacement_method)
        def api_method(self, request):
            pass

        self.assertEqual(api_method.deprecated, api_replacement_method)

    def test_class_marked_as_deprecated(self):
        class api_replacement_endpoint:
            api_doc_section_name = "Replacement"

        @deprecated(use=api_replacement_endpoint)
        class api_endpoint:
            api_doc_section_name = "Deprecated"

        self.assertEqual(api_endpoint.deprecated, api_replacement_endpoint)

    def test_deprecated_class_inheritance_only_affects_own_methods(self):
        class BaseHandler:
            api_doc_section_name = "Base"

            def inherited_method(self):
                pass

        class ReplacementHandler:
            api_doc_section_name = "Replacement"

            def own_method(self):
                pass

        @deprecated(use=ReplacementHandler)
        class DeprecatedHandler(BaseHandler):
            api_doc_section_name = "Deprecated"

            def own_method(self):
                pass

        self.assertTrue(hasattr(DeprecatedHandler.own_method, "deprecated"))
        self.assertFalse(
            hasattr(DeprecatedHandler.inherited_method, "deprecated")
        )


class TestOperationsHandlerMixin(MAASTestCase):
    """Tests for :py:class:`maasserver.api.support.OperationsHandlerMixin`."""

    def make_handler(self, **namespace):
        return type("TestHandler", (OperationsHandlerMixin,), namespace)

    def test_decorate_decorates_exports(self):
        handler = self.make_handler(
            exports={"foo": sentinel.foo, "bar": sentinel.bar}
        )
        handler.decorate(lambda thing: str(thing).upper())
        self.assertEqual(
            {"foo": "SENTINEL.FOO", "bar": "SENTINEL.BAR"}, handler.exports
        )

    def test_decorate_decorates_anonymous_exports(self):
        handler = self.make_handler(exports={"foo": sentinel.foo})
        handler.anonymous = self.make_handler(exports={"bar": sentinel.bar})
        handler.decorate(lambda thing: str(thing).upper())
        self.assertEqual({"foo": "SENTINEL.FOO"}, handler.exports)
        self.assertEqual({"bar": "SENTINEL.BAR"}, handler.anonymous.exports)
