# Privacy

The plugin has no telemetry, analytics, advertising, or remote account of its
own.

It keeps only the selected room UID and cached private speaker IP addresses on
disk so startup is fast. Now-playing metadata, room/device details, local music
share paths, alarms, volumes, grouping, Favorites, playlists, and queues are
held in memory while the plugin runs. Alarm service URIs and metadata are not
sent to QML.

External requests occur only for requested or explicitly enabled functionality:

- an Apple catalog search sends the typed query and storefront to Apple's
  public iTunes Search API;
- when **Find radio track artwork** is enabled and the popup is open, the title
  and artist currently supplied by Sonos may be sent to that same public Apple
  API. Only confident artwork matches are used, and positive and negative
  results stay in a bounded memory-only cache for the shell session;
- allowlisted public HTTPS artwork may be loaded from a sanitized URL supplied
  by Sonos or an Apple search result;
- Global Player and TuneIn actions contact those connected services as needed.

The plugin does not receive or store the user's Apple Music, Global Player, or
Sonos account password/token. Private Apple Music library search is therefore
not available.

Automatic radio-art matching can be disabled with the `enrichRadioArtwork`
bar setting. Disabling popup artwork also disables matching.

The private Python environment contains only executable dependencies and a
hash of the checked-in lock file. There are no analytics identifiers, account
records, browsing-history databases, or cloud backups created by the plugin.
