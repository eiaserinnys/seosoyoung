import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from seosoyoung.slackbot.daily_todo.delivery_store import DeliveryStore

store = DeliveryStore(sys.argv[1])
store.update(lambda state: state['events'].append({'id': sys.argv[2]}))
