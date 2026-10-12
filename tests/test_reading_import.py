"""Fail-closed reading import tests using entirely original practice text.

The fixture mirrors the public CET paper layout without reproducing exam
questions. These tests exercise extracted text, so they do not need pypdf.
"""
import unittest

from tools.import_reading import (
    ReadingImportError, build_pack, parse_answers, parse_careful_reading_text,
    parse_reading_text,
)


LETTERS = "ABCDEFGHIJKLMNO"
ANSWERS = dict(zip(range(26, 36), "ABCDEFGHIJ"))
ANSWERS.update(zip(range(36, 46), "ABCDEFGHIJ"))
ANSWERS.update(zip(range(46, 56), "ABCDABCDAB"))


def answer_table(answers=None, groups=(10, 10, 10)):
    answers = ANSWERS if answers is None else answers
    rows = []
    first = 26
    for size in groups:
        numbers = list(range(first, first + size))
        rows.append(" ".join(str(number) for number in numbers))
        rows.append(" ".join(answers[number] for number in numbers))
        first += size
    return "KEYS\nPart III Reading Comprehension\n" + "\n".join(rows)


def original_reading_paper():
    paragraphs = [
        "Part III Reading Comprehension (40 minutes)",
        "Section A",
        "Directions: In this section, there is a passage with ten blanks. "
        "Select one word for each blank from the word bank.",
        "",
        "A community garden opens beside a small library. "
        + " ".join(f"Learners use ___{number}___ during their weekly meetings."
                   for number in range(26, 36)),
        "",
    ]
    paragraphs.extend(f"{letter}) gardenword{letter.lower()}" for letter in LETTERS)
    paragraphs.extend([
        "Section B",
        "Directions: Each statement contains information given in one paragraph. "
        "Identify the paragraph from which the information is derived.",
        "",
        "A library garden for everyone",
    ])
    paragraphs.extend(f"{letter}) Original paragraph {letter} describes activity "
                      f"{letter.lower()} at the library garden."
                      for letter in "ABCDEFGHIJ")
    paragraphs.extend(f"{number}. Original statement {number} concerns activity "
                      f"{letter.lower()} in the garden."
                      for number, letter in zip(range(36, 46), "ABCDEFGHIJ"))
    paragraphs.extend([
        "Section C",
        "Directions: Read the following passages and choose the best answer.",
        "Passage One",
        "Questions 46 to 50 are based on the following passage.",
        "The first original passage describes a quiet bicycle workshop. "
        "Volunteers teach visitors to repair old bicycles every Saturday.",
    ])
    for number in range(46, 56):
        if number == 51:
            paragraphs.extend([
                "Passage Two",
                "Questions 51 to 55 are based on the following passage.",
                "The second original passage describes a local science club. "
                "Members measure rain and share their observations every Friday.",
            ])
        paragraphs.extend([
            f"{number}. What does original question {number} ask about?",
            f"A) Choice A for question {number}. C) Choice C for question {number}.",
            f"B) Choice B for question {number}. D) Choice D for question {number}.",
        ])
    paragraphs.extend([
        "Part IV Translation (30 minutes)",
        "This original translation prompt is outside the reading section.",
        answer_table(),
    ])
    return "\n".join(paragraphs)


def reformatted_careful_paper():
    paper = original_reading_paper()
    articles = paper[paper.index("Passage One\n"):paper.index("\nPart IV Translation")]
    for first, last in ((46, 50), (51, 55)):
        articles = articles.replace(
            f"Questions {first} to {last} are based on the following passage.\n", "", 1)
    return ("Part III · Reading Comprehension\nSection C Passages\n"
            + articles + "\nPart IV · Translation\nAn original translation prompt.")


def reformatted_answers(*, explanatory_prose=False):
    rows = ["Part III Reading Comprehension"]
    for first in (26, 36, 46):
        rows.append(" ".join(f"{number} {ANSWERS[number]}"
                             for number in range(first, first + 10)))
        if explanatory_prose:
            rows.append(f"{first}. Original explanation: a printed reference such as "
                        f"{first} A is explanatory prose, rather than an answer-table row.")
    rows.extend(["Part IV Translation", "An original model translation outside the table."])
    return "\n".join(rows)


class AnswerExtractionTests(unittest.TestCase):
    def test_three_complete_number_and_letter_rows(self):
        self.assertEqual(parse_answers(answer_table()), ANSWERS)

    def test_external_quick_answers_can_use_different_row_lengths(self):
        self.assertEqual(parse_answers(answer_table(groups=(13, 13, 4))), ANSWERS)

    def test_missing_answer_is_rejected(self):
        damaged = answer_table().replace("A B C D A B C D A B", "A B C D A B C D A", 1)
        with self.assertRaises(ReadingImportError):
            parse_answers(damaged)

    def test_duplicate_answer_number_is_rejected(self):
        damaged = answer_table().replace("26 27 28", "26 26 28", 1)
        with self.assertRaises(ReadingImportError):
            parse_answers(damaged)

    def test_missing_entire_answer_group_is_rejected(self):
        damaged = answer_table().rsplit("\n", 2)[0]
        with self.assertRaises(ReadingImportError):
            parse_answers(damaged)


class ReadingExtractionTests(unittest.TestCase):
    def setUp(self):
        self.paper = original_reading_paper()

    def assert_rejected(self, text, **kwargs):
        with self.assertRaises(ReadingImportError):
            parse_reading_text(text, **kwargs)

    def test_all_thirty_questions_have_original_numbers_and_options(self):
        sections = parse_reading_text(self.paper)
        self.assertEqual([section["id"] for section in sections],
                         ["reading-cloze", "reading-matching", "reading-careful"])
        self.assertTrue(all(section["kind"] == "reading" for section in sections))
        self.assertEqual([len(section["questions"]) for section in sections], [10, 10, 10])
        for start, section, options in zip((26, 36, 46), sections,
                                          (LETTERS, "ABCDEFGHIJ", "ABCD")):
            self.assertEqual([question["id"] for question in section["questions"]],
                             [f"q{number}" for number in range(start, start + 10)])
            for number, question in zip(range(start, start + 10), section["questions"]):
                self.assertEqual(question["type"], "choice")
                self.assertEqual([option["id"] for option in question["options"]],
                                 list(options))
                self.assertEqual(question["answer"], ANSWERS[number])
        self.assertEqual(
            {option["id"]: option["text"] for option in sections[0]["questions"][0]["options"]},
            {letter: f"gardenword{letter.lower()}" for letter in LETTERS},
        )

    def test_two_column_options_keep_their_actual_labels_and_text(self):
        questions = parse_reading_text(self.paper)[2]["questions"]
        for number, question in zip(range(46, 56), questions):
            choices = {option["id"]: option["text"] for option in question["options"]}
            for letter in "ABCD":
                self.assertEqual(choices[letter], f"Choice {letter} for question {number}.")
            self.assertIn(f"What does original question {number} ask about?", question["prompt"])

    def test_passages_and_matching_statements_are_preserved(self):
        sections = parse_reading_text(self.paper)
        self.assertIn("community garden", sections[0]["passage"])
        self.assertIn("Original paragraph J", sections[1]["passage"])
        self.assertIn("Original statement 36", sections[1]["questions"][0]["prompt"])
        self.assertIn("Passage One", sections[2]["passage"])
        self.assertIn("Passage Two", sections[2]["passage"])
        self.assertIn("quiet bicycle workshop", sections[2]["passage"])
        self.assertIn("local science club", sections[2]["passage"])
        self.assertNotIn("translation prompt", sections[2]["passage"])

    def test_missing_cloze_blank_is_rejected(self):
        self.assert_rejected(self.paper.replace("___30___", "an unnumbered gap", 1))

    def test_cloze_intro_before_the_first_numbered_gap_is_preserved(self):
        text = self.paper.replace("A community garden opens beside", "An opening paragraph has no gaps.\n\nA community garden opens beside", 1)
        passage = parse_reading_text(text)[0]["passage"]
        self.assertTrue(passage.startswith("An opening paragraph has no gaps."))
        self.assertIn("community garden", passage)

    def test_duplicate_cloze_blank_is_rejected(self):
        self.assert_rejected(self.paper.replace("___30___", "___29___", 1))

    def test_missing_word_bank_choice_is_rejected(self):
        self.assert_rejected(self.paper.replace("O) gardenwordo\n", "", 1))

    def test_missing_matching_paragraph_is_rejected(self):
        self.assert_rejected(self.paper.replace(
            "J) Original paragraph J describes activity j at the library garden.\n", "", 1))

    def test_missing_matching_statement_is_rejected(self):
        self.assert_rejected(self.paper.replace(
            "40. Original statement 40 concerns activity e in the garden.\n", "", 1))

    def test_missing_period_does_not_lose_an_unambiguous_numbered_stem(self):
        text = self.paper.replace("43. Original statement", "43 Original statement", 1)
        text = text.replace("48. What does", "48 What does", 1)
        sections = parse_reading_text(text)
        self.assertIn("Original statement 43", sections[1]["questions"][7]["prompt"])
        self.assertIn("What does original question 48 ask about?", sections[2]["questions"][2]["prompt"])

    def test_missing_careful_option_is_rejected(self):
        self.assert_rejected(self.paper.replace(" D) Choice D for question 49.", "", 1))

    def test_duplicate_careful_question_number_is_rejected(self):
        self.assert_rejected(self.paper.replace("49. What does original question 49", 
                                               "48. What does original question 49", 1))

    def test_wrong_passage_question_range_is_rejected(self):
        self.assert_rejected(self.paper.replace("Questions 51 to 55", "Questions 50 to 54", 1))

    def test_answers_outside_each_sections_choices_are_rejected(self):
        for number, wrong_answer in ((26, "P"), (36, "K"), (46, "E")):
            with self.subTest(question=number):
                answers = dict(ANSWERS)
                answers[number] = wrong_answer
                text = self.paper.replace(answer_table(), answer_table(answers))
                self.assert_rejected(text)

    def test_matching_external_answers_are_accepted(self):
        sections = parse_reading_text(self.paper, answer_text=answer_table(groups=(13, 13, 4)))
        self.assertEqual(sections[2]["questions"][-1]["answer"], ANSWERS[55])

    def test_conflicting_external_answers_are_rejected(self):
        answers = dict(ANSWERS)
        answers[26] = "O"
        self.assert_rejected(self.paper, answer_text=answer_table(answers))

    def test_external_answers_allow_papers_without_embedded_keys(self):
        text = self.paper.split("\nKEYS\n", 1)[0]
        sections = parse_reading_text(text, answer_text=answer_table())
        self.assertEqual(sum(len(section["questions"]) for section in sections), 30)

    def test_no_answer_source_is_rejected(self):
        self.assert_rejected(self.paper.split("\nKEYS\n", 1)[0])

    def test_pack_is_importable_schema_and_does_not_claim_verification(self):
        pack = build_pack(self.paper, level="CET4", year=2024, session="2024.06",
                          paper_number=3, source_url="https://example.test/original-practice.pdf",
                          exam_id="synthetic-reading-2024")
        self.assertEqual(pack["schema_version"], 1)
        self.assertEqual(len(pack["exams"]), 1)
        exam = pack["exams"][0]
        self.assertEqual(exam["id"], "synthetic-reading-2024")
        self.assertEqual(exam["level"], "CET4")
        self.assertEqual(exam["year"], 2024)
        self.assertEqual(exam["source"]["url"], "https://example.test/original-practice.pdf")
        self.assertIs(exam["source"]["verified"], False)
        self.assertEqual(sum(len(section["questions"]) for section in exam["sections"]), 30)


class ReformattedCarefulReadingTests(unittest.TestCase):
    def setUp(self):
        self.paper = reformatted_careful_paper()
        self.answers = reformatted_answers()

    def test_only_ten_careful_questions_are_imported_with_actual_passages_and_choices(self):
        sections = parse_careful_reading_text(self.paper, answer_text=self.answers)
        self.assertEqual(len(sections), 1)
        section = sections[0]
        self.assertEqual((section["id"], section["kind"]), ("reading-careful", "reading"))
        self.assertIn("仅此部分", section["title"])
        self.assertEqual([q["id"] for q in section["questions"]],
                         [f"q{number}" for number in range(46, 56)])
        self.assertIn("quiet bicycle workshop", section["passage"])
        self.assertIn("local science club", section["passage"])
        self.assertNotIn("translation prompt", section["passage"])
        for number, question in zip(range(46, 56), section["questions"]):
            self.assertIn(f"What does original question {number} ask about?", question["prompt"])
            self.assertEqual(question["answer"], ANSWERS[number])
            self.assertEqual({option["id"]: option["text"] for option in question["options"]},
                             {letter: f"Choice {letter} for question {number}."
                              for letter in "ABCD"})

    def test_explanatory_prose_is_ignored_without_becoming_an_answer_row(self):
        sections = parse_careful_reading_text(
            self.paper, answer_text=reformatted_answers(explanatory_prose=True))
        self.assertEqual([question["answer"] for question in sections[0]["questions"]],
                         [ANSWERS[number] for number in range(46, 56)])
        self.assertNotIn("explanatory prose", sections[0]["passage"])

    def test_entire_answer_table_is_required_and_duplicates_or_bad_choices_are_rejected(self):
        defects = {
            "missing_outside_imported_scope": self.answers.replace("26 A ", "", 1),
            "missing_imported_answer": self.answers.replace(" 55 B", "", 1),
            "only_careful_answers": self.answers.replace(
                " ".join(f"{n} {ANSWERS[n]}" for n in range(26, 36)) + "\n", "", 1).replace(
                " ".join(f"{n} {ANSWERS[n]}" for n in range(36, 46)) + "\n", "", 1),
            "duplicate_same_answer": self.answers.replace(
                "Part IV Translation", "46 A\nPart IV Translation", 1),
            "conflicting_duplicate": self.answers.replace(
                "Part IV Translation", "46 B\nPart IV Translation", 1),
            "answer_outside_choices": self.answers.replace("46 A", "46 E", 1),
        }
        for defect, answers in defects.items():
            with self.subTest(defect=defect), self.assertRaises(ReadingImportError):
                parse_careful_reading_text(self.paper, answer_text=answers)

    def test_missing_careful_option_is_rejected(self):
        text = self.paper.replace(" D) Choice D for question 54.", "", 1)
        with self.assertRaises(ReadingImportError):
            parse_careful_reading_text(text, answer_text=self.answers)

    def test_unknown_or_missing_paper_and_answer_headers_are_rejected(self):
        cases = [
            (self.paper.replace("Part III · Reading Comprehension", "Part II · Reading Comprehension", 1),
             self.answers),
            (self.paper.replace("Section C Passages", "Section C Exercises", 1), self.answers),
            (self.paper.replace("Part IV · Translation", "Part V · Translation", 1), self.answers),
            (self.paper.replace("Passage Two", "Passage Three", 1), self.answers),
            (self.paper, self.answers.replace("Part III Reading Comprehension", "Reading Answers", 1)),
            (self.paper, self.answers.replace("Part IV Translation", "Other Answers", 1)),
        ]
        for index, (text, answers) in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ReadingImportError):
                parse_careful_reading_text(text, answer_text=answers)

    def test_careful_only_pack_identifies_scope_and_keeps_verification_false(self):
        pack = build_pack(self.paper, level="CET6", year=2025, session="2025.12",
                          paper_number=3, source_url="https://example.test/original-careful.pdf",
                          answer_text=self.answers, careful_only=True)
        self.assertEqual(pack["schema_version"], 1)
        exam = pack["exams"][0]
        self.assertEqual(exam["level"], "CET6")
        self.assertIn("仅仔细阅读", exam["title"])
        self.assertIn("46—55", exam["title"])
        self.assertIn("careful-reading", exam["id"])
        self.assertIs(exam["source"]["verified"], False)
        self.assertEqual(len(exam["sections"]), 1)
        self.assertEqual(sum(len(section["questions"]) for section in exam["sections"]), 10)

    def test_reformatted_route_requires_explicit_cet6_selection(self):
        metadata = {"year": 2025, "session": "2025.12", "paper_number": 3,
                    "source_url": "https://example.test/original-careful.pdf",
                    "answer_text": self.answers}
        with self.assertRaises(ReadingImportError):
            build_pack(self.paper, level="CET4", careful_only=True, **metadata)
        with self.assertRaises(ReadingImportError):
            build_pack(self.paper, level="CET6", **metadata)


if __name__ == "__main__":
    unittest.main()
