const {layoutTree, pathToRoot} = require('./tree-layout.js');
// 构造一棵 fork 树：branch0 [cp0(step0),cp1(step1)]; branch1 从 cp0 fork [cp2(step0),cp3(step1)]
const tree = {
  "0": {parent_cp:null, steps:[
    {id:0,branch:0,step:0,parent:null,thought:"a"},
    {id:1,branch:0,step:1,parent:0,final:"f0"}]},
  "1": {parent_cp:0, steps:[
    {id:2,branch:1,step:0,parent:0,thought:"b"},
    {id:3,branch:1,step:1,parent:2,final:"f1"}]},
};
const L = layoutTree(tree);
const byId = L.byId;
let ok = true, msg = [];
// C4: cp0(step0) 和 cp2(step0) 不能同 y（用 depth：cp2 parent=cp0 → depth1）
if (byId[0].y === byId[2].y) { ok=false; msg.push("FAIL: cp0/cp2 同 y(没按 depth)"); }
else msg.push(`OK cp0.y=${byId[0].y} cp2.y=${byId[2].y} (depth 分开)`);
// cp2 depth 应=1（parent cp0）
if (byId[2].depth !== 1) { ok=false; msg.push("FAIL: cp2 depth!=1"); } else msg.push("OK cp2.depth=1");
// 不同分支不同 x 列
if (byId[0].x === byId[2].x) { ok=false; msg.push("FAIL: branch0/1 同列"); } else msg.push(`OK 分列 x0=${byId[0].x} x2=${byId[2].x}`);
// 任意两节点不重叠
const pts = L.nodes.map(n=>n.x+","+n.y); 
if (new Set(pts).size !== pts.length){ ok=false; msg.push("FAIL: 有节点重叠"); } else msg.push(`OK ${L.nodes.length} 节点无重叠`);
// edges: 4 个节点中 3 条边(cp0是根无边)
if (L.edges.length !== 3){ ok=false; msg.push("FAIL: edges!="+L.edges.length); } else msg.push("OK 3 条边");
// pathToRoot(3) = [cp0,cp2,cp3]
const p = pathToRoot(byId,3).map(n=>n.id).join(",");
if (p !== "0,2,3"){ ok=false; msg.push("FAIL path="+p); } else msg.push("OK path(3)=0,2,3");
console.log(msg.join("\n"));
console.log(ok ? "\n✅ 布局测试 PASS" : "\n❌ FAIL");
process.exit(ok?0:1);
