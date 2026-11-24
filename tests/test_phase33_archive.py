"""Phase 3.3: soft archive / restore domain and adapter tests (no Flask)."""
import pytest

from services.catalogue import Catalogue, CatalogueError
from stock_manager.models import Actor, MovementType


@pytest.fixture
def store():
    return Catalogue()


def test_archive_zero_stock_product_keeps_history_and_identity(store):
    original = store.get_product('P004')
    before_history = store.history('P004')
    result = store.set_product_archived('P004', archived=True)
    assert result['archived'] is True and result['id'] == 'P004'
    assert store.get_product('P004') is None
    assert store.get_product('P004', include_archived=True)['category_ids'] == original['category_ids']
    assert store.history('P004') == before_history
    assert store.movement_rows('P004')[0]['actor'] == 'system-seed'


def test_archive_excluded_from_all_active_views_and_stats(store):
    store.set_product_archived('P004', archived=True)
    assert len(store.products) == 5
    assert len(store.product_rows()) == 5
    assert len(store.filter_products()) == 5
    assert len(store.filter_products(status='out')) == 0
    assert len(store.audit_product_rows()) == 6
    assert store.statistics() == {'total_products': 5, 'low_stock': 2, 'out_of_stock': 0}
    assert [p['id'] for p in store.archived_product_rows()] == ['P004']


def test_positive_stock_cannot_be_archived_and_state_is_unchanged(store):
    snapshot = store.repository.read()
    with pytest.raises(CatalogueError, match='zero stock'):
        store.set_product_archived('P001', archived=True)
    assert store.repository.read() == snapshot


def test_restore_preserves_code_categories_price_quantity_and_history(store):
    expected = store.get_product('P004')
    original_history = store.history('P004')
    store.set_product_archived('P004', archived=True)
    restored = store.set_product_archived('P004', archived=False)
    assert restored == expected | {'archived': False}
    assert store.get_product('P004') == restored
    assert store.history('P004') == original_history
    assert store.statistics() == {'total_products': 6, 'low_stock': 2, 'out_of_stock': 1}


def test_archive_and_restore_do_not_create_stock_movements(store):
    before = store.movement_rows()
    store.set_product_archived('P004', archived=True)
    store.set_product_archived('P004', archived=False)
    assert store.movement_rows() == before


def test_repeat_archive_or_restore_is_rejected(store):
    store.set_product_archived('P004', archived=True)
    snapshot = store.repository.read()
    with pytest.raises(CatalogueError, match='already archived'):
        store.set_product_archived('P004', archived=True)
    assert store.repository.read() == snapshot
    store.set_product_archived('P004', archived=False)
    snapshot = store.repository.read()
    with pytest.raises(CatalogueError, match='already active'):
        store.set_product_archived('P004', archived=False)
    assert store.repository.read() == snapshot


def test_archived_product_cannot_be_edited_or_receive_movement(store):
    store.set_product_archived('P004', archived=True)
    snapshot = store.repository.read()
    with pytest.raises(CatalogueError):
        store.edit_product('P004', 'New Keyboard', ['C001'], 5, '100.00')
    with pytest.raises(CatalogueError):
        store.record_stock_movement(
            product_code='P004', kind='entry', amount='5', reason='Delivery',
            expected_quantity=None, actor=Actor('test-admin', 'admin')
        )
    assert store.repository.read() == snapshot


def test_archived_product_categories_remain_protected(store):
    store.set_product_archived('P004', archived=True)
    assert store.category_rows()[0]['product_count'] == 5
    # Create a category only used by an archived product.
    special = store.add_category('Old Supplies')
    # Restore, edit assignment and archive again to set up the test.
    store.set_product_archived('P004', archived=False)
    store.edit_product('P004', 'Keyboard', ['C006'], '5', '199.99')
    store.set_product_archived('P004', archived=True)
    with pytest.raises(CatalogueError, match='assigned'):
        store.delete_category(special['id'])
    assert store.get_category('C006') is not None


def test_codes_not_reused_and_archive_list_id_sorted(store):
    store.set_product_archived('P004', archived=True)
    # First newly created product gets P007, even though P004 is archived.
    p = store.add_product('New Product', ['C001'], '0', '1', '5.00')
    assert p['id'] == 'P007'
    store.set_product_archived('P007', archived=True)
    assert [p['id'] for p in store.archived_product_rows()] == ['P004', 'P007']
    assert store.add_product('Another Product', ['C001'], '1', '1', '1.00')['id'] == 'P008'


def test_unknown_product_cannot_archive_or_restore(store):
    for archived in (True, False):
        with pytest.raises(CatalogueError, match='not found'):
            store.set_product_archived('P999', archived=archived)


def test_movement_exit_to_zero_then_archive(store):
    store.record_stock_movement(
        product_code='P002', kind=MovementType.EXIT.value, amount='8',
        reason='Last delivery', expected_quantity=None, actor=Actor('admin-id', 'admin')
    )
    assert store.get_product('P002')['quantity'] == 0
    previous_history = store.movement_rows('P002')
    store.set_product_archived('P002', archived=True)
    assert len(store.movement_rows('P002')) == 2
    assert store.movement_rows('P002') == previous_history
