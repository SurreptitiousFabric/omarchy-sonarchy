from sonarchy_backend.artwork import (
    artist_similarity,
    select_artwork_match,
    title_similarity,
)


def candidate(title, artist, artwork, album="Album"):
    return {
        "title": title,
        "artist": artist,
        "album": album,
        "artwork_url": artwork,
    }


def test_classic_fm_metadata_matches_the_choirboys_recording():
    match = select_artwork_match(
        "Requiem - Pie Jesu.",
        "Andrew Lloyd Webber, The Choirboys",
        [
            candidate(
                "Pie Jesu - Album Version",
                "The Choirboys",
                "https://is1-ssl.mzstatic.com/right.jpg",
                "The Choir Boys (EU Version)",
            ),
            candidate(
                "Requiem: Pie Jesu",
                "Duncan Watts",
                "https://is1-ssl.mzstatic.com/wrong.jpg",
            ),
        ],
    )

    assert match is not None
    assert match["title"] == "Pie Jesu - Album Version"
    assert match["artist"] == "The Choirboys"
    assert match["confidence"] >= 0.8


def test_classical_work_title_matches_a_catalog_movement_when_composer_agrees():
    shared_artwork = "https://is1-ssl.mzstatic.com/english-folksong-suite.jpg"
    match = select_artwork_match(
        "English Folksong Suite",
        "Ralph Vaughan Williams",
        [
            candidate(
                'English Folksong Suite: March - "Seventeen Come Sunday"',
                "Sir Adrian Boult, Orchester der Wiener Staatsoper & Ralph Vaughan Williams",
                shared_artwork,
            ),
            candidate(
                'English Folksong Suite: Intermezzo - "My Bonny Boy"',
                "Sir Adrian Boult, Orchester der Wiener Staatsoper & Ralph Vaughan Williams",
                shared_artwork,
            ),
            candidate(
                "English Folksong Suite: II. Intermezzo My Bonny Boy",
                "Royal Liverpool Philharmonic Orchestra & Andrew Manze",
                "https://is1-ssl.mzstatic.com/different-recording.jpg",
            ),
        ],
    )

    assert match is not None
    assert match["artwork_url"] == shared_artwork
    assert match["confidence"] >= 0.85


def test_similarity_handles_work_prefixes_versions_and_multi_artist_metadata():
    assert title_similarity("Requiem - Pie Jesu", "Pie Jesu (Album Version)") > 0.8
    assert artist_similarity("Andrew Lloyd Webber, The Choirboys", "The Choirboys") == 1.0


def test_same_title_with_the_wrong_artist_is_rejected():
    assert (
        select_artwork_match(
            "Pie Jesu",
            "The Choirboys",
            [candidate("Pie Jesu", "Duncan Watts", "https://example.test/wrong.jpg")],
        )
        is None
    )


def test_different_equally_good_recordings_are_treated_as_ambiguous():
    assert (
        select_artwork_match(
            "Song One",
            "Artist Alpha, Artist Beta",
            [
                candidate("Song One", "Artist Alpha", "https://example.test/a.jpg"),
                candidate("Song One", "Artist Beta", "https://example.test/b.jpg"),
            ],
        )
        is None
    )


def test_duplicate_catalog_entries_for_the_same_recording_are_safe():
    match = select_artwork_match(
        "Song One",
        "Artist Alpha",
        [
            candidate("Song One", "Artist Alpha", "https://example.test/a.jpg", "Original"),
            candidate("Song One", "Artist Alpha", "https://example.test/b.jpg", "Collection"),
        ],
    )

    assert match is not None
    assert match["artist"] == "Artist Alpha"


def test_candidates_without_artwork_are_ignored():
    assert select_artwork_match("Song", "Artist", [candidate("Song", "Artist", "")]) is None


def test_empty_metadata_has_no_similarity():
    assert title_similarity("", "Song") == 0.0
    assert artist_similarity("Artist", "") == 0.0


def test_one_word_title_does_not_receive_the_classical_work_boost():
    assert title_similarity("Adagio", "Adagio for Strings: Live") < 0.95
