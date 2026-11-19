from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from dataclasses import FrozenInstanceError
from uuid import UUID
import pytest

from stock_manager.models import Actor, MovementType, StockStatus
from stock_manager.repository import InMemoryRepository
from stock_manager.service import WarehouseService, ValidationError, NotFoundError, price_to_centimes


@pytest.fixture
def warehouse():
    repo = InMemoryRepository()
    service = WarehouseService(repo)
    a = service.create_category('Electronics')
    b = service.create_category('Accessories')
    actor = Actor('test-admin-id', 'test-admin')
    return repo, service, a, b, actor


def create(warehouse, *, name='Mouse', quantity=10, ids=None):
    repo, service, a, b, actor = warehouse
    return service.create_product(name=name, quantity=quantity, category_ids=[a.id] if ids is None else ids,
                                  min_stock=3, price='129.99', actor=actor)


@pytest.mark.parametrize('name', [' electronics ', 'ELECTRONICS', '\tElectronics\n'])
def test_category_duplicate(warehouse, name):
    with pytest.raises(ValidationError):
        warehouse[1].create_category(name)


def test_whitespace_and_casefold(warehouse):
    service = warehouse[1]
    c = service.create_category('  Office   Supplies  ')
    assert c.name == 'Office Supplies'
    with pytest.raises(ValidationError):
        service.create_category('OFFICE supplies')
    service.create_category('Straße')
    with pytest.raises(ValidationError):
        service.create_category('STRASSE')


def test_category_rename_preserves_product_reference(warehouse):
    repo, service, a, b, actor = warehouse
    p = create(warehouse)
    service.rename_category(a.id, 'Electronic Equipment')
    assert repo.read().categories[p.category_ids[0]].name == 'Electronic Equipment'
    assert repo.read().products[p.id] == p
    with pytest.raises(ValidationError):
        service.rename_category(a.id, b.name)


def test_delete_category_in_use_including_archived(warehouse):
    repo, service, a, b, actor = warehouse
    p = create(warehouse, quantity=0)
    with pytest.raises(ValidationError):
        service.delete_category(a.id)
    service.set_archived(p.id, True)
    with pytest.raises(ValidationError):
        service.delete_category(a.id)
    service.delete_category(b.id)
    assert b.id not in repo.read().categories


@pytest.mark.parametrize('price', ['NaN', 'Infinity', '-1', '1.001', 'x', 0.1, '1.0000000000000000000000000000000000000001'])
def test_bad_prices(price):
    with pytest.raises(ValidationError):
        price_to_centimes(price)


def test_exact_prices():
    assert price_to_centimes('129.99') == 12999
    assert price_to_centimes('0.10') == 10


def test_product_category_validation(warehouse):
    a = warehouse[2]
    for ids in [[], ['unknown'], [a.id, a.id]]:
        with pytest.raises(ValidationError):
            create(warehouse, ids=ids)
    assert not warehouse[0].read().products
    assert not warehouse[0].read().movements
    assert create(warehouse).code == 'P001'


def test_filter_any_all_and_combined(warehouse):
    repo, service, a, b, actor = warehouse
    p = create(warehouse, name='Mouse', ids=[a.id, b.id], quantity=2)
    q = create(warehouse, name='Keyboard', ids=[a.id], quantity=0)
    r = create(warehouse, name='Cable', ids=[b.id], quantity=12)
    ids = (a.id, b.id)
    assert {x.id for x in service.filter_products(category_ids=ids, mode='any')} == {p.id, q.id, r.id}
    assert service.filter_products(category_ids=ids, mode='all') == [p]
    assert service.filter_products(category_ids=ids, mode='any', status=StockStatus.LOW, search='MOUSE') == [p]
    assert service.filter_products(search=q.code.lower()) == [q]
    assert len(service.filter_products()) == 3


@pytest.mark.parametrize('quantity,status', [(0, StockStatus.OUT), (1, StockStatus.LOW), (3, StockStatus.LOW), (4, StockStatus.AVAILABLE)])
def test_status_boundaries(warehouse, quantity, status):
    assert create(warehouse, quantity=quantity).status == status


@pytest.mark.parametrize('quantity', [0, 20])
def test_initial_stock_and_actor(warehouse, quantity):
    repo, service, a, b, actor = warehouse
    product = create(warehouse, quantity=quantity)
    UUID(product.id)
    movement, = service.history(product.id)
    assert (movement.previous_quantity, movement.quantity_delta, movement.resulting_quantity) == (0, quantity, quantity)
    assert movement.movement_type == MovementType.INITIAL
    assert (movement.actor_id, movement.actor_username) == (actor.id, actor.username)
    assert movement.created_at.utcoffset().total_seconds() == 0
    assert product.price_centimes == 12999


def test_movements_and_name_snapshot(warehouse):
    repo, service, a, b, actor = warehouse
    p = create(warehouse, quantity=20)
    service.record_movement(p.id, kind=MovementType.ENTRY, amount=5, actor=actor)
    service.edit_product(p.id, name='New Mouse', category_ids=[b.id], min_stock=2, price='5.00')
    service.record_movement(p.id, kind=MovementType.EXIT, amount=7, actor=actor)
    service.record_movement(p.id, kind=MovementType.ADJUSTMENT, amount=15, actor=actor, reason='Physical count', expected_quantity=18)
    history = service.history(p.id)
    assert [m.quantity_delta for m in history] == [20, 5, -7, -3]
    assert [m.product_name for m in history] == ['Mouse', 'Mouse', 'New Mouse', 'New Mouse']
    assert all(a.resulting_quantity == b.previous_quantity for a, b in zip(history, history[1:]))
    assert sum(m.quantity_delta for m in history) == repo.read().products[p.id].quantity == 15
    with pytest.raises(FrozenInstanceError):
        history[0].quantity_delta = 999


def test_invalid_movements_leave_state_unchanged(warehouse):
    repo, service, a, b, actor = warehouse
    p = create(warehouse, quantity=10)
    before = repo.read()
    for kind, amount, reason, expected in [(MovementType.EXIT, 11, '', None), (MovementType.ENTRY, 0, '', None), (MovementType.ADJUSTMENT, 5, '', 10), (MovementType.ADJUSTMENT, 5, 'count', 9), (MovementType.ADJUSTMENT, 10, 'count', 10), (MovementType.INITIAL, 1, '', None)]:
        with pytest.raises(ValidationError):
            service.record_movement(p.id, kind=kind, amount=amount, actor=actor, reason=reason, expected_quantity=expected)
        assert repo.read() == before


def test_archiving_and_restore(warehouse):
    repo, service, a, b, actor = warehouse
    p = create(warehouse, quantity=1)
    with pytest.raises(ValidationError):
        service.set_archived(p.id, True)
    service.record_movement(p.id, kind=MovementType.EXIT, amount=1, actor=actor)
    service.set_archived(p.id, True)
    assert service.filter_products() == []
    assert service.filter_products(archived=True)[0].id == p.id
    with pytest.raises(ValidationError):
        service.record_movement(p.id, kind=MovementType.ENTRY, amount=1, actor=actor)
    assert len(service.history(p.id)) == 2
    service.set_archived(p.id, False)
    assert service.filter_products()[0].id == p.id


def test_concurrent_exits(warehouse):
    repo, service, a, b, actor = warehouse
    product = create(warehouse, quantity=10)
    barrier = Barrier(2)
    def exit_stock(amount):
        barrier.wait(timeout=5)
        try:
            service.record_movement(product.id, kind=MovementType.EXIT, amount=amount, actor=actor)
            return True
        except ValidationError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(exit_stock, [8, 7])) == 1
    history = service.history(product.id)
    assert len(history) == 2
    assert sum(m.quantity_delta for m in history) == repo.read().products[product.id].quantity in (2, 3)


def test_repository_rollback_and_isolated_snapshot(warehouse):
    repo = warehouse[0]
    before = repo.read()
    draft = repo.read()
    draft.categories.clear()
    assert repo.read() == before
    def fail(state):
        state.categories.clear()
        raise RuntimeError('failure')
    with pytest.raises(RuntimeError):
        repo.transact(fail)
    assert repo.read() == before


def test_sequential_codes_not_reused(warehouse):
    repo, service, a, b, actor = warehouse
    service.delete_category(b.id)
    assert service.create_category('Third category').code == 'C003'
    assert create(warehouse).code == 'P001'
    assert create(warehouse).code == 'P002'
