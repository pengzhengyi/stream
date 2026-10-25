"""The Libraries API: registering, listing, scanning, and removing Libraries."""

from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from medleyplay.domain.libraries import Library, LibraryId, LibraryKind, LibraryState
from medleyplay.web.deps import JobsDep, LibrariesDep, SignedInAccount
from medleyplay.web.jobs import JobOut

router = APIRouter(prefix="/api", tags=["libraries"])


class LibraryIn(BaseModel):
    """A Library to register: a folder, or a zip archive, on this server."""

    name: str = Field(examples=["Music"])
    kind: LibraryKind = Field(examples=["folder"])
    path: str = Field(examples=["~/Music"])


class LibraryOut(BaseModel):
    """A Library as the API shows it."""

    id: int
    name: str
    kind: LibraryKind
    path: str
    state: LibraryState
    message: str
    file_count: int
    added_at: datetime
    last_scanned_at: datetime | None

    @classmethod
    def of(cls, library: Library) -> "LibraryOut":
        """Return the API view of `library`."""
        return cls(**vars(library))


class RegisteredOut(BaseModel):
    """A registered Library, and its first scan when this request registered it."""

    library: LibraryOut
    scan: JobOut | None


@router.post("/libraries", status_code=status.HTTP_201_CREATED)
def register_library(
    body: LibraryIn,
    response: Response,
    me: SignedInAccount,
    libraries: LibrariesDep,
    jobs: JobsDep,
) -> RegisteredOut:
    """Register a Library and scan it; admins only. A root already registered answers 200."""
    registered = libraries.register(me, body.name, body.kind, body.path)
    if not registered.created:
        response.status_code = status.HTTP_200_OK
    scan = None if registered.scan is None else JobOut.of(jobs.get_job(registered.scan.id))
    return RegisteredOut(library=LibraryOut.of(registered.library), scan=scan)


@router.get("/libraries")
def list_libraries(_: SignedInAccount, libraries: LibrariesDep) -> list[LibraryOut]:
    """Return every Library."""
    return [LibraryOut.of(library) for library in libraries.list_libraries()]


@router.post("/libraries/{library_id}/scan")
def scan_library(
    library_id: int,
    me: SignedInAccount,
    libraries: LibrariesDep,
    jobs: JobsDep,
    *,
    full: bool = False,
) -> JobOut:
    """Scan a Library, or return its scan already running; admins only.

    `full` reads every file again, even those that look unchanged.
    """
    job = libraries.scan(me, LibraryId(library_id), full=full)
    return JobOut.of(jobs.get_job(job.id))


@router.delete("/libraries/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_library(library_id: int, me: SignedInAccount, libraries: LibrariesDep) -> None:
    """Remove a Library, and its Tracks found nowhere else; admins only. Removing twice is fine."""
    libraries.remove(me, LibraryId(library_id))
