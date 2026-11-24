"""Checks that Flask writes use WarehouseService with authenticated identities."""
from decimal import Decimal
from unittest.mock import patch

import pytest
import app as application
from auth_helpers import TEST_CONFIG, csrf, sign_in
from services.catalogue import Catalogue
from stock_manager.models import MovementType


@pytest.fixture
def client(monkeypatch):
    warehouse = Catalogue()
    monkeypatch.setattr(application, 'catalogue', warehouse)
    for k, v in TEST_CONFIG.items():
        monkeypatch.setitem(application.app.config, k, v)
    yield application.app.test_client(), warehouse


def test_admin_creation_records_real_session_user(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    response = browser.post('/admin/add', data={
        'name': 'SSD', 'category_ids': ['C001', 'C002'],
        'quantity': '5', 'min_stock': '3', 'price': '79.99',
        'csrf_token': csrf(browser, '/admin/add')
    })
    assert response.status_code == 303
    movement, = warehouse.history('P007')
    assert movement.movement_type == MovementType.INITIAL
    assert movement.actor_id == 'test-admin'
    assert movement.actor_username == 'admin'
    assert movement.resulting_quantity == 5
    assert warehouse.get_product('P007')['price'] == Decimal('79.99')


def test_viewer_cannot_create_product_or_invent_actor(client):
    browser, warehouse = client
    assert sign_in(browser, 'viewer').status_code == 303
    assert browser.post('/admin/add', data={
        'name': 'Malicious', 'category_ids': ['C001'],
        'quantity': '5', 'min_stock': '3', 'price': '79.99',
        'actor': 'admin', 'csrf_token': csrf(browser),
    }).status_code == 403
    assert warehouse.statistics()['total_products'] == 6


def test_invalid_scientific_price_rejected_by_flask_and_no_audit_write(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    response = browser.post('/admin/add', data={
        'name': 'Bad Price', 'category_ids': ['C001'],
        'quantity': '5', 'min_stock': '3', 'price': '1e3',
        'csrf_token': csrf(browser, '/admin/add')
    })
    assert response.status_code == 400
    assert warehouse.statistics()['total_products'] == 6
    assert len(warehouse.repository.read().movements) == 6


def test_existing_category_and_product_pages_survive_migration(client):
    browser, warehouse = client
    assert sign_in(browser).status_code == 303
    for path in ('/', '/inventory', '/admin', '/admin/categories', '/admin/edit/P001', '/admin/add'):
        assert browser.get(path).status_code == 200
    assert b'Showing 6 of 6 products' in browser.get('/inventory').data
    assert b'Wireless Mouse' in browser.get('/inventory').data
