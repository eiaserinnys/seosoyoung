from copy import deepcopy

from seosoyoung.slackbot.daily_todo.rendering import render_daily_todo_messages, render_snapshot


def test_tree_memos_buttons_split_and_fixed_parts():
    items = [{'id': 'parent', 'title': '묶음', 'area': '회사일', 'parent': None, 'status': 'open', 'order': 0}]
    items += [{'id': f'i{i}', 'title': f'항목 {i}', 'area': '회사일', 'parent': 'parent', 'status': 'open', 'order': i} for i in range(70)]
    items += [{'id': 'done', 'title': '이미 완료', 'area': '개인사', 'parent': None, 'status': 'done', 'done_on': '2026-11-08', 'order': 0},
              {'id': 'held', 'title': '보류 업무', 'area': '개인사', 'parent': None, 'status': 'held', 'order': 1}]
    mapping = {i + 1: f'i{i}' for i in range(70)}
    parts = render_daily_todo_messages(items, areas=['회사일', '개인사'], memos={'i0': '메모'}, date='2026-11-09', delivery_id='d', number_to_todo_id=mapping)
    assert len(parts) > 1
    assert sorted(n for part in parts for n in part.numbers) == list(range(1, 71))
    assert all(len(p.blocks) <= 50 for p in parts)
    assert all(len(b['text']['text']) <= 3000 for p in parts for b in p.blocks if b['type'] == 'section')
    assert all(len(b['elements']) <= 10 for p in parts for b in p.blocks if b['type'] == 'actions')
    assert any('메모' in str(p.blocks) for p in parts)
    assert any('~• 이미 완료~' in str(p.blocks) for p in parts)
    assert any('보류' in str(p.blocks) for p in parts)
    assert any('할 일 앱' in p.text for p in parts)
    for part in parts:
        for block in part.blocks:
            if block['type'] == 'actions':
                assert all(len(button['accessibility_label']) <= 75 for button in block['elements'])
    original = deepcopy(parts[0].snapshot)
    changed = deepcopy(items)
    changed[1]['status'] = 'done'
    changed[1]['title'] = '이름을 아주 길게 바꾸고 새 항목을 추가해도 번호 위치는 그대로'
    changed.append({'id': 'new', 'title': '새 작업', 'status': 'open'})
    result = render_snapshot(original, {item['id']: item for item in changed}, 'd', 1, include_actions=True)
    assert result.numbers == parts[0].numbers
    assert result.snapshot == original
    assert '~' in str(result.blocks) and '↺1' in str(result.blocks)


def test_long_text_fallback_limits_and_app_link():
    items = [{'id': 'a', 'title': '가' * 10000, 'area': '회사일', 'parent': None, 'status': 'open', 'date': '2026-12-01', 'wait': '답변 대기'}]
    parts = render_daily_todo_messages(items, areas=['회사일'], memos={'a': '메' * 10000}, date='2026-11-09', delivery_id='d', number_to_todo_id={1: 'a'}, todo_url='https://example.test/app')
    assert all(len(block['text']['text']) <= 3000 for part in parts for block in part.blocks if block['type'] == 'section')
    assert all(len(part.text) <= 4000 for part in parts)
    assert any('<https://example.test/app|할 일 앱>' in str(part.blocks) for part in parts)
    assert any('2026-12-01' in str(part.blocks) and '답변 대기' in str(part.blocks) for part in parts)


def test_very_long_memo_keeps_number_row_and_button_in_same_part():
    items = [{'id': 'a', 'title': '할 일', 'area': '회사일', 'parent': None, 'status': 'open'}]
    memo = '가' * 200000
    parts = render_daily_todo_messages(items, areas=['회사일'], memos={'a': memo}, date='2026-11-09',
                                       delivery_id='d', number_to_todo_id={1: 'a'})
    row_part = next(part for part in parts if any(entry.get('kind') == 'row' and entry.get('id') == 'a' for entry in part.snapshot))
    assert row_part.numbers == [1]
    assert any(block.get('type') == 'actions' for block in row_part.blocks)
    text = '\n'.join(block['text']['text'] for block in row_part.blocks if block['type'] == 'section')
    assert '(이어지는 메모는 할 일 앱에서)' in text
    assert 0 < text.count('가') < len(memo)
    assert len(row_part.blocks) <= 50
    assert sum(len(block['text']['text']) for block in row_part.blocks if block['type'] == 'section') < 39000


def test_done_items_omit_memo_and_details_read_as_a_sentence():
    items = [{'id': 'open', 'title': '남은 일', 'area': '회사일', 'parent': None, 'status': 'open', 'order': 0,
              'date': '2026-11-19', 'wait': '답변 대기'},
             {'id': 'done', 'title': '끝낸 일', 'area': '회사일', 'parent': None, 'status': 'done',
              'done_on': '2026-11-09', 'order': 1}]
    parts = render_daily_todo_messages(items, areas=['회사일'], memos={'open': '남은 메모', 'done': '끝난 메모'},
                                       date='2026-11-09', delivery_id='d', number_to_todo_id={1: 'open'})
    blocks = str([part.blocks for part in parts])
    assert '남은 메모' in blocks
    assert '끝난 메모' not in blocks
    assert '(2026-11-19, 답변 대기)' in blocks
    assert '·' not in blocks


def test_long_notification_text_keeps_the_opening_lines():
    items = [{'id': 'a', 'title': '가' * 5000, 'area': '회사일', 'parent': None, 'status': 'open', 'order': 0}]
    parts = render_daily_todo_messages(items, areas=['회사일'], memos={}, date='2026-11-09',
                                       delivery_id='d', number_to_todo_id={1: 'a'})
    assert parts[0].text.startswith('*일일 TODO*\n*회사일*\n')
    assert len(parts[0].text) <= 4000
