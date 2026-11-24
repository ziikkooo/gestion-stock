"""Phase 3.2: stock audit integration without Flask dependencies."""
import pytest

from services.catalogue import Catalogue, CatalogueError
from stock_manager.models import Actor, MovementType


@pytest.fixture
def warehouse():
    return Catalogue()


@pytest.fixture
def admin():
    return Actor('test-admin', 'admin')


def change(warehouse, admin, kind, amount, *, reason='', expected=None, product='P001'):
    return warehouse.record_stock_movement(
        product_code=product, kind=kind, amount=str(amount),
        reason=reason, expected_quantity=expected, actor=admin,
    )


def test_seed_history_has_six_records_and_correct_balances(warehouse):
    rows = warehouse.movement_rows()
    assert len(rows) == 6
    assert {r['product_code'] for r in rows} == {'P001','P002','P003','P004','P005','P006'}
    initial = warehouse.movement_rows('P001')
    assert len(initial) == 1
    assert (initial[0]['kind'], initial[0]['previous_quantity'], initial[0]['delta'], initial[0]['resulting_quantity']) == ('initial',0,45,45)
    assert initial[0]['actor'] == 'system-seed'
    assert initial[0]['timestamp'].endswith(' UTC')


def test_entry_exit_adjustment_and_actor_audit(warehouse, admin):
    entry = change(warehouse, admin, 'entry', 10, reason='Supplier delivery')
    assert entry.movement_type == MovementType.ENTRY
    assert warehouse.get_product('P001')['quantity'] == 55
    exit_m = change(warehouse, admin, 'exit', 7, reason='Order fulfillment')
    assert exit_m.quantity_delta == -7
    adjusted = change(warehouse, admin, 'adjustment', 12, expected='48', reason='Physical recount')
    assert adjusted.quantity_delta == -36
    assert warehouse.get_product('P001')['quantity'] == 12
    h = warehouse.movement_rows('P001')
    assert [r['kind'] for r in h] == ['adjustment','exit','entry','initial']
    assert [r['resulting_quantity'] for r in reversed(h)] == [45,55,48,12]
    assert all(r['actor'] == 'admin' for r in h[:-1])
    assert h[0]['reason'] == 'Physical recount'
    assert len(warehouse.movement_rows()) == 9
    assert warehouse.statistics()['low_stock'] == 2


def test_zero_stock_adjustment_allowed(warehouse, admin):
    change(warehouse, admin, 'adjustment', 0, expected='45', reason='Stock count: zero')
    assert warehouse.get_product('P001')['quantity'] == 0
    assert warehouse.statistics()['out_of_stock'] == 2


@pytest.mark.parametrize('kind,amount,reason,expected', [
    ('initial', 5, '', None), ('invalid', 5, '', None),
    ('entry', 0, '', None), ('exit', 0, '', None),
    ('exit', 999, '', None), ('entry', -1, '', None),
    ('entry', '5.5', '', None), ('exit', '1e3', '', None),
    ('entry', '2147483648', '', None),
    ('adjustment', 5, '', '45'),
    ('adjustment', 5, 'Counted', '44'),
    ('adjustment', 45, 'Unchanged count', '45'),
    ('adjustment', 10, 'Counted', None),
    ('entry', 1, 'x' * 501, None),
])
def test_invalid_operations_are_atomic(warehouse, admin, kind, amount, reason, expected):
    before = warehouse.repository.read()
    with pytest.raises(CatalogueError):
        change(warehouse, admin, kind, amount, reason=reason, expected=expected)
    assert warehouse.repository.read() == before


def test_stale_adjustment_rejected_after_concurrent_entry(warehouse, admin):
    stale_quantity = warehouse.get_product('P001')['quantity']
    change(warehouse, admin, 'entry', 2)
    before = warehouse.repository.read()
    with pytest.raises(CatalogueError, match='Stock changed since counting'):
        change(warehouse, admin, 'adjustment', 12, expected=str(stale_quantity), reason='Recount')
    assert warehouse.repository.read() == before


def test_history_uses_product_name_snapshot(warehouse, admin):
    change(warehouse, admin, 'entry', 1)
    warehouse.edit_product('P001','Mouse New Name', ['C001'], 10, '199.99')
    change(warehouse, admin, 'exit', 1)
    rows = warehouse.movement_rows('P001')
    assert [r['product_name'] for r in rows] == ['Mouse New Name','Wireless Mouse','Wireless Mouse']


def test_history_filter_is_read_only(warehouse):
    before = warehouse.repository.read()
    assert len(warehouse.movement_rows('P002')) == 1
    assert warehouse.repository.read() == before
    with pytest.raises(CatalogueError):
        warehouse.movement_rows('P999')


def test_archived_history_remains_accessible(warehouse):
    archived_uid = warehouse._product_uuid('P004')  # Seed keyboard quantity is zero.
    warehouse.service.set_archived(archived_uid, True)
    assert warehouse.get_product('P004') is None
    assert warehouse.get_product('P004', include_archived=True)['archived'] is True
    assert [r['product_code'] for r in warehouse.movement_rows('P004')] == ['P004']
    assert any(p['id'] == 'P004' and p['archived'] for p in warehouse.audit_product_rows())
