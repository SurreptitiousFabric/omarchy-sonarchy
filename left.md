# What remains before publishing Sonarchy

Recorded on 2026-09-08 after reconciling the existing acceptance results.

These are **gaps in our test records, not confirmed bugs**. They were included
in the original pre-publication checklist to check that the advertised features
work on real speakers. Matching passing results have not been found for these
specific cases. That does not prove the owner has never done them.

## 1. Browsing and playing your local music library

This means music files Sonos has indexed from your computer or a shared drive.
We have evidence that Sonarchy can read the library, and automated tests cover
navigation. The missing result is someone browsing through real folders or
albums, changing pages where available, then playing the selected music. The
original check also includes safely rejecting an old selection if the library
has changed.

**Why it was included:** to check that navigating real library contents plays
the item you actually selected, and does not play something else when a selection
is out of date.

## 2. Putting music into the queue

“Play now,” “Play next” and “Add to end” should put the selected music in the
right place. Some queue operations and playlist playback have already passed.
The missing results concern particular music sources and the buttons in
Sonarchy’s interface, including what the screen shows if a speaker rejects an
action.

**Why it was included:** to catch music being inserted in the wrong place, the
wrong track starting, or the screen showing a change that the speaker never
accepted.

This does not reopen the separate destructive queue-restoration project or
authorize replacing an existing queue.

## 3. Changing an alarm’s room, and handling a failed alarm edit

**The owner’s alarm works. That is recorded as passed.** The narrower questions
are whether moving an alarm to another room preserves its time and other
settings, and whether a rejected edit leaves the screen showing the alarm’s
actual settings.

**Why it was included:** to avoid an edit accidentally changing other alarm
settings or appearing saved when it wasn’t.

## 4. Displaying the TV’s audio format

Sonarchy can display the format the speaker reports, such as stereo or Dolby.
We checked the idle and unsupported cases. The missing comparison is Sonarchy
versus the official Sonos app while TV audio is actually playing.

**Why it was included:** to check that the displayed information is accurate.

## 5. Switching between music, TV and Line-In

Line-In means audio coming through a speaker’s physical input. Changing the TV
Autoplay setting has passed. The separate missing result is deliberately
switching sources on hardware that supports them and then returning to the
original source.

**Why it was included:** to check that the source buttons select the intended
input and let you return successfully.

## 6. The remaining playback and room-group controls

Playback, seeking, stopping, grouping and volume controls already have passing
results. Matching results have not been found for pause, previous/next, certain
ungroup/group-all actions, applying a prepared group-membership change, selecting
a playback session, or moving playback between rooms and restoring the agreed
setup. Cancelling a prepared group change in the interface has passed.

**Why it was included:** to check that these particular controls affect the
intended music and rooms without leaving the setup unexpectedly changed.

## 7. Recovering when a speaker disappears

Restarting Sonarchy’s backend and reconnecting MCP already passed. The missing
cases concern a speaker becoming unreachable, returning later, and ordinary
playback, grouping and idle use over a recorded period.

**Why it was included:** to catch stale room information, failure to reconnect,
or errors that build up over time.

## 8. An album continuing to its second track

Individual playback works, and a two-track Apple share-link test advanced
automatically. The whole-album case is separate: an earlier attempt was
interrupted by TV Autoplay.

**Why it was included:** to confirm that starting an album continues playing it,
rather than only proving that its first track starts.

## 9. Favorites, radio playback and artwork

Reading Favorites and searching Global Player passed. The missing results
concern starting those streams and showing suitable artwork as the station’s
current song changes.

**Why it was included:** to check that a playable search result actually plays
and that uncertain song matches don’t display misleading artwork.

## 10. Checking a renamed room in the official app

Renaming the speaker and restoring its name already passed. The missing record
is comparing those names with the official Sonos app.

**Why it was included:** to check that both apps agree. This is a narrower
consistency check; it does not mean room renaming is broken.

## How to settle these gaps

We do not automatically need to repeat all of these. An existing result or the
owner’s confirmation may settle a gap. The owner can also explicitly decide
that a particular check is unnecessary for this beta. An unverified case must
not be called passed, and a missing record must not automatically become another
test the owner is asked to perform.

This list does not authorize speaker changes, desktop interaction or new tests.
Completed keyboard/layout checks, the alarm confirmation repair, installation
lifecycle checks, code reviews and the amended QML platform gate remain credited.
The documented upstream QML warnings do not block publication.

## Final publication steps

- Run the final marketplace baseline and check that the permanent plugin ID is
  available for the selected release commit. Refresh other checks only as
  required by changes to that candidate.
- Obtain the owner’s approval of the release commit and submission package.

For the exact evidence and issue mapping, see
[the reconciled acceptance record](docs/acceptance-status.md) and
[the detailed checklist](ACCEPTANCE_TESTS.md).
