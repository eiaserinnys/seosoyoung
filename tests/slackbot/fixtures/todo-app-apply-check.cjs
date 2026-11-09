// Extracted from kaleidoscope todo-client v1: copyItem, itemOf, descendantsOf, allDone, applyCheck.
// Source: kaleidoscope-appstore apps/todo/assets/todo-client.javascript at def32d9b8e6b9b95214bfd7426fccd10ac116628.
// The bot's idempotency guard is applied by the caller before invoking applyCheck.
  function copyItem(item) {
    return Object.assign({}, item);
  }

  function itemOf(items, id) {
    for (var index = 0; index < items.length; index += 1) if (items[index].id === id) return items[index];
    return null;
  }

  function descendantsOf(items, id) {
    var result = [];
    var seen = {};
    seen[id] = true;
    var queue = [id];
    while (queue.length) {
      var current = queue.shift();
      items.forEach(function (item) {
        if (item.parent !== current || seen[item.id]) return;
        seen[item.id] = true;
        result.push(item);
        queue.push(item.id);
      });
    }
    return result;
  }

  function allDone(list) {
    return list.length > 0 && list.every(function (item) { return item.status === "done"; });
  }

  function applyCheck(items, op) {
    var target = itemOf(items, op.id);
    if (!target) return null;
    var next = items.map(copyItem);
    var changed = itemOf(next, op.id);
    if (op.checked) {
      changed.status = "done";
      changed.done_on = op.today;
      descendantsOf(next, op.id).forEach(function (item) {
        if (item.status === "open" || item.status === "held") {
          item.status = "done";
          item.done_on = op.today;
        }
      });
      // 자식이 모두 끝난 조상도 같은 날 끝낸다. 끝나지 않은 자식이 나오면 거기서 멈춘다.
      var seen = {};
      seen[op.id] = true;
      var parentId = typeof changed.parent === "string" ? changed.parent : null;
      while (parentId && !seen[parentId]) {
        seen[parentId] = true;
        var parent = itemOf(next, parentId);
        if (!parent) break;
        var siblings = next.filter(function (item) { return item.parent === parent.id; });
        if (!allDone(siblings)) break;
        parent.status = "done";
        parent.done_on = op.today;
        parentId = typeof parent.parent === "string" ? parent.parent : null;
      }
    } else {
      changed.status = "open";
      changed.done_on = null;
      var seenUp = {};
      seenUp[op.id] = true;
      var upId = typeof changed.parent === "string" ? changed.parent : null;
      while (upId && !seenUp[upId]) {
        seenUp[upId] = true;
        var ancestor = itemOf(next, upId);
        if (!ancestor || ancestor.status !== "done") break;
        ancestor.status = "open";
        ancestor.done_on = null;
        upId = typeof ancestor.parent === "string" ? ancestor.parent : null;
      }
    }
    return next;
  }

const fs = require('fs');
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(cases.map(({items, id, checked, today}) => {
  const current = itemOf(items, id);
  if ((current.status === 'done') === checked) return items;
  return applyCheck(items, {id, checked, today});
})));
