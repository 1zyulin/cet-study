"""Original-text tests for complete CET6 reading conversion."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.import_cet6_reading import (
    ReadingImportError, apply_document_corrections, build_cet6_pack, checked_answer_text, numbered_blocks,
    parse_cet6_answers, parse_cet6_reading, plain_markdown,
)
from tests.test_reading_import import ANSWERS, original_reading_paper


def numbered_answers():
    values = dict(ANSWERS)
    values[36] = 'R'
    return values, '\n'.join(f'{number}. {letter}' for number, letter in values.items())


def full_cet6_paper():
    paper = original_reading_paper()
    paper = paper.replace('Select one word for each blank from the word bank.',
                          'Select one word for each blank from the word bank. You may not use any of the words in the bank more than once.')
    for letter in 'KLMNOPQR':
        paper = paper.replace('36. Original', f'{letter}) Original paragraph {letter} describes a different club activity.\n36. Original')
    return paper


def reformatted_paper(statements_first=True):
    paper = full_cet6_paper()
    first = paper.index('A) Original paragraph A')
    first_question = paper.index('36. Original')
    next_section = paper.index('Section C')
    article = paper[first:first_question]
    statements = paper[first_question:next_section]
    if statements_first:
        matching = ('Section B Long Reading Matching\nA library garden for everyone\n'
                    + statements + '长篇阅读匹配题：根据文章作答。\n原文段落 A – R\n' + article)
    else:
        matching = ('Section B Long Reading Matching\nA library garden for everyone\n'
                    '原文段落 A – R\n' + article + statements)
    start = paper.index('Section B')
    paper = paper[:start] + matching + paper[next_section:]
    instructions = paper.index('Directions: In this section, there is a passage')
    passage = paper.index('A community garden')
    paper = paper[:instructions] + paper[passage:]
    paper = paper.replace('Section A\n', 'Section A Banked Cloze\n')
    paper = paper.replace('A) gardenworda', 'Word Bank: A) gardenworda')
    for first, last in ((46, 50), (51, 55)):
        paper = paper.replace(f'Questions {first} to {last} are based on the following passage.\n', '')
    paper = paper.replace('Section C\n', 'Section C Passages\n')
    return paper


class Cet6ReadingImportTests(unittest.TestCase):
    def test_complete_standard_with_eighteen_paragraphs(self):
        values, _ = numbered_answers()
        sections = parse_cet6_reading(full_cet6_paper(), values)
        self.assertEqual([len(s['questions']) for s in sections], [10, 10, 10])
        self.assertEqual(sections[1]['questions'][0]['options'][-1]['id'], 'R')
        self.assertEqual(sections[1]['questions'][0]['answer'], 'R')

    def test_reformatted_statement_before_and_after_article(self):
        values, _ = numbered_answers()
        for before in (True, False):
            sections = parse_cet6_reading(reformatted_paper(before), values)
            self.assertEqual(len(sections[1]['questions']), 10)
            self.assertIn('Original paragraph R', sections[1]['passage'])
            self.assertNotIn('原文段落', sections[1]['passage'])

    def test_literal_percentages_are_not_blank_markers(self):
        values, _ = numbered_answers()
        paper = reformatted_paper().replace('A community garden opens', 'An attendance increase of 32% to 35% means a community garden opens')
        sections = parse_cet6_reading(paper, values)
        self.assertIn('32% to 35%', sections[0]['passage'])

    def test_same_line_word_question_boundary(self):
        block = '36. An original first statement. 37.A different original statement.'
        self.assertEqual([n for n, _ in numbered_blocks(block, 36, 37, 'fixture')], [36, 37])

    def test_markdown_blank_tags_distinguish_literal_numbers(self):
        values, _ = numbered_answers()
        paper = reformatted_paper()
        for n in range(26, 36):
            paper = paper.replace(f'___{n}___', f'<u>&emsp;{n}&emsp;</u>')
        paper = paper.replace('A community garden opens', 'For 30 seconds, a community garden opens')
        sections = parse_cet6_reading(plain_markdown(paper), values)
        self.assertIn('30 seconds', sections[0]['passage'])

    def test_correction_requires_unique_source_and_evidence(self):
        corrections = {'corrections': {'original.docx': [{'old': 'ID) label', 'new': 'I) label',
                                                       'evidence_url': 'https://example.test/source'}]}}
        self.assertEqual(apply_document_corrections('ID) label', 'original.docx', corrections), 'I) label')
        with self.assertRaises(ReadingImportError):
            apply_document_corrections('ID) label ID) label', 'original.docx', corrections)

    def test_short_marker_correction_checks_fingerprint_and_question_scope(self):
        paper = full_cet6_paper().replace('C) Choice C for question 54.', 'O) Choice C for question 54.')
        paper = paper.replace('41. Original statement', '41.1t is an original statement')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original.pdf'
            path.write_bytes(b'original fixture file bytes')
            fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
            entries = [{'kind': 'question-option-label', 'question': 54, 'old': 'O)', 'new': 'C)'},
                       {'kind': 'question-leading-token', 'question': 41, 'old': '1t', 'new': 'It'}]
            entries = [dict(e, source_sha256=fingerprint, evidence_url='https://example.test/reference') for e in entries]
            corrections = {'corrections': {'original.pdf': entries}}
            fixed = apply_document_corrections(paper, path.name, corrections, path)
            self.assertIn('O) gardenwordo', fixed)
            self.assertIn('C) Choice C for question 54.', fixed)
            self.assertIn('41.It is an original statement', fixed)
            path.write_bytes(b'a different edition of the fixture')
            with self.assertRaises(ReadingImportError):
                apply_document_corrections(paper, path.name, corrections, path)

    def test_reviewed_answers_require_exact_paper_and_answer_bytes(self):
        _, table = numbered_answers()
        values = {str(n): a for n, a in parse_cet6_answers(table).items()}
        with tempfile.TemporaryDirectory() as directory:
            paper, answer = Path(directory) / 'fixture.pdf', Path(directory) / 'fixture_ans.pdf'
            paper.write_bytes(b'original fixture paper')
            answer.write_bytes(b'original fixture answer')
            entry = {'paper': paper.name, 'source': answer.name, 'source_url': 'https://example.test/answers',
                     'paper_sha256': hashlib.sha256(paper.read_bytes()).hexdigest(),
                     'source_sha256': hashlib.sha256(answer.read_bytes()).hexdigest(), 'answers': values}
            self.assertEqual(parse_cet6_answers(checked_answer_text(entry, paper, answer)), parse_cet6_answers(table))
            answer.write_bytes(b'a different answer booklet')
            with self.assertRaises(ReadingImportError):
                checked_answer_text(entry, paper, answer)
            entry.update(source_kind='web_answer_table', evidence={'26-55': 'explicit table'},
                         cross_check_url='https://example.test/independent-answer-table')
            self.assertEqual(parse_cet6_answers(checked_answer_text(entry, paper, answer)), parse_cet6_answers(table))
            paper.write_bytes(b'a different fixture paper')
            with self.assertRaises(ReadingImportError):
                checked_answer_text(entry, paper, answer)

    def test_missing_option_fails_closed(self):
        values, _ = numbered_answers()
        paper = full_cet6_paper().replace('D) Choice D for question 55.', '')
        with self.assertRaises(ReadingImportError):
            parse_cet6_reading(paper, values)

    def test_answer_pairs_and_duplicate_agreement(self):
        values, table = numbered_answers()
        self.assertEqual(parse_cet6_answers(table + '\n26. A)'), values)
        with self.assertRaises(ReadingImportError):
            parse_cet6_answers(table + '\n26. B)')

    def test_internal_keys_reads_complete_paired_rows_including_r(self):
        values, _ = numbered_answers()
        rows = []
        for start in (26, 36, 46):
            rows.append(' '.join(str(n) for n in range(start, start + 10)))
            rows.append(' '.join(values[n] for n in range(start, start + 10)))
        text = 'KEYS\nPart III Reading Comprehension\n' + '\n'.join(rows)
        self.assertEqual(parse_cet6_answers(text), values)
        with self.assertRaises(ReadingImportError):
            parse_cet6_answers(text.replace('26 27', '27 26'))

    def test_missing_answer_is_rejected(self):
        _, table = numbered_answers()
        with self.assertRaises(ReadingImportError):
            parse_cet6_answers(table.replace('55. B', ''))

    def test_publisher_zero_glyph_is_only_normalized_in_letter_banks(self):
        _, table = numbered_answers()
        self.assertEqual(parse_cet6_answers(table.replace('31. F', '31. 0'))[31], 'O')
        with self.assertRaises(ReadingImportError):
            parse_cet6_answers(table.replace('46. A', '46. 0'))

    def test_pack_preserves_unverified_metadata_without_title_badge(self):
        _, table = numbered_answers()
        pack = build_cet6_pack(full_cet6_paper(), table, year=2025, month='12', paper_number=3,
                              source_url='https://example.test/paper', answer_url='https://example.test/answer')
        exam = pack['exams'][0]
        self.assertFalse(exam['source']['verified'])
        self.assertNotIn('待校对', exam['title'])
        self.assertEqual(sum(len(s['questions']) for s in exam['sections']), 30)


if __name__ == '__main__':
    unittest.main()
