from anki_generator import create_anki_deck


cards = [
    {
        "type": "basic",
        "front": "What is the anatomical position?",
        "back": "Standing upright, facing forward, arms at sides, palms facing anteriorly.",
        "extra": "Test card",
        "tags": [
            "Anatomy"
        ]
    }
]


deck_path = create_anki_deck(
    "MCOM Test Deck",
    cards
)


print(deck_path)