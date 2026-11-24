"""Phase 3.1 repository integration: runnable with pytest or unittest."""
import unittest
from decimal import Decimal

from services.catalogue import Catalogue, CatalogueError
from stock_manager.models import Actor, MovementType
from stock_manager.service import ValidationError, price_to_centimes


class Phase3BridgeTests(unittest.TestCase):
    def setUp(self):
        self.store = Catalogue()

    def test_seed_codes_numbers_and_categories(self):
        self.assertEqual([c['id'] for c in self.store.categories],
                         ['C001', 'C002', 'C003', 'C004', 'C005'])
        self.assertEqual([p['id'] for p in self.store.products],
                         ['P001', 'P002', 'P003', 'P004', 'P005', 'P006'])
        self.assertEqual(self.store.statistics(),
                         {'total_products': 6, 'low_stock': 2, 'out_of_stock': 1})
        self.assertEqual(self.store.get_product('P001')['category_ids'],
                         ['C001', 'C002', 'C005'])

    def test_seed_stock_history_is_explicitly_system_attributed(self):
        self.assertEqual(len(self.store.repository.read().movements), 6)
        for product in self.store.products:
            movement, = self.store.history(product['id'])
            self.assertEqual(movement.movement_type, MovementType.INITIAL)
            self.assertEqual(movement.actor_username, 'system-seed')
            self.assertEqual(movement.previous_quantity, 0)
            self.assertEqual(movement.resulting_quantity, product['quantity'])
            self.assertEqual(movement.quantity_delta, product['quantity'])

    def test_new_product_uses_authenticated_actor_and_centimes(self):
        admin = Actor('signed-in-admin-id', 'admin')
        product = self.store.add_product('SSD', ['C001', 'C002', 'C001'], '12', '3', '179.90', actor=admin)
        self.assertEqual(product['id'], 'P007')
        self.assertEqual(product['category_ids'], ['C001', 'C002'])
        movement, = self.store.history('P007')
        self.assertEqual((movement.actor_id, movement.actor_username), ('signed-in-admin-id', 'admin'))
        internal_product = next(p for p in self.store.repository.read().products.values() if p.code == 'P007')
        self.assertEqual(internal_product.price_centimes, 17990)
        self.assertEqual(product['price'], Decimal('179.9'))

    def test_no_second_mutable_catalogue_can_diverge(self):
        before = self.store.products[0]
        before['quantity'] = 999
        before['category_ids'].clear()
        self.assertEqual(self.store.get_product('P001')['quantity'], 45)
        self.assertEqual(self.store.get_product('P001')['category_ids'], ['C001', 'C002', 'C005'])
        categories = self.store.categories
        categories.clear()
        self.assertEqual(len(self.store.categories), 5)

    def test_category_rename_propagates_and_cannot_delete_assigned(self):
        self.store.rename_category('C001', 'Devices')
        self.assertIn('Devices', self.store.product_rows()[0]['category_names'])
        with self.assertRaises(CatalogueError):
            self.store.delete_category('C001')
        extra = self.store.add_category('Free Category')
        self.assertEqual(extra['id'], 'C006')
        self.store.delete_category(extra['id'])
        self.assertEqual(self.store.add_category('Other Category')['id'], 'C007')

    def test_edit_never_changes_id_stock_or_existing_initial_movement(self):
        old = self.store.history('P001')[0]
        self.store.edit_product('P001', 'Mouse Pro', ['C002'], '60', '139.99')
        product = self.store.get_product('P001')
        self.assertEqual(product['quantity'], 45)
        self.assertEqual(product['id'], 'P001')
        self.assertEqual(product['status'], 'low')
        self.assertEqual(product['category_ids'], ['C002'])
        self.assertEqual(self.store.history('P001'), [old])

    def test_rejected_price_and_bad_stock_do_not_create_product(self):
        initial = self.store.repository.read()
        for price in ['1e3', '12.999', '+1', '-1', 'NaN', 'Infinity', '1,25']:
            with self.subTest(price=price), self.assertRaises(CatalogueError):
                self.store.add_product('Bad', ['C001'], '1', '1', price)
        for qty in ['-1', '2.5', '1e3', '2147483648']:
            with self.subTest(qty=qty), self.assertRaises(CatalogueError):
                self.store.add_product('Bad', ['C001'], qty, '1', '1.00')
        self.assertEqual(self.store.repository.read(), initial)
        with self.assertRaises(ValidationError):
            price_to_centimes('1e3')

    def test_filtering_keeps_public_ids_and_id_order(self):
        self.assertEqual([p['id'] for p in self.store.product_rows(
            self.store.filter_products(category_ids=['C001', 'C002'], mode='all'))],
            ['P001', 'P002', 'P005'])
        self.assertEqual(self.store.filter_products(category_ids=['C999']), [])
        self.assertEqual(self.store.filter_products('HEAD', ['C001'], 'any', 'low')[0]['id'], 'P005')
        self.assertEqual([c['id'] for c in self.store.category_rows()],
                         ['C001', 'C002', 'C003', 'C004', 'C005'])
        self.assertEqual([c['id'] for c in self.store.sorted_categories()],
                         ['C002', 'C005', 'C001', 'C004', 'C003'])


if __name__ == '__main__':
    unittest.main()
