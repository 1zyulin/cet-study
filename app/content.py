"""Versioned content packs and deterministic grading."""
import re


class ContentError(ValueError):
    pass


def text(value, label, limit=50000, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ContentError(f'{label}须为有效文本（最多 {limit} 字符）')
    return value


def identifier(value, label):
    value = text(value, label, 120, True)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ContentError(f'{label}只允许字母、数字、点、下划线及连字符')
    return value


def validate_pack(pack):
    if not isinstance(pack, dict) or pack.get('schema_version') != 1:
        raise ContentError('题库格式须包含 schema_version: 1')
    exams = pack.get('exams')
    if not isinstance(exams, list) or not 1 <= len(exams) <= 300:
        raise ContentError('每次导入须包含 1—300 套练习')
    ids, output = set(), []
    for raw in exams:
        if not isinstance(raw, dict):
            raise ContentError('试卷须为对象')
        eid = identifier(raw.get('id'), '试卷 ID')
        if eid in ids:
            raise ContentError('题库内试卷 ID 重复')
        ids.add(eid)
        if raw.get('level') not in ('CET4', 'CET6'):
            raise ContentError('level 须为 CET4 或 CET6')
        if raw.get('source_kind') not in ('demo', 'past_paper'):
            raise ContentError('source_kind 须为 demo 或 past_paper')
        year = raw.get('year')
        if type(year) is not int or not 1987 <= year <= 2100:
            raise ContentError('须提供有效试卷年份')
        source = raw.get('source')
        if not isinstance(source, dict):
            raise ContentError('须记录题目来源')
        normalized_source = {
            'title': text(source.get('title'), '来源名称', 500, True),
            'url': text(source.get('url', ''), '来源链接', 2000),
            'rights': text(source.get('rights'), '内容权利说明', 1000, True),
            'verified': source.get('verified') is True,
        }
        sections = raw.get('sections')
        if not isinstance(sections, list) or not 1 <= len(sections) <= 30:
            raise ContentError('每套练习须包含 1—30 个非空部分')
        section_ids, question_ids, result_sections = set(), set(), []
        for s in sections:
            if not isinstance(s, dict):
                raise ContentError('部分须为对象')
            sid = identifier(s.get('id'), '部分 ID')
            if sid in section_ids:
                raise ContentError('部分 ID 重复')
            section_ids.add(sid)
            if s.get('kind') not in ('reading', 'listening', 'writing', 'translation'):
                raise ContentError('不支持的题型部分')
            ns = {'id': sid, 'title': text(s.get('title'), '部分标题', 500, True), 'kind': s['kind'], 'passage': text(s.get('passage', ''), '原文'), 'transcript': text(s.get('transcript', ''), '听力原文')}
            audio = s.get('audio_url', '')
            if audio:
                if not isinstance(audio, str) or not re.fullmatch(r'/media/[a-f0-9]{32}\.(mp3|wav|m4a|ogg)', audio):
                    raise ContentError('音频须使用上传接口返回的本地 /media/ 地址')
                ns['audio_url'] = audio
            segments = s.get('segments', [])
            if not isinstance(segments, list) or len(segments) > 2000:
                raise ContentError('听力时间轴格式错误')
            ns['segments'] = []
            last_start = -1
            for seg in segments:
                if not isinstance(seg, dict) or type(seg.get('start')) not in (int, float) or type(seg.get('end')) not in (int, float):
                    raise ContentError('时间轴须有数值 start/end')
                if not 0 <= seg['start'] < seg['end'] <= 86400 or seg['start'] < last_start:
                    raise ContentError('时间轴必须按开始时间排序，结束时间须大于开始时间')
                last_start = seg['start']
                ns['segments'].append({'start': seg['start'], 'end': seg['end'], 'text': text(seg.get('text'), '字幕文本', 5000, True)})
            qs = s.get('questions')
            if not isinstance(qs, list) or not 1 <= len(qs) <= 100:
                raise ContentError('每部分须有 1—100 道题；不接受空题目数组')
            ns['questions'] = []
            for q in qs:
                if not isinstance(q, dict):
                    raise ContentError('题目须为对象')
                qid = identifier(q.get('id'), '题目 ID')
                if qid in question_ids:
                    raise ContentError('同一试卷内题目 ID 重复')
                question_ids.add(qid)
                qt = q.get('type')
                if qt not in ('choice', 'writing', 'translation'):
                    raise ContentError('type 须为 choice / writing / translation')
                nq = {'id': qid, 'type': qt, 'prompt': text(q.get('prompt'), '题干', 30000, True), 'explanation': text(q.get('explanation', ''), '解析'), 'reference': text(q.get('reference', ''), '参考答案')}
                if qt == 'choice':
                    opts = q.get('options')
                    if not isinstance(opts, list) or not 2 <= len(opts) <= 30:
                        raise ContentError('选择题须有 2—30 个选项')
                    seen, nq['options'] = set(), []
                    for o in opts:
                        if not isinstance(o, dict):
                            raise ContentError('选项须为对象')
                        oid = identifier(o.get('id'), '选项 ID')
                        if oid in seen:
                            raise ContentError('选项 ID 重复')
                        seen.add(oid)
                        nq['options'].append({'id': oid, 'text': text(o.get('text'), '选项文本', 10000, True)})
                    if not isinstance(q.get('answer'), str) or q.get('answer') not in seen:
                        raise ContentError('正确答案须对应实际选项 ID')
                    nq['answer'] = q['answer']
                else:
                    minimum = (120 if raw['level'] == 'CET4' else 150) if qt == 'writing' else 0
                    maximum = (180 if raw['level'] == 'CET4' else 200) if qt == 'writing' else 5000
                    for k, default in [('min_words', minimum), ('max_words', maximum)]:
                        v = q.get(k, default)
                        if type(v) is not int or not 0 <= v <= 5000:
                            raise ContentError('字数范围须为有效整数')
                        nq[k] = v
                    if nq['max_words'] < nq['min_words']:
                        raise ContentError('最高字数不得低于最低字数')
                ns['questions'].append(nq)
            result_sections.append(ns)
        output.append({'id': eid, 'title': text(raw.get('title'), '试卷标题', 500, True), 'level': raw['level'], 'year': year, 'session': text(raw.get('session', ''), '考次', 100), 'source_kind': raw['source_kind'], 'source': normalized_source, 'sections': result_sections})
    return output


def questions(exam):
    return [(s, q) for s in exam['sections'] for q in s['questions']]


def public_exam(exam):
    import copy
    result = copy.deepcopy(exam)
    for _, q in questions(result):
        q.pop('answer', None)
        q.pop('explanation', None)
    return result


def grade(exam, answers):
    if not isinstance(answers, dict):
        raise ContentError('answers 须为题目 ID 到答案文本的映射')
    known = {q['id'] for _, q in questions(exam)}
    if set(answers) - known:
        raise ContentError('作答包含未知题目')
    results, correct, total = [], 0, 0
    for _, q in questions(exam):
        answer = text(answers.get(q['id'], ''), '作答', 30000)
        r = {'question_id': q['id'], 'type': q['type'], 'answer': answer}
        if q['type'] == 'choice':
            if answer and answer not in {o['id'] for o in q['options']}:
                raise ContentError('选择题答案不在选项范围内')
            ok = answer == q['answer']
            correct += int(ok)
            total += 1
            r.update(status='graded', correct_answer=q['answer'], is_correct=ok, explanation=q['explanation'])
        else:
            r['status'] = 'pending_ai'
        results.append(r)
    return {'results': results, 'correct': correct, 'total_objective': total}


def word_count(answer):
    return len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", answer))
