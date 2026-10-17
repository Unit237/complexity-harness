/* Trusted metric visitor for the pinned Babel AST. Never evaluate input code. */
function complexityMetrics(source, language, lines) {
  const typescript = language === "typescript" || language === "tsx";
  const plugins = typescript ? ["typescript"] : [];
  if (language !== "typescript") plugins.push("jsx");
  if (!typescript && /^\s*(?:\/\/[^\n]*@flow|\/\*(?:[^*]|\*(?!\/))*@flow)/.test(source)) plugins.push("flow");
  plugins.push("decorators-legacy", "importAttributes", "explicitResourceManagement");
  const root = exports.parse(source, {
    sourceType: "unambiguous", plugins, attachComment: false,
    allowReturnOutsideFunction: true, errorRecovery: false
  });
  const functionTypes = new Set(["FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression", "ObjectMethod", "ClassMethod", "ClassPrivateMethod"]);
  const decisionTypes = new Set(["IfStatement", "ForStatement", "ForInStatement", "ForOfStatement", "WhileStatement", "DoWhileStatement", "CatchClause", "ConditionalExpression"]);
  const rows = [], outside = {symbol:"<module>", line:1, end_line:Math.max(1,lines), branches:[]};
  const stack = [[root, outside, null]];
  while (stack.length) {
    let [node, owner, parent] = stack.pop();
    const enclosingOwner = owner;
    if (functionTypes.has(node.type) && node.body) {
      const name = node.id || node.key || (parent && parent.type === "VariableDeclarator" && parent.id);
      owner = {symbol:String(name && (name.name || name.value) || "<"+node.type+">"), line:node.loc.start.line, end_line:node.loc.end.line, branches:[]};
      rows.push(owner);
    }
    let kind = null;
    if (decisionTypes.has(node.type) || node.type === "SwitchCase" && node.test) kind = node.type;
    if (node.type === "LogicalExpression" && ["&&","||","??"].includes(node.operator) || node.type === "AssignmentExpression" && ["&&=","||=","??="].includes(node.operator)) kind = "short-circuit";
    if (["OptionalMemberExpression","OptionalCallExpression"].includes(node.type) && node.optional) kind = "optional_chain";
    if (node.type === "AssignmentPattern") kind = "default-evaluation";
    if (kind) owner.branches.push({kind, line:node.loc.start.line, contribution:1});
    const children = [];
    for (const key of Object.keys(node)) {
      if (["loc","extra","comments","tokens","leadingComments","trailingComments","innerComments"].includes(key)) continue;
      const value = node[key];
      const childOwner = functionTypes.has(node.type) && (key === "decorators" || key === "key" && node.computed) ? enclosingOwner : owner;
      if (Array.isArray(value)) { for (const child of value) if (child && typeof child.type === "string") children.push([child,childOwner,node]); }
      else if (value && typeof value.type === "string") children.push([value,childOwner,node]);
    }
    for (let i=children.length-1;i>=0;i--) stack.push(children[i]);
  }
  if (outside.branches.length || !rows.length && root.program.body.length) rows.push(outside);
  return rows;
}
