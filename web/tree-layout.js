/* 世界树布局：把 Recorder.tree() 算成 {nodes, edges}。
   关键(Codex C4)：y 用 parent 链 depth（不是 cp.step——step 每次 resume/fork 从 0 重置会重叠）；
   x 用 branch lane（每分支一列），sibling 分支自然分列、不串线。
   纯函数，可单测。被 worldtree.js / convtree 复用。 */
(function (root) {
  function layoutTree(tree, opt) {
    opt = opt || {};
    const ROW = opt.row || 74, LANE = opt.lane || 150, X0 = opt.x0 || 70, Y0 = opt.y0 || 60;

    // 1) 扁平化所有 checkpoint
    const nodes = {};
    for (const bid in tree) {
      for (const cp of (tree[bid].steps || [])) nodes[cp.id] = Object.assign({}, cp, { branch: +bid });
    }
    // 2) depth = parent 链长度（memo，防环）
    function depthOf(id, seen) {
      const n = nodes[id];
      if (!n) return 0;
      if (n._d != null) return n._d;
      seen = seen || new Set();
      if (n.parent == null || !(n.parent in nodes) || seen.has(id)) return (n._d = 0);
      seen.add(id);
      return (n._d = depthOf(n.parent, seen) + 1);
    }
    // 3) branch → lane 列
    const branches = Object.keys(tree).map(Number).sort((a, b) => a - b);
    const lane = {}; branches.forEach((b, i) => (lane[b] = i));

    const out = [];
    let maxD = 0;
    for (const id in nodes) {
      const n = nodes[id], d = depthOf(+id);
      maxD = Math.max(maxD, d);
      out.push({
        id: +id, branch: n.branch, parent: n.parent, depth: d,
        x: X0 + lane[n.branch] * LANE, y: Y0 + d * ROW,
        kind: n.final ? 'final' : 'step',
        thought: n.thought, action: n.action, obs: n.obs, final: n.final,
        user: n.user, rule: n.rule, state: n.state,
      });
    }
    out.sort((a, b) => a.id - b.id);
    const byId = {}; out.forEach((n) => (byId[n.id] = n));
    const edges = out.filter((n) => n.parent != null && byId[n.parent])
      .map((n) => ({ from: byId[n.parent], to: byId[n.id] }));

    return {
      nodes: out, edges, byId, branches, lane,
      width: X0 + Math.max(1, branches.length) * LANE,
      height: Y0 + (maxD + 1) * ROW,
    };
  }

  // 从某节点回溯到根的路径（用于玻璃盒"当前路径"高亮 + 详情）
  function pathToRoot(byId, id) {
    const path = [];
    let cur = byId[id];
    while (cur) { path.unshift(cur); cur = cur.parent != null ? byId[cur.parent] : null; }
    return path; // [root..id]
  }

  const api = { layoutTree, pathToRoot };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.TreeLayout = api;
})(typeof window !== 'undefined' ? window : globalThis);
