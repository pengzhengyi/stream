"""The download policy's plan: what it starts, what it removes, and what it never touches."""

import dataclasses
from datetime import UTC, datetime, timedelta
from random import Random

from hypothesis import given, settings
from hypothesis import strategies as st

from medleyplay.domain.accounts import AccountId
from medleyplay.domain.catalog import SourceId, TrackId
from medleyplay.domain.policy import (
    MAX_ACTIVE,
    MAX_FAILURES,
    MIN_FREE,
    REST,
    RETRY_AFTER,
    CacheCopy,
    Failure,
    Plan,
    PolicyState,
    Remove,
    RemoveCache,
    Shortfall,
    Standing,
    Start,
    StoredDownload,
    Wanted,
    plan,
    removable,
    reservation,
)

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
MB = 1_000_000
ALICE, BOB = AccountId(1), AccountId(2)
ROOMY_DISK = 1000 * 1024**3


def _standing(
    *, favorite: bool = False, rating: int | None = None, days_old: int = 100
) -> Standing:
    return Standing(
        favorite=favorite,
        best_rating=rating,
        last_played_at=None,
        added_at=NOW - timedelta(days=days_old),
    )


def _old_download(source: int, size: int, **changes: object) -> StoredDownload:
    """A Download nobody wants, downloaded a week ago and never served: removable once limited."""
    download = StoredDownload(
        source_id=SourceId(source),
        size=size,
        standing=_standing(),
        downloaded_at=NOW - timedelta(days=7),
    )
    return dataclasses.replace(download, **changes)  # type: ignore[arg-type]


def _wanted(track: int, estimate: int, **changes: object) -> Wanted:
    """A Bilibili Track Alice keeps downloaded, with no Download yet."""
    wanted = Wanted(
        track_id=TrackId(track),
        source_id=SourceId(100 + track),
        site="bilibili",
        estimate=estimate,
        standing=_standing(),
        wanted_by=(ALICE,),
    )
    return dataclasses.replace(wanted, **changes)  # type: ignore[arg-type]


def _state(**changes: object) -> PolicyState:
    """A roomy disk, no limit, Bilibili downloadable, and nothing on it yet."""
    state = PolicyState(
        now=NOW,
        limit=None,
        free=ROOMY_DISK // 2,
        disk_size=ROOMY_DISK,
        downloadable_sites=frozenset({"bilibili"}),
    )
    return dataclasses.replace(state, **changes)  # type: ignore[arg-type]


def test_a_wanted_track_starts_downloading_as_the_account_that_wants_it() -> None:
    planned = plan(_state(wanted=(_wanted(1, 5 * MB),)))

    assert planned == Plan(starts=(Start(TrackId(1), SourceId(101), ALICE, 5 * MB),))


def test_the_download_uses_the_login_of_the_first_account_wanting_it_that_has_one() -> None:
    state = _state(
        wanted=(_wanted(1, 5 * MB, wanted_by=(ALICE, BOB)),),
        valid_logins=frozenset({(BOB, "bilibili")}),
    )

    assert [each.requester for each in plan(state).starts] == [BOB]


def test_without_a_limit_nothing_is_removed() -> None:
    state = _state(downloads=(_old_download(1, 900 * MB),), wanted=(_wanted(2, 5 * MB),))

    assert plan(state).removals == ()


def test_room_is_made_for_a_wanted_track_cache_copies_first() -> None:
    state = _state(
        limit=100 * MB,
        cache=(CacheCopy("1-v1.flac", 4 * MB, NOW - timedelta(days=3)),),
        downloads=(
            _old_download(1, 3 * MB),
            _old_download(2, 88 * MB, standing=_standing(favorite=True)),
        ),
        wanted=(_wanted(9, 10 * MB),),
    )

    planned = plan(state)

    assert planned.removals == (RemoveCache("1-v1.flac", 4 * MB), Remove(SourceId(1), 3 * MB))
    assert [each.track_id for each in planned.starts] == [TrackId(9)]


def test_a_download_that_cant_fit_even_after_removing_is_skipped_and_nothing_goes_for_it() -> None:
    state = _state(
        limit=100 * MB,
        downloads=(_old_download(1, 50 * MB, wanted=True),),
        wanted=(_wanted(9, 60 * MB),),
    )

    planned = plan(state)

    assert planned.is_empty()
    assert planned.shortfalls == {TrackId(9): Shortfall.OVER_LIMIT}


def test_a_lowered_limit_removes_least_favorite_first_until_use_is_under_it() -> None:
    state = _state(
        limit=100 * MB,
        downloads=(
            _old_download(1, 60 * MB, standing=_standing(rating=5)),
            _old_download(2, 60 * MB, standing=_standing(rating=2)),
            _old_download(3, 60 * MB, standing=_standing(favorite=True)),
        ),
    )

    assert plan(state).removals == (Remove(SourceId(2), 60 * MB), Remove(SourceId(1), 60 * MB))


def test_a_limit_nothing_removable_can_meet_leaves_everything_in_place() -> None:
    state = _state(
        limit=100 * MB,
        downloads=(_old_download(1, 150 * MB, wanted=True), _old_download(2, 10 * MB)),
    )

    assert plan(state).removals == ()


def test_what_may_not_be_removed_stays_whatever_the_limit() -> None:
    recently = NOW - REST + timedelta(minutes=1)
    state = _state(
        limit=1,
        downloads=(
            _old_download(1, MB, wanted=True),
            _old_download(2, MB, replaceable=False),
            _old_download(3, MB, active_job=True),
            _old_download(4, MB, downloaded_at=recently),
            _old_download(5, MB, last_served_at=recently),
            _old_download(6, MB, last_wanted_at=recently),
        ),
        cache=(CacheCopy("7-v1.flac", MB, recently),),
    )

    assert removable(state) == []


def test_at_most_two_policy_downloads_are_active_and_the_rest_wait_their_turn() -> None:
    state = _state(
        wanted=tuple(_wanted(n, MB) for n in range(1, 5)),
        active_policy_jobs=1,
    )

    planned = plan(state)

    assert len(planned.starts) == MAX_ACTIVE - 1
    assert list(planned.shortfalls.values()).count(Shortfall.WAITING_TURN) == 4 - len(
        planned.starts
    )


def test_the_most_favored_wanted_track_downloads_first() -> None:
    state = _state(
        wanted=(
            _wanted(1, MB),
            _wanted(2, MB, standing=_standing(favorite=True)),
            _wanted(3, MB, standing=_standing(rating=5)),
        ),
    )

    assert [each.track_id for each in plan(state).starts] == [TrackId(2), TrackId(3)]


def test_a_download_leaves_the_disk_its_free_space() -> None:
    # On a 10 GiB disk, 2 GiB is more than 5%, so a Download must leave 2 GiB free.
    small_disk = 10 * 1024**3
    state = _state(
        disk_size=small_disk,
        free=MIN_FREE + 4 * MB,
        wanted=(_wanted(1, 5 * MB), _wanted(2, 3 * MB)),
    )

    planned = plan(state)

    assert [each.track_id for each in planned.starts] == [TrackId(2)]
    assert planned.shortfalls == {TrackId(1): Shortfall.DISK_FULL}


def test_a_failure_is_retried_a_day_later_up_to_three_times_or_at_once_when_its_cause_is_gone() -> (
    None
):
    yesterday = NOW - RETRY_AFTER
    state = _state(
        wanted=(
            _wanted(1, MB, failure=Failure(yesterday, in_a_row=1)),
            _wanted(2, MB, failure=Failure(NOW - timedelta(hours=1), in_a_row=1)),
            _wanted(3, MB, failure=Failure(yesterday, in_a_row=MAX_FAILURES + 1)),
            _wanted(4, MB, failure=Failure(NOW, in_a_row=MAX_FAILURES + 1, cleared=True)),
        ),
    )

    planned = plan(state)

    assert {each.track_id for each in planned.starts} == {TrackId(1), TrackId(4)}
    assert planned.shortfalls == {TrackId(2): Shortfall.FAILING, TrackId(3): Shortfall.FAILING}


def test_a_track_no_plugin_downloads_or_whose_source_is_gone_is_reported_not_started() -> None:
    state = _state(
        wanted=(_wanted(1, MB, site="elsewhere"), _wanted(2, MB, source_ok=False)),
    )

    assert plan(state).shortfalls == {
        TrackId(1): Shortfall.NO_PLUGIN,
        TrackId(2): Shortfall.UNAVAILABLE,
    }


def test_a_reservation_is_the_size_at_the_bitrate_plus_a_tenth() -> None:
    assert reservation(60_000, 192) == 1_584_000
    assert reservation(None, 192) == 16 * 1024**2


# Properties over generated snapshots.

_TIMES = st.integers(min_value=0, max_value=240).map(lambda hours: NOW - timedelta(hours=hours))
# Mostly the ordinary case, sometimes the exception, so plans remove often enough to test.
_RARELY = st.sampled_from([False, False, False, True])
_USUALLY = _RARELY.map(lambda rare: not rare)
_SIZES = st.integers(min_value=1, max_value=40 * MB)
_STANDINGS = st.builds(
    Standing,
    favorite=st.booleans(),
    best_rating=st.none() | st.integers(min_value=1, max_value=5),
    last_played_at=st.none() | _TIMES,
    added_at=_TIMES,
)


@st.composite
def _states(draw: st.DrawFn) -> PolicyState:
    downloads = draw(
        st.lists(
            st.builds(
                StoredDownload,
                source_id=st.just(SourceId(0)),
                size=_SIZES,
                standing=_STANDINGS,
                downloaded_at=_TIMES,
                last_served_at=st.none() | _TIMES,
                last_wanted_at=st.none() | _TIMES,
                wanted=_RARELY,
                replaceable=_USUALLY,
                active_job=_RARELY,
            ),
            max_size=10,
        )
    )
    wanted = draw(
        st.lists(
            st.builds(
                Wanted,
                track_id=st.just(TrackId(0)),
                source_id=st.just(SourceId(0)),
                site=st.sampled_from(["bilibili", "elsewhere"]),
                estimate=_SIZES,
                standing=_STANDINGS,
                wanted_by=st.lists(st.sampled_from([ALICE, BOB]), min_size=1, unique=True).map(
                    tuple
                ),
                source_ok=_USUALLY,
                active_job=_RARELY,
                failure=st.none()
                | st.builds(
                    Failure, failed_at=_TIMES, in_a_row=st.integers(1, 5), cleared=st.booleans()
                ),
            ),
            max_size=6,
        )
    )
    cache = draw(
        st.lists(st.builds(CacheCopy, name=st.just(""), size=_SIZES, touched_at=_TIMES), max_size=4)
    )
    # A limit near what is stored, so plans both fit and must make room.
    stored = sum(each.size for each in downloads) + sum(each.size for each in cache)
    share = None if draw(_RARELY) else draw(st.floats(min_value=0.3, max_value=1.5))
    return PolicyState(
        now=NOW,
        limit=None if share is None else int(stored * share),
        free=draw(st.integers(min_value=0, max_value=400 * MB)) + MIN_FREE,
        disk_size=ROOMY_DISK // 100,
        # Ids follow the rows, so each is unique and the plan can name it.
        downloads=tuple(
            dataclasses.replace(each, source_id=SourceId(n)) for n, each in enumerate(downloads)
        ),
        cache=tuple(dataclasses.replace(each, name=f"{n}-v1.flac") for n, each in enumerate(cache)),
        wanted=tuple(
            dataclasses.replace(each, track_id=TrackId(n), source_id=SourceId(1000 + n))
            for n, each in enumerate(wanted)
        ),
        reserved=draw(st.integers(min_value=0, max_value=20 * MB)),
        active_policy_jobs=draw(st.integers(min_value=0, max_value=MAX_ACTIVE)),
        downloadable_sites=frozenset({"bilibili"}),
        valid_logins=frozenset(
            draw(st.sets(st.sampled_from([(ALICE, "bilibili"), (BOB, "bilibili")])))
        ),
    )


def _applied(state: PolicyState, planned: Plan) -> PolicyState:
    """The state after the plan's removals happen and its Downloads are submitted, as planned."""
    removed = {each.source_id for each in planned.removals if isinstance(each, Remove)}
    removed_cache = {each.name for each in planned.removals if isinstance(each, RemoveCache)}
    started = {each.track_id for each in planned.starts}
    return dataclasses.replace(
        state,
        downloads=tuple(each for each in state.downloads if each.source_id not in removed),
        cache=tuple(each for each in state.cache if each.name not in removed_cache),
        wanted=tuple(
            dataclasses.replace(each, active_job=True) if each.track_id in started else each
            for each in state.wanted
        ),
        free=state.free + sum(each.size for each in planned.removals),
        reserved=state.reserved + sum(each.estimate for each in planned.starts),
        active_policy_jobs=state.active_policy_jobs + len(planned.starts),
    )


@settings(max_examples=300)
@given(_states())
def test_planning_again_after_applying_a_plan_plans_nothing(state: PolicyState) -> None:
    assert plan(_applied(state, plan(state))).is_empty()


@settings(max_examples=300)
@given(_states())
def test_only_what_may_be_removed_is_removed_and_in_removal_order(state: PolicyState) -> None:
    planned = plan(state)

    assert list(planned.removals) == removable(state)[: len(planned.removals)]


@given(_states())
def test_without_a_limit_a_plan_removes_nothing(state: PolicyState) -> None:
    assert plan(dataclasses.replace(state, limit=None)).removals == ()


@settings(max_examples=300)
@given(_states())
def test_every_start_is_a_startable_wanted_track_and_the_active_downloads_stay_bounded(
    state: PolicyState,
) -> None:
    planned = plan(state)

    startable = {
        each.track_id
        for each in state.wanted
        if not each.active_job and each.source_ok and each.site in state.downloadable_sites
    }
    assert {each.track_id for each in planned.starts} <= startable
    assert len({each.source_id for each in planned.starts}) == len(planned.starts)
    assert state.active_policy_jobs + len(planned.starts) <= MAX_ACTIVE


@settings(max_examples=300)
@given(_states())
def test_downloads_started_fit_the_limit_and_leave_the_disk_its_free_space(
    state: PolicyState,
) -> None:
    planned = plan(state)
    after = _applied(state, planned)

    if planned.starts:
        assert after.free - after.reserved >= state.min_free()
        if state.limit is not None:
            assert after.use() <= state.limit


@settings(max_examples=300)
@given(_states())
def test_nothing_is_removed_unless_a_start_or_the_limit_needed_it(state: PolicyState) -> None:
    planned = plan(state)

    if planned.removals and not planned.starts:
        assert state.limit is not None
        assert state.use() > state.limit
        assert _applied(state, planned).use() <= state.limit


@given(_states(), st.randoms())
def test_the_plan_does_not_depend_on_the_order_of_the_snapshot(
    state: PolicyState, random: Random
) -> None:
    shuffled = dataclasses.replace(
        state,
        downloads=tuple(random.sample(state.downloads, len(state.downloads))),
        wanted=tuple(random.sample(state.wanted, len(state.wanted))),
        cache=tuple(random.sample(state.cache, len(state.cache))),
    )

    assert plan(shuffled) == plan(state)


@settings(max_examples=300)
@given(_states())
def test_no_removal_touches_a_wanted_irreplaceable_recent_or_busy_file(state: PolicyState) -> None:
    removed = {each.source_id for each in plan(state).removals if isinstance(each, Remove)}
    removed_cache = {each.name for each in plan(state).removals if isinstance(each, RemoveCache)}

    for download in state.downloads:
        if download.source_id in removed:
            assert not download.wanted
            assert download.replaceable
            assert not download.active_job
            assert state.now - download.touched_at() >= REST
    for copy in state.cache:
        if copy.name in removed_cache:
            assert state.now - copy.touched_at >= REST
