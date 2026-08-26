# Official Sonos app gaps

This controller deliberately covers everyday LAN control, not account setup or
every feature in the official mobile app. “Possible” below means technically
reasonable without pretending an undocumented/private interface is stable.

| Official-app capability not fully present here | Can this plugin add it? |
|---|---|
| Universal browsing/search across every connected content service, including private Apple Music library, recommendations, and personal playlists | **Not generically with the current auth-free design.** Each service has different private authentication and catalog behavior. Apple public catalog search works now; private-library search would require a separate, opt-in Apple authentication design and would still not reproduce Sonos's private service session. |
| Add, remove, switch, or reauthenticate music/content-service accounts | **Leave to the official app.** These are account/OAuth flows and the plugin intentionally never receives service credentials. |
| Add a new SMB/NAS music-library share and store its username/password | **Technically conceivable but not appropriate now.** SoCo can list, search, re-index, and delete shares, but has no stable high-level add-with-credentials API. This plugin searches and re-indexes existing shares only. |
| Browse local library by artist, album, genre, composer, and imported playlist | **Possible.** SoCo exposes these views; this release starts with bounded track search. |
| Full queue editing: drag/reorder, replace queue, play in another room, and add whole albums | **Partly possible.** Safe reorder/replace operations and more content containers can be added, but need stale-item checks and service-specific testing. This release supports Play, Next, End, remove, clear, and Sonos Playlist reorder. |
| Alarm source browsing across every music service and changing an existing alarm's room | **Partly possible.** The local alarm API supports room, schedule, duration, grouping, volume, and program metadata. This release safely offers Chime and verified Sonos Favorites and preserves an unknown existing source. Broader sources require careful service metadata handling. |
| Set up a new system, add products, change Wi-Fi, transfer ownership, or reset products | **No, not responsibly through SoCo.** Sonos requires the official mobile/account and device-pairing flows; ownership and reset are especially destructive. |
| Install/check speaker firmware and perform S1/S2 migration | **Leave to the official app.** Firmware orchestration and migrations are account/device operations where an unofficial failure can strand a system. |
| Run Trueplay tuning | **No.** Tuning needs supported mobile hardware, microphones, and Sonos's proprietary calibration flow. This plugin can only enable/disable tuning already stored by a compatible speaker. |
| Create/separate stereo pairs | **Possible but intentionally deferred.** SoCo exposes this topology mutation; marketplace quality needs model compatibility checks, explicit two-stage confirmation, and recovery guidance first. |
| Add/remove Sub or surrounds, TV setup, surround-distance calibration, or Sonos Ace TV Audio Swap | **Mostly no through stable SoCo APIs.** Some post-setup sound levels are available here, but bonding and proprietary TV/headphone setup should remain in the official app. |
| Add/remove voice assistants or configure Alexa, Google Assistant, or Sonos Voice Control | **No in this local design.** These require account authorization and proprietary service setup. Read-only microphone/voice status is shown when reported. |
| AirPlay or Bluetooth pairing/streaming and playing this PC's live audio | **Outside SoCo.** These are OS/hardware media transports, not Sonos queue-control operations. A separate PipeWire/AirPlay sender would be a different plugin and threat model. |
| Account details, parental controls, privacy/security settings, diagnostics upload, and support workflows | **No.** These belong to authenticated Sonos account/support systems and should not be imitated locally. |
| Control away from home | **Possible only as a separate cloud integration.** Sonos's official Control API requires a registered integration, OAuth, a public HTTPS redirect, access/refresh-token storage, and usually server-side secret handling. This plugin is intentionally LAN-only. |
| Official home-screen personalization, recents, favorites editing, and service recommendations | **Some favorites editing may be possible later; personalized feeds are not generic.** They depend on private Sonos/service account data this plugin does not request. |
| Every model-specific option, such as Sub phase, surround distance, line-in autoplay, compression, spatial-music, or special Arc/Ace controls | **Some are possible one by one.** TV Autoplay can now be read and changed explicitly on compatible home-theater speakers; other options should be added only where a tested local interface exists and unsupported models fail safely. Proprietary setup remains official-app territory. |

Primary Sonos references:

- [Supported desktop/mobile feature comparison](https://support.sonos.com/en/article/supported-features-in-the-sonos-desktop-app)
- [Add a content service](https://support.sonos.com/en/article/add-a-content-service-to-sonos)
- [Add a local music library](https://support.sonos.com/en/article/add-your-music-library-to-sonos)
- [Set an alarm](https://support.sonos.com/en-us/article/set-an-alarm-on-sonos)
- [Queue options](https://support.sonos.com/en/article/add-tracks-to-the-queue)
- [Sonos app requirements](https://support.sonos.com/en/article/sonos-app-requirements)
- [Sonos Control API authorization](https://docs.sonos.com/docs/authorize)
