from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import unquote, urlsplit

from .controller_common import ControllerError
from .model import format_sonos_time

LOG = logging.getLogger(__name__)


class FavoritesMixin:
    @staticmethod
    def _favorite_kind(uri: str) -> str:
        radio_prefixes = (
            "x-sonosapi-stream:",
            "x-sonosapi-radio:",
            "x-rincon-mp3radio:",
            "hls-radio:",
        )
        return "radio" if uri.lower().startswith(radio_prefixes) else "audio"

    @staticmethod
    def _favorite_reference(favorite: Any) -> Any | None:
        try:
            return favorite.reference
        except Exception as exc:  # noqa: BLE001 - malformed favorites are common
            LOG.debug("Could not parse Sonos Favorite reference: %s", exc)
            return None

    @staticmethod
    def _tunein_podcast_id(reference: Any) -> str:
        """Return the TuneIn container id embedded in a Sonos Favorite.

        TuneIn (New) favorites use an AppLink account that SoCo cannot read
        back from the speaker. Podcast ids remain browseable through TuneIn's
        anonymous legacy Sonos service, however, so no developer or user token
        is required.
        """
        desc = str(getattr(reference, "desc", "") or "")
        item_id = str(getattr(reference, "item_id", "") or "")
        if "85255" not in desc or not item_id.startswith("100b2064"):
            return ""
        return unquote(item_id.removeprefix("100b2064"))

    @staticmethod
    def _tunein_service(coordinator: Any) -> Any:
        from soco.music_services import MusicService

        return MusicService("TuneIn", device=coordinator)

    @staticmethod
    def _tunein_media_url(service: Any, episode: Any) -> str:
        """Resolve TuneIn's short M3U response to a direct episode URL."""
        import requests

        media_uri = str(service.get_media_uri(episode.id) or "")
        parsed_media = urlsplit(media_uri)
        hostname = str(parsed_media.hostname or "").casefold().rstrip(".")
        trusted_hosts = ("tunein.com", "radiotime.com")
        if parsed_media.scheme not in {"http", "https"} or not any(
            hostname == suffix or hostname.endswith("." + suffix) for suffix in trusted_hosts
        ):
            raise ControllerError("TuneIn returned an invalid podcast media URL")

        with requests.get(
            media_uri,
            timeout=10,
            stream=True,
            allow_redirects=False,
        ) as response:
            if 300 <= response.status_code < 400:
                redirect = str(response.headers.get("location", "") or "")
                if urlsplit(redirect).scheme in {"http", "https"}:
                    return redirect
                raise ControllerError("TuneIn returned an invalid podcast redirect")
            response.raise_for_status()
            content_type = str(response.headers.get("content-type", "")).lower()
            if "mpegurl" not in content_type and not media_uri.lower().endswith((".m3u", ".m3u8")):
                return media_uri

            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=4096):
                size += len(chunk)
                if size > 256 * 1024:
                    raise ControllerError("TuneIn returned an oversized podcast playlist")
                chunks.append(chunk)

        playlist = b"".join(chunks).decode("utf-8", errors="replace")
        for line in playlist.splitlines():
            candidate = line.strip()
            if not candidate or candidate.startswith("#"):
                continue
            if urlsplit(candidate).scheme in {"http", "https"}:
                return candidate
        raise ControllerError("TuneIn returned an empty podcast playlist")

    @staticmethod
    def _podcast_playback_metadata(episode: Any, media_url: str) -> str:
        """Build rich DIDL metadata for a resolved TuneIn podcast episode."""
        episode_metadata = getattr(episode, "metadata", {})
        if not isinstance(episode_metadata, dict):
            episode_metadata = {}
        track_metadata = getattr(episode_metadata.get("track_metadata"), "metadata", {})
        if not isinstance(track_metadata, dict):
            track_metadata = {}

        title = str(getattr(episode, "title", "") or "Podcast")
        show = str(track_metadata.get("podcast") or track_metadata.get("associated_show") or "")
        artist = str(
            track_metadata.get("host")
            or track_metadata.get("artist")
            or track_metadata.get("producer")
            or ""
        )
        artwork = str(track_metadata.get("album_art_uri") or "")
        if urlsplit(artwork).scheme not in {"http", "https"}:
            artwork = ""

        didl_ns = "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
        dc_ns = "http://purl.org/dc/elements/1.1/"
        upnp_ns = "urn:schemas-upnp-org:metadata-1-0/upnp/"
        rincon_ns = "urn:schemas-rinconnetworks-com:metadata-1-0/"
        ET.register_namespace("", didl_ns)
        ET.register_namespace("dc", dc_ns)
        ET.register_namespace("upnp", upnp_ns)
        ET.register_namespace("r", rincon_ns)
        root = ET.Element(f"{{{didl_ns}}}DIDL-Lite")
        item = ET.SubElement(
            root,
            f"{{{didl_ns}}}item",
            {"id": "R:0/0/0", "parentID": "R:0/0", "restricted": "true"},
        )
        ET.SubElement(item, f"{{{dc_ns}}}title").text = title
        ET.SubElement(item, f"{{{upnp_ns}}}class").text = "object.item.audioItem.musicTrack"
        if artist:
            ET.SubElement(item, f"{{{dc_ns}}}creator").text = artist
            ET.SubElement(item, f"{{{upnp_ns}}}artist").text = artist
        if show:
            ET.SubElement(item, f"{{{upnp_ns}}}album").text = show
        if artwork:
            ET.SubElement(item, f"{{{upnp_ns}}}albumArtURI").text = artwork
        description = str(getattr(episode, "desc", "") or "SA_RINCON65031_")
        desc = ET.SubElement(
            item,
            f"{{{didl_ns}}}desc",
            {"id": "cdudn", "nameSpace": rincon_ns},
        )
        desc.text = description
        resource = ET.SubElement(
            item,
            f"{{{didl_ns}}}res",
            {"protocolInfo": "http-get:*:audio/mpeg:*"},
        )
        duration = track_metadata.get("duration")
        try:
            if duration is not None:
                resource.set("duration", format_sonos_time(int(duration)))
        except TypeError, ValueError:
            pass
        resource.text = media_url
        return ET.tostring(root, encoding="unicode")

    @staticmethod
    def _favorite_is_directly_playable(uri: str) -> bool:
        """Keep the MVP on URI types Sonos accepts via SetAVTransportURI.

        In particular, ``x-rincon-cpcontainer`` Favorites are albums, mixes,
        or playlists which must be expanded into a queue before playback.
        Treating those as direct audio produces UPnP 714 on real speakers.
        """
        direct_prefixes = (
            "http:",
            "https:",
            "x-file-cifs:",
            "x-rincon-mp3radio:",
            "x-sonos-http:",
            "x-sonos-https:",
            "x-sonosapi-radio:",
            "x-sonosapi-stream:",
            "hls-radio:",
        )
        return uri.lower().startswith(direct_prefixes)

    def refresh_favorites(self) -> None:
        self._favorites_loaded = True
        self._favorites_household_id = self._target_household_id
        self._favorite_objects = {}
        if self._target_group is None:
            self._favorites_model = {
                "state": "error",
                "items": [],
                "total": 0,
                "unsupported": 0,
                "error": "No target Sonos group is available",
            }
            return
        try:
            coordinator = self._target_group.coordinator
            result = coordinator.music_library.get_sonos_favorites(
                complete_result=True,
                max_items=100,
            )
            favorites = list(result)
            total = int(getattr(result, "total_matches", len(favorites)))
            items: list[dict[str, str]] = []
            for favorite in favorites:
                resources = list(getattr(favorite, "resources", []) or [])
                uri = str(getattr(resources[0], "uri", "") or "") if resources else ""
                metadata = str(getattr(favorite, "resource_meta_data", "") or "")
                title = self._clean_name(getattr(favorite, "title", ""), "Favorite")
                reference = self._favorite_reference(favorite) if metadata else None
                artwork = self._safe_artwork_url(
                    getattr(favorite, "album_art_uri", "")
                    or getattr(reference, "album_art_uri", ""),
                    getattr(coordinator, "ip_address", ""),
                )
                playback: dict[str, Any] | None = None
                kind = self._favorite_kind(uri)
                identity = uri
                if uri and metadata and self._favorite_is_directly_playable(uri):
                    playback = {
                        "mode": "direct",
                        "uri": uri,
                        "metadata": metadata,
                    }
                elif uri.lower().startswith("x-rincon-cpcontainer:") and reference:
                    playback = {"mode": "queue", "item": reference}
                elif reference:
                    podcast_id = self._tunein_podcast_id(reference)
                    if podcast_id:
                        playback = {
                            "mode": "tuneinPodcast",
                            "podcastId": podcast_id,
                        }
                        identity = podcast_id
                        kind = "podcast"
                if playback is None:
                    continue
                favorite_id = hashlib.sha256(
                    f"{title}\0{identity}\0{metadata}".encode()
                ).hexdigest()[:20]
                self._favorite_objects[favorite_id] = playback
                items.append(
                    {
                        "id": favorite_id,
                        "title": title,
                        "kind": kind,
                        "albumArtUrl": artwork,
                    }
                )
            self._favorites_model = {
                "state": "ready",
                "items": items,
                "total": total,
                "unsupported": max(0, total - len(items)),
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001 - favorites must not break control
            LOG.warning("Could not load Sonos Favorites: %s", exc)
            self._favorites_model = {
                "state": "error",
                "items": [],
                "total": 0,
                "unsupported": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def play_favorite(self, favorite_id: str) -> None:
        favorite = self._favorite_objects.get(favorite_id)
        if favorite is None:
            raise ControllerError("Unknown or unavailable Sonos Favorite")
        coordinator = self._coordinator()
        mode = favorite["mode"]
        if mode == "direct":
            coordinator.play_uri(
                uri=favorite["uri"],
                meta=favorite["metadata"],
                start=True,
            )
            return
        if mode == "queue":
            queue_position = coordinator.add_to_queue(favorite["item"])
            coordinator.play_from_queue(queue_position - 1)
            return
        if mode == "tuneinPodcast":
            try:
                service = self._tunein_service(coordinator)
                episodes = service.get_metadata(
                    favorite["podcastId"],
                    count=1,
                )
                episode = next(iter(episodes))
                media_url = self._tunein_media_url(service, episode)
                metadata = self._podcast_playback_metadata(episode, media_url)
                coordinator.play_uri(
                    uri=media_url,
                    meta=metadata,
                    start=True,
                )
                return
            except (StopIteration, TypeError) as exc:
                raise ControllerError("TuneIn did not return a playable podcast episode") from exc
            except ControllerError:
                raise
            except Exception as exc:
                raise ControllerError(
                    f"Could not load the TuneIn podcast: {type(exc).__name__}: {exc}"
                ) from exc
        raise ControllerError("Unsupported Sonos Favorite playback mode")
