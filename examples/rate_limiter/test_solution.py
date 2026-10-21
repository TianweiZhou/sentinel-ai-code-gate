import pytest

from solution import TokenBucket


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.mark.req("R1")
def test_starts_full_and_allows_up_to_capacity(clock):
    bucket = TokenBucket(3, 1, clock=clock)
    assert [bucket.allow() for _ in range(3)] == [True, True, True]


@pytest.mark.req("R2")
def test_rejects_when_empty_without_consuming(clock):
    bucket = TokenBucket(2, 1, clock=clock)
    bucket.allow()
    bucket.allow()
    assert bucket.allow() is False
    assert bucket.tokens == 0


@pytest.mark.req("R3")
def test_refills_at_configured_rate(clock):
    bucket = TokenBucket(3, 2, clock=clock)
    for _ in range(3):
        bucket.allow()
    clock.now += 0.5
    assert bucket.tokens == pytest.approx(1.0)
    assert bucket.allow() is True
    assert bucket.allow() is False


@pytest.mark.req("R3")
def test_never_refills_above_capacity(clock):
    bucket = TokenBucket(3, 2, clock=clock)
    clock.now += 3600
    assert bucket.tokens == 3
    assert [bucket.allow() for _ in range(4)] == [True, True, True, False]


@pytest.mark.req("R4")
@pytest.mark.parametrize("capacity, rate", [(0, 1), (-1, 1), (1, 0), (1, -0.5)])
def test_rejects_invalid_configuration(capacity, rate):
    with pytest.raises(ValueError):
        TokenBucket(capacity, rate)


@pytest.mark.req("R4")
def test_accepts_smallest_valid_configuration(clock):
    assert TokenBucket(1, 0.1, clock=clock).allow() is True


@pytest.mark.req("R5")
def test_cost_is_consumed_and_checked(clock):
    bucket = TokenBucket(5, 1, clock=clock)
    assert bucket.allow(3) is True
    assert bucket.allow(3) is False
    assert bucket.tokens == 2
    assert bucket.allow(2) is True
