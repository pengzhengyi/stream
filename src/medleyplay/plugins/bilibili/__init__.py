"""The plugin `bilibili`: music from Bilibili videos, read and downloaded with yt-dlp.

Off by default until yt-dlp can read Bilibili again; see the Bilibili design note.
"""

from medleyplay.plugin_api import (
    CREDENTIAL_SPEC,
    SOURCE_DOWNLOADER,
    SOURCE_RESOLVER,
    Plugin,
    Registry,
)
from medleyplay.plugins.bilibili.providers import (
    BilibiliDownloader,
    BilibiliLogin,
    BilibiliResolver,
)


def register(registry: Registry) -> None:
    """Add the resolver, the downloader, and the login check for `bilibili` Sources."""
    registry.add(SOURCE_RESOLVER, "bilibili", BilibiliResolver())
    registry.add(SOURCE_DOWNLOADER, "bilibili", BilibiliDownloader())
    registry.add(CREDENTIAL_SPEC, "bilibili", BilibiliLogin())


plugin = Plugin(api_version=1, register=register)
