# Copyright 2014-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the Registry"""

from unittest.mock import sentinel

from maastesting.testcase import MAASTestCase
from provisioningserver.utils.registry import Registry
from provisioningserver.utils.testing import RegistryFixture


class TestRegistry(MAASTestCase):
    def setUp(self):
        super().setUp()
        # Ensure the global registry is empty for each test run.
        self.useFixture(RegistryFixture())

    def test_register_and_get_item(self):
        name = self.getUniqueString()
        item = self.getUniqueString()
        Registry.register_item(name, item)
        self.assertEqual(item, Registry.get_item(name))

    def test_register_and_unregister_item(self):
        name = self.getUniqueString()
        Registry.register_item(name, sentinel.item)
        Registry.unregister_item(name)
        self.assertIsNone(Registry.get_item(name))
        self.assertNotIn(name, Registry)

    def test_is_singleton_over_multiple_imports(self):
        Registry.register_item("resource1", sentinel.resource1)
        from provisioningserver.drivers import Registry as Registry2

        Registry2.register_item("resource2", sentinel.resource2)
        self.assertEqual(
            [
                ("resource1", sentinel.resource1),
                ("resource2", sentinel.resource2),
            ],
            list(Registry2),
        )

    def test_getitem__(self):
        Registry.register_item("resource", sentinel.resource)
        self.assertEqual(sentinel.resource, Registry["resource"])

    def test_getitem__raises_KeyError_when_name_is_not_registered(self):
        self.assertRaises(KeyError, lambda: Registry["resource"])

    def test_get_item(self):
        Registry.register_item("resource", sentinel.resource)
        self.assertEqual(sentinel.resource, Registry.get_item("resource"))

    def test_get_item_returns_default_if_value_not_present(self):
        self.assertEqual(
            sentinel.default, Registry.get_item("resource", sentinel.default)
        )

    def test_get_item_returns_None_default(self):
        self.assertIsNone(Registry.get_item("resource"))

    def test_contains__(self):
        Registry.register_item("resource", sentinel.resource)
        self.assertIn("resource", Registry)

    def test_duplicate_key(self):
        Registry.register_item("resource", sentinel.resource)
        self.assertRaises(
            KeyError, Registry.register_item, "resource", sentinel.resource
        )

    def test_registered_items_are_stored_separately_by_registry(self):
        class RegistryOne(Registry):
            """A registry distinct from the base `Registry`."""

        class RegistryTwo(Registry):
            """A registry distinct from the base `Registry`."""

        name = self.getUniqueString()
        Registry.register_item(name, sentinel.item)
        RegistryOne.register_item(name, sentinel.item_in_one)
        RegistryTwo.register_item(name, sentinel.item_in_two)

        # Items stored in separate registries are stored separately;
        # names do not clash between registries.
        self.assertEqual(sentinel.item, Registry.get_item(name))
        self.assertEqual(sentinel.item_in_one, RegistryOne.get_item(name))
        self.assertEqual(sentinel.item_in_two, RegistryTwo.get_item(name))
