from seosoyoung.slackbot.daily_todo.numbering import assign_todo_numbers


def test_numbers_exclude_groups_held_done_and_context_and_never_reuse():
    items = [
        {'id': 'p', 'status': 'open'}, {'id': 'a', 'status': 'open', 'parent': 'p'},
        {'id': 'held', 'status': 'held'}, {'id': 'done', 'status': 'done'},
        {'id': 'context', 'status': 'open', 'context_only': True}, {'id': 'new', 'status': 'open'},
    ]
    assert assign_todo_numbers(items, {1: 'gone', 2: 'a', 3: 'done'}) == {2: 'a', 4: 'new'}
    assert assign_todo_numbers(items, {}) == {1: 'a', 2: 'new'}
    assert assign_todo_numbers(items, {2: 'a'}, 10) == {2: 'a', 10: 'new'}
