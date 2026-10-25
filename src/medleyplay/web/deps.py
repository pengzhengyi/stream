"""Request dependencies: the services, and the signed-in Account."""

from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import Cookie, Depends, Request

from medleyplay.application.accounts import AccountService
from medleyplay.application.catalog import CatalogService
from medleyplay.application.jobs import JobService
from medleyplay.application.libraries import LibraryService
from medleyplay.application.playback import PlaybackService
from medleyplay.application.plugins import PluginService
from medleyplay.domain.accounts import Account
from medleyplay.domain.errors import NotSignedInError

SESSION_COOKIE: Final = "medleyplay_session"


@dataclass(frozen=True)
class Services:
    """The application services one server shares across requests."""

    accounts: AccountService
    catalog: CatalogService
    plugins: PluginService
    jobs: JobService
    libraries: LibraryService
    playback: PlaybackService


def _services(request: Request) -> Services:
    services = request.app.state.services
    if not isinstance(services, Services):  # pragma: no cover -- create_app always sets it
        message = "The app was built without services; use medleyplay.web.app.create_app."
        raise TypeError(message)
    return services


def _accounts(services: Annotated[Services, Depends(_services)]) -> AccountService:
    return services.accounts


def _catalog(services: Annotated[Services, Depends(_services)]) -> CatalogService:
    return services.catalog


def _plugins(services: Annotated[Services, Depends(_services)]) -> PluginService:
    return services.plugins


def _jobs(services: Annotated[Services, Depends(_services)]) -> JobService:
    return services.jobs


def _libraries(services: Annotated[Services, Depends(_services)]) -> LibraryService:
    return services.libraries


def _playback(services: Annotated[Services, Depends(_services)]) -> PlaybackService:
    return services.playback


AccountsDep = Annotated[AccountService, Depends(_accounts)]
CatalogDep = Annotated[CatalogService, Depends(_catalog)]
PluginsDep = Annotated[PluginService, Depends(_plugins)]
JobsDep = Annotated[JobService, Depends(_jobs)]
LibrariesDep = Annotated[LibraryService, Depends(_libraries)]
PlaybackDep = Annotated[PlaybackService, Depends(_playback)]
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE, include_in_schema=False)]


def _signed_in(accounts: AccountsDep, token: SessionToken = None) -> Account:
    if token is None:
        raise NotSignedInError
    return accounts.authenticate(token)


SignedInAccount = Annotated[Account, Depends(_signed_in)]
