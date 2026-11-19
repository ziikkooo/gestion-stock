import unittest
from unittest.mock import patch
import app as application
from services.catalogue import Catalogue


class CategoryRouteTests(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.object(application, 'catalogue', Catalogue())
        self.store = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = application.app.test_client()

    def test_pages(self):
        for path in ('/', '/inventory', '/admin', '/admin/add', '/admin/categories', '/admin/edit/P001'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_filter(self):
        for mode, count in [('any', 5), ('all', 3)]:
            response = self.client.get(f'/inventory?category=C001&category=C002&match={mode}')
            self.assertIn(f'Showing {count} of 6 products'.encode(), response.data)

    def test_create_category_and_duplicate(self):
        self.assertEqual(self.client.post('/admin/categories', data={'name': 'Cleaning'}).status_code, 303)
        self.assertEqual(self.client.post('/admin/categories', data={'name': ' cleaning '}).status_code, 400)

    def test_edit_and_delete_category(self):
        self.assertEqual(self.client.post('/admin/categories/C001/rename', data={'name': 'Electronic Equipment'}).status_code, 303)
        self.assertIn(b'Electronic Equipment', self.client.get('/inventory').data)
        self.assertEqual(self.client.post('/admin/categories/C001/delete').status_code, 409)
        new = self.store.add_category('Unused')
        self.assertEqual(self.client.post(f'/admin/categories/{new["id"]}/delete').status_code, 303)
        self.assertIsNone(self.store.get_category(new['id']))

    def test_add_and_edit_product(self):
        form = {'name': 'Flash Drive', 'category_ids': ['C001', 'C002'], 'quantity': '20', 'min_stock': '5', 'price': '89.99'}
        self.assertEqual(self.client.post('/admin/add', data=form).status_code, 303)
        self.assertIn(b'Flash Drive', self.client.get('/inventory').data)
        self.assertEqual(self.client.post('/admin/edit/P007', data={**form, 'quantity': '999', 'category_ids': ['C002']}).status_code, 303)
        self.assertEqual(self.store.get_product('P007')['quantity'], 20)
        self.assertEqual(self.store.get_product('P007')['category_ids'], ['C002'])

    def test_invalid_product(self):
        form = {'name': 'Bad', 'quantity': '0', 'min_stock': '0', 'price': '1.00'}
        self.assertEqual(self.client.post('/admin/add', data=form).status_code, 400)
        self.assertEqual(self.client.post('/admin/add', data={**form, 'category_ids': ['C999']}).status_code, 400)
        self.assertEqual(len(self.store.products), 6)


if __name__ == '__main__':
    unittest.main()
