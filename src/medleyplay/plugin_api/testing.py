"""The contract kit: checks every provider of an operation must pass, for plugins' tests."""

from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ValidationError

from medleyplay.plugin_api.extension import Operation
from medleyplay.plugin_api.library import (
    CHECK_ROOT,
    FETCH_FILE,
    FINGERPRINT_FILE,
    LIST_FILES,
    LOCATE_FILE,
    CheckRoot,
    FetchFile,
    FileList,
    FileRequest,
    LibraryBackend,
    LibraryRoot,
    ListFiles,
)
from medleyplay.plugin_api.sources import (
    CANONICALIZE,
    CHECK_LOGIN,
    DOWNLOAD_PART,
    READ_VIDEO,
    Canonical,
    Canonicalize,
    CheckedLogin,
    CheckLogin,
    CredentialSpec,
    Downloaded,
    DownloadPart,
    ReadVideo,
    SourceDownloader,
    SourceResolver,
    VideoDetails,
    VideoStatus,
)
from medleyplay.plugin_api.tags import READ_TAGS, ReadTags, TagReader, Tags


class ContractError(AssertionError):
    """A provider broke its extension point's contract."""


def check_operation[P, I: BaseModel, O: BaseModel](
    operation: Operation[P, I, O], provider: P, request: I
) -> O:
    """Call `operation` on `provider` twice and return the reply.

    The reply must be the operation's reply model, survive a JSON round trip
    unchanged, as it must to cross the pipe, and be the same both times.
    """
    first = operation.invoke(provider, request)
    check_round_trip(first)
    second = operation.invoke(provider, request)
    if second != first:
        message = f"Calling twice gave different replies: {first!r}, then {second!r}."
        raise ContractError(message)
    return first


def check_round_trip(model: BaseModel) -> None:
    """Check that `model` survives a JSON round trip unchanged."""
    try:
        again = type(model).model_validate_json(model.model_dump_json())
    except ValidationError as error:
        message = f"{model!r} doesn't survive a JSON round trip: {error}"
        raise ContractError(message) from error
    if again != model:
        message = f"{model!r} became {again!r} in a JSON round trip."
        raise ContractError(message)


def check_library_backend(
    backend: LibraryBackend, root: LibraryRoot, extensions: frozenset[str], scratch: Path
) -> FileList:
    """Check a backend against a readable `root`, and return its listing.

    Every listed file must have a requested extension, a fingerprint that stays the
    same, and a location within its bounds; a compressed file must fetch into
    `scratch`, an empty folder, and nowhere else. A file the listing lacks must be
    missing, and a path that leaves the root must be refused or missing.
    """
    if not check_operation(CHECK_ROOT, backend, CheckRoot(root=root)).readable:
        message = f"The backend can't read {root!r}."
        raise ContractError(message)
    listing = check_operation(LIST_FILES, backend, ListFiles(root=root, extensions=extensions))
    for file in listing.files:
        if PurePosixPath(file.path).suffix.lower().removeprefix(".") not in extensions:
            message = f"{file.path!r} doesn't have a requested extension."
            raise ContractError(message)
        request = FileRequest(root=root, path=file.path)
        check_operation(FINGERPRINT_FILE, backend, request)
        location = check_operation(LOCATE_FILE, backend, request)
        if location.missing:
            message = f"A listed file, {file.path!r}, was located as missing."
            raise ContractError(message)
        if location.compressed or location.local_path is None:
            fetched = FETCH_FILE.invoke(
                backend, FetchFile(root=root, path=file.path, folder=str(scratch))
            )
            if not Path(fetched.local_path).resolve().is_relative_to(scratch.resolve()):
                message = f"{file.path!r} was fetched outside {scratch}."
                raise ContractError(message)
        elif location.offset + location.length > Path(location.local_path).stat().st_size:
            message = f"The location of {file.path!r} runs past the end of its file."
            raise ContractError(message)
    _check_unlisted(backend, root, min(extensions), len(listing.files))
    return listing


def _check_unlisted(backend: LibraryBackend, root: LibraryRoot, extension: str, n: int) -> None:
    absent = FileRequest(root=root, path=f"not-listed-{n}.{extension}")
    if not check_operation(LOCATE_FILE, backend, absent).missing:
        message = f"{absent.path!r} isn't listed, but wasn't located as missing."
        raise ContractError(message)
    escaping = FileRequest.model_construct(root=root, path=f"../outside.{extension}")
    try:
        escaped = LOCATE_FILE.invoke(backend, escaping)
    except (ValueError, OSError):
        return
    if not escaped.missing:
        message = "The backend located a path outside its root."
        raise ContractError(message)


def check_tag_reader(reader: TagReader, request: ReadTags) -> Tags:
    """Check a tag reader against a readable file, and return its tags."""
    tags = check_operation(READ_TAGS, reader, request)
    if tags.duration_ms is not None and tags.duration_ms < 0:
        message = f"A negative duration: {tags.duration_ms} ms."
        raise ContractError(message)
    return tags


def check_source_resolver(
    resolver: SourceResolver, link: str
) -> tuple[Canonical, VideoDetails | None]:
    """Check a resolver against a link, and return what it names and, for a video, its details.

    A readable video has parts and qualities, none named twice; one that can't be
    read has neither.
    """
    canonical = check_operation(CANONICALIZE, resolver, Canonicalize(link=link))
    if canonical.video is None:
        if canonical.part is not None:
            message = f"{link!r} names a part, {canonical.part}, but no video."
            raise ContractError(message)
        return canonical, None
    details = check_operation(READ_VIDEO, resolver, ReadVideo(video=canonical.video))
    if details.status is not VideoStatus.OK:
        if details.parts or details.qualities:
            message = f"A video that is {details.status} has parts or qualities."
            raise ContractError(message)
        return canonical, details
    parts = [part.part for part in details.parts]
    qualities = [quality.id for quality in details.qualities]
    if not parts or len(set(parts)) != len(parts):
        message = f"A readable video's parts must be there and distinct, not {parts}."
        raise ContractError(message)
    if not qualities or len(set(qualities)) != len(qualities):
        message = f"A readable video's qualities must be there and distinct, not {qualities}."
        raise ContractError(message)
    return canonical, details


def check_source_downloader(downloader: SourceDownloader, request: DownloadPart) -> Downloaded:
    """Check a downloader against a part, and return what it downloaded.

    The file must be a regular file named bare, directly in the request's folder,
    with the quality it got; a part that is gone has no file.
    """
    downloaded = check_operation(DOWNLOAD_PART, downloader, request)
    if downloaded.gone or downloaded.file is None:
        if downloaded.file is not None or not downloaded.gone:
            message = "A download must name its file, or say the part is gone, not both."
            raise ContractError(message)
        return downloaded
    path = Path(request.folder) / downloaded.file
    if PurePosixPath(downloaded.file).name != downloaded.file or path.is_symlink():
        message = f"{downloaded.file!r} isn't a bare file name."
        raise ContractError(message)
    if not path.is_file() or downloaded.quality is None:
        message = f"{downloaded.file!r} isn't a file in the folder with the quality it got."
        raise ContractError(message)
    return downloaded


def check_credential_spec(spec: CredentialSpec, text: str) -> CheckedLogin:
    """Check a credential spec against a pasted login, and return what it keeps.

    A valid login keeps something, and checking what it kept keeps it unchanged.
    """
    checked = check_operation(CHECK_LOGIN, spec, CheckLogin(text=text))
    if not checked.valid:
        if checked.login:
            message = "A login that isn't valid keeps nothing."
            raise ContractError(message)
        return checked
    again = check_operation(CHECK_LOGIN, spec, CheckLogin(text=checked.login))
    if again != checked:
        message = f"Checking the kept login again gave {again!r}, not {checked!r}."
        raise ContractError(message)
    return checked
