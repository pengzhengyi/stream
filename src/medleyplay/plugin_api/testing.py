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
    `scratch`, an empty folder, and nowhere else. A path that leaves the root must be
    refused.
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
    escaping = FileRequest.model_construct(root=root, path="../outside.mp3")
    try:
        LOCATE_FILE.invoke(backend, escaping)
    except (ValueError, OSError):
        pass
    else:
        message = "The backend located a path outside its root."
        raise ContractError(message)
    return listing


def check_tag_reader(reader: TagReader, request: ReadTags) -> Tags:
    """Check a tag reader against a readable file, and return its tags."""
    tags = check_operation(READ_TAGS, reader, request)
    if tags.duration_ms is not None and tags.duration_ms < 0:
        message = f"A negative duration: {tags.duration_ms} ms."
        raise ContractError(message)
    return tags
