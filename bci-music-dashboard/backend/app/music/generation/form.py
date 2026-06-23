from __future__ import annotations

from dataclasses import dataclass

from app.music.schemas import FormSection


@dataclass(frozen=True)
class FormPosition:
    section: FormSection
    phrase_id: str
    phrase_index: int
    section_phrase: int
    section_changed: bool
    is_final: bool


class CompositionStateMachine:
    BASE_SECTIONS: tuple[tuple[FormSection, int], ...] = (
        ("intro", 1),
        ("theme", 2),
        ("variation", 2),
        ("climax", 1),
        ("return", 2),
        ("coda", 1),
    )

    def __init__(self) -> None:
        self.positions: list[tuple[FormSection, int]] = []
        self.index = 0
        self.configure(84, 240)

    def configure(self, bpm: int, target_duration_seconds: int) -> None:
        phrase_seconds = 8 * 4 * 60 / max(30, bpm)
        base_phrases = sum(count for _, count in self.BASE_SECTIONS)
        required = round(target_duration_seconds / phrase_seconds) - base_phrases
        development_phrases = max(0, min(6, required))
        sections = (
            ("intro", 1),
            ("theme", 2),
            ("variation", 2),
            ("development", development_phrases),
            ("climax", 1),
            ("return", 2),
            ("coda", 1),
        )
        self.positions = [
            (section, phrase)
            for section, count in sections
            for phrase in range(count)
        ]
        self.index = 0

    def reset(self) -> None:
        self.index = 0

    def current(self) -> FormPosition:
        index = min(self.index, len(self.positions) - 1)
        section, section_phrase = self.positions[index]
        previous = self.positions[index - 1][0] if index > 0 else None
        return FormPosition(
            section=section,
            phrase_id=f"{section}-{section_phrase + 1}",
            phrase_index=index,
            section_phrase=section_phrase,
            section_changed=section != previous,
            is_final=index == len(self.positions) - 1,
        )

    def advance(self) -> None:
        self.index = min(self.index + 1, len(self.positions))

    @property
    def complete(self) -> bool:
        return self.index >= len(self.positions)

    @property
    def total_phrases(self) -> int:
        return len(self.positions)
