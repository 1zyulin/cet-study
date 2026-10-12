"""Original fixtures exercise data extraction without real exam material."""
import unittest

from app.content import ContentError, validate_pack
from tools.import_sources import cet4_subjective, cet6_subjective, read_literal


class SourceImportTests(unittest.TestCase):
    def test_js_literals_do_not_execute_expressions(self):
        for expression in ["[run()]", "[{x: function(){}}]", "[{x: globalThis.token}]",
                           "[{x: `template`}]", "[{x: 1, x: 2}]", "[1] + run()"]:
            with self.subTest(expression=expression), self.assertRaises(ContentError):
                read_literal('const DATA = ' + expression + ';', 'DATA')

    def test_strings_comments_and_trailing_comma(self):
        value = read_literal("const DATA = [ /* ignored */ {key: 'It\\'s \\u0041', nested: [true, null, -2,],}, ];", 'DATA')
        self.assertEqual(value, [{'key': "It's A", 'nested': [True, None, -2]}])

    def test_cet6_pairing_preserves_prompt_and_marks_unverified(self):
        writing = "const WRITING_EXAMS=[{year:2025,period:'6月',set:'第一套',prompt:'Original prompt 150-200 words'}];"
        translation = "const TRANSLATION_DATA=[{year:2025,period:'6月',set:'第一套',original:'自创原文',reference:'Original reference'}];"
        exams = validate_pack({'schema_version': 1, 'exams': cet6_subjective(writing, translation, [2025])})
        self.assertFalse(exams[0]['source']['verified'])
        self.assertEqual(len(exams[0]['sections']), 2)
        self.assertIn('自创原文', exams[0]['sections'][1]['questions'][0]['prompt'])
        self.assertIn('非已核验官方答案', exams[0]['sections'][1]['questions'][0]['reference'])
        with self.assertRaises(ContentError):
            cet6_subjective(writing, 'const TRANSLATION_DATA=[];', [2025])

    def test_markdown_sections_exclude_model_essay_and_other_years(self):
        sets = '\n'.join(f'''#### 第{number}套
**写作**（练习）
> Original writing {number}, 120 to 180 words.
**★ 满分范文**
> Do not copy this example essay into the prompt.
**翻译**（练习）
> 自创中文 {number}
**★ 满分参考译文**（社区文本）
> Original translation {number}.
''' for number in [1, 2, 3])
        markdown = '### 2022.12月\n' + sets + '\n### 2023.3月（加考）\n' + sets
        exams = validate_pack({'schema_version': 1, 'exams': cet4_subjective(markdown, [2023])})
        self.assertEqual(len(exams), 3)
        self.assertTrue(all(e['year'] == 2023 for e in exams))
        self.assertNotIn('example essay', exams[0]['sections'][0]['questions'][0]['prompt'])
        self.assertFalse(exams[0]['source']['verified'])
        with self.assertRaises(ContentError):
            cet4_subjective('### 2023.6月\n#### 第1套\n**写作**\n> Incomplete.', [2023])


if __name__ == '__main__':
    unittest.main()
