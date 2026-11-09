from seosoyoung.slackbot.daily_todo.model import visible_ids


def test_visibility_keeps_order_and_does_not_mutate_item_fields():
    items = [{'id': 'parent', 'status': 'done', 'done_on': '2026-01-01', 'area': '개인사', 'order': 4, 'custom': '보존'},
             {'id': 'child', 'parent': 'parent', 'status': 'open', 'area': '개인사', 'order': 1}]
    assert visible_ids(items, '2026-11-09') == {'parent', 'child'}
    assert items[0]['custom'] == '보존'
    assert [item['id'] for item in items] == ['parent', 'child']
