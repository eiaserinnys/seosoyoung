from seosoyoung.slackbot.daily_todo.model import apply_check, visible_ids


def item(id, status='open', parent=None, done_on=None, **extra):
    return {'id': id, 'status': status, 'parent': parent, 'done_on': done_on, **extra}


def test_complete_tree_and_preserve_existing_done_date_and_unknown_fields():
    items = [item('p', custom='keep'), item('a', parent='p'), item('b', 'held', 'p'), item('c', 'done', 'p', '2026-11-01')]
    result = apply_check(items, 'p', True, '2026-11-09')
    assert [(x['status'], x['done_on']) for x in result] == [('done', '2026-11-09'), ('done', '2026-11-09'), ('done', '2026-11-09'), ('done', '2026-11-01')]
    assert result[0]['custom'] == 'keep'
    assert items[0]['status'] == 'open'


def test_last_child_completes_ancestors_and_reopen_propagates():
    items = [item('g'), item('p', parent='g'), item('a', 'done', 'p', '2026-11-08'), item('b', parent='p')]
    done = apply_check(items, 'b', True, '2026-11-09')
    assert [x['status'] for x in done] == ['done'] * 4
    assert done[2]['done_on'] == '2026-11-08'
    opened = apply_check(done, 'a', False, '2026-11-09')
    assert [x['status'] for x in opened] == ['open', 'open', 'open', 'done']
    assert all(x['done_on'] is None for x in opened[:3])
    assert apply_check(done, 'b', True, '2026-11-10') == done


def test_visible_recent_done_and_ancestors_future_date_still_visible():
    items = [item('p', 'done', done_on='2026-10-01'), item('a', parent='p', date='2026-12-01'), item('b', 'held'), item('c', 'done', done_on='2026-11-08'), item('d', 'done', done_on='2026-11-07')]
    assert visible_ids(items, '2026-11-09') == {'p', 'a', 'b', 'c'}


def test_five_operations_match_todo_client_javascript():
    import json
    from pathlib import Path
    import subprocess

    parent = [item('g'), item('p', parent='g'), item('a', parent='p'), item('b', 'held', 'p'), item('c', 'done', 'p', '2026-11-08')]
    last = [item('g'), item('p', parent='g'), item('a', 'done', 'p', '2026-11-08'), item('b', parent='p')]
    done = apply_check(last, 'b', True, '2026-11-09')
    cases = [
        {'items': parent, 'id': 'p', 'checked': True, 'today': '2026-11-09'},
        {'items': parent, 'id': 'a', 'checked': True, 'today': '2026-11-09'},
        {'items': last, 'id': 'b', 'checked': True, 'today': '2026-11-09'},
        {'items': done, 'id': 'a', 'checked': False, 'today': '2026-11-09'},
        {'items': done, 'id': 'b', 'checked': True, 'today': '2026-11-10'},
    ]
    script = Path(__file__).parent / 'fixtures' / 'todo-app-apply-check.cjs'
    result = subprocess.run(['node', str(script)], input=json.dumps(cases, ensure_ascii=False), text=True, capture_output=True, check=True, timeout=10)
    assert json.loads(result.stdout) == [apply_check(c['items'], c['id'], c['checked'], c['today']) for c in cases]
