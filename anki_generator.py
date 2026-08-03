import genanki
import random
import tempfile


BASIC_MODEL = genanki.Model(
    random.randrange(1 << 30, 1 << 31),
    "MCOM Basic Card",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
        {"name": "Extra"},
    ],
    templates=[
        {
            "name": "Basic",
            "qfmt": "{{Front}}",
            "afmt": "{{FrontSide}}<hr id='answer'>{{Back}}<br><br>{{Extra}}",
        }
    ],
)


CLOZE_MODEL = genanki.Model(
    random.randrange(1 << 30, 1 << 31),
    "MCOM Cloze Card",
    fields=[
        {"name": "Text"},
        {"name": "Extra"},
    ],
    templates=[
        {
            "name": "Cloze",
            "qfmt": "{{cloze:Text}}",
            "afmt": "{{cloze:Text}}<br><br>{{Extra}}",
        }
    ],
    model_type=genanki.Model.CLOZE,
)


def create_anki_deck(
    deck_name: str,
    cards: list,
):

    deck = genanki.Deck(
        random.randrange(1 << 30, 1 << 31),
        deck_name,
    )


    for card in cards:

        card_type = card.get("type", "cloze")


        if card_type == "cloze":

            note = genanki.Note(
                model=CLOZE_MODEL,
                fields=[
                    card.get("text", ""),
                    card.get("extra", ""),
                ],
                tags=card.get("tags", []),
            )


        else:

            note = genanki.Note(
                model=BASIC_MODEL,
                fields=[
                    card.get("front", ""),
                    card.get("back", ""),
                    card.get("extra", ""),
                ],
                tags=card.get("tags", []),
            )


        deck.add_note(note)


    output_file = tempfile.NamedTemporaryFile(
        suffix=".apkg",
        delete=False
    )

    output_file.close()


    genanki.Package(deck).write_to_file(
        output_file.name
    )


    return output_file.name