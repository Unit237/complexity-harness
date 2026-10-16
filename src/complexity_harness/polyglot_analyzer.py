"""Bundled CST adapters. Measurements never execute repository code."""
from collections import Counter
import hashlib
from importlib.metadata import version, PackageNotFoundError

from .burden import CONTROL_LANGUAGES, STRUCTURAL_LANGUAGES
from .models import BranchEvidence, FileMetric, FunctionMetric
from .python_analyzer import analyze_python_bytes

# Grammar-specific node names: closures own their branches exactly once.
FUNCTIONS = {
    'javascript': {'function_declaration','function_expression','generator_function_declaration','generator_function','arrow_function','method_definition'},
    'typescript': {'function_declaration','function_expression','generator_function_declaration','generator_function','arrow_function','method_definition'},
    'tsx': {'function_declaration','function_expression','generator_function_declaration','generator_function','arrow_function','method_definition'},
    'c': {'function_definition'}, 'cpp': {'function_definition','lambda_expression'},
    'csharp': {'method_declaration','constructor_declaration','local_function_statement','lambda_expression','anonymous_method_expression','accessor_declaration'},
    'java': {'method_declaration','constructor_declaration','lambda_expression'},
    'go': {'function_declaration','method_declaration','func_literal'},
    'rust': {'function_item','closure_expression'},
    'ruby': {'method','singleton_method','lambda','block','do_block'},
    'php': {'function_definition','method_declaration','anonymous_function','arrow_function'},
    'kotlin': {'function_declaration','anonymous_function','lambda_literal','secondary_constructor'},
    'swift': {'function_declaration','lambda_literal','init_declaration'},
    'dart': {'function_body'}, 'bash': {'function_definition'},
    'lua': {'function_declaration','function_definition'},
}
BRANCHES = {
    'if_statement','if_expression','if','unless','unless_modifier','if_modifier',
    'elsif','elif_clause','elseif_statement','else_if_clause',
    'for_statement','for_in_statement','for_expression','for','for_generic_clause','for_numeric_clause',
    'while_statement','while_expression','while','while_modifier','until','until_modifier',
    'do_statement','do_while_statement','repeat_statement',
    'catch_clause','catch_block','catch','rescue','rescue_modifier',
    'case_statement','switch_case','case_switch_label','switch_label','switch_section','switch_statement_case','expression_case','type_case','switch_expression_arm',
    'match_arm','when_entry','when','case_item','switch_entry','select_case','communication_case','foreach_statement',
    'conditional_expression','ternary_expression','conditional','ternary','optional_chain','conditional_access_expression',
    'preproc_if','preproc_ifdef',
}
# Avoid double counting wrapper and label nodes in the same grammar.
IGNORED_BRANCHES = {'java':{'switch_block_statement_group'}, 'csharp':{'switch_block_statement_group'},
                    'ruby':{'case_statement'}, 'bash':{'case_statement'}, 'dart':{'switch_entry'}}
CONTAINERS = {
    'hcl':{'block','tuple','object','for_tuple_expr','for_object_expr','conditional'},
    'sql':{'statement','select','subquery','join','case','cte','binary_expression'},
    'css':{'rule_set','media_statement','supports_statement','block'},
    'json':{'object','array'}, 'yaml':{'block_mapping','block_sequence','flow_mapping','flow_sequence'},
    'html':{'element'}, 'xml':{'element'}, 'toml':{'table','table_array_element','array','inline_table'},
    'dockerfile':{'stage','run_instruction','if_statement','for_statement'},
    'make':{'rule','conditional','conditional_directive'},
    'graphql':{'selection_set','object_type_definition','input_object_type_definition','list_type'},
}


def analyze_bytes(data, *, relative_path, language):
    if language == 'python':
        return analyze_python_bytes(data, relative_path=relative_path)
    family = 'structure' if language in STRUCTURAL_LANGUAGES else 'control_flow'
    base = dict(path=relative_path, language=language, sha256=hashlib.sha256(data).hexdigest(),
                lines=len(data.splitlines()), metric_family=family)
    if language not in CONTROL_LANGUAGES | STRUCTURAL_LANGUAGES:
        return FileMetric(**base, parse_error='No validated complexity adapter')
    try:
        if version('tree-sitter-language-pack') != '0.13.0' or version('tree-sitter') != '0.25.2':
            raise ValueError('Parser bundle version does not match the analysis contract')
        from tree_sitter_language_pack import get_parser
        data.decode('utf-8')
        root = get_parser(language).parse(data).root_node
    except (ImportError, PackageNotFoundError, LookupError, ValueError, UnicodeDecodeError) as exc:
        return FileMetric(**base, parse_error=f'Parser unavailable: {type(exc).__name__}')
    if root.has_error:
        return FileMetric(**base, parse_error='Syntax or dialect not fully recognized; no score assigned')
    if family == 'structure':
        return _structural(root, base, language, data)
    metrics, outside, units, occurrences = [], [], [], Counter()
    # Iterative traversal bounds Python stack use for deeply nested customer code.
    stack = [(root, None)]
    while stack:
        node, owner = stack.pop()
        if node.type in FUNCTIONS[language]:
            name = node.child_by_field_name('name') or node.child_by_field_name('declarator')
            if language == 'dart' and node.prev_named_sibling:
                name = node.prev_named_sibling.child_by_field_name('name')
            while name and name.child_by_field_name('declarator'):
                name = name.child_by_field_name('declarator')
            symbol = (data[name.start_byte:name.end_byte].decode()[:160] if name else '<'+node.type+'>')
            occurrences[symbol] += 1
            owner = {'symbol':symbol, 'occurrence':occurrences[symbol], 'line':node.start_point.row+1,
                     'end_line':max(node.start_point.row+1,node.end_point.row+1), 'branches':[]}
            units.append(owner)
        evidence = []
        if node.type in BRANCHES - IGNORED_BRANCHES.get(language,set()):
            # Default cases do not add an alternative decision.
            if node.type not in {'switch_case','case_statement','case_switch_label','switch_label','switch_section','when_entry','switch_entry'} or not any(c.type in {'default','default_keyword','else'} for c in node.children):
                evidence.append(BranchEvidence(node.type,node.start_point.row+1))
        for token in node.children:
            if not token.is_named and token.type in {'&&','||','??','and','or'}:
                evidence.append(BranchEvidence('short-circuit',token.start_point.row+1))
        (owner['branches'] if owner else outside).extend(evidence)
        stack.extend((child,owner) for child in reversed(node.named_children))
    for unit in units:
        branches = tuple(unit.pop('branches'))
        metrics.append(FunctionMetric(**unit,cyclomatic=1+sum(b.contribution for b in branches),branches=branches))
    # Script/module control flow is a measured unit too, never discarded.
    if outside:
        metrics.append(FunctionMetric('<module>',1,1,max(1,base['lines']),1+sum(b.contribution for b in outside),tuple(outside)))
    return FileMetric(**base,functions=tuple(metrics))


def _structural(root, base, language, data):
    branches, max_depth, containers = [], 0, 0
    stack = [(root,0)]
    while stack:
        node, depth = stack.pop()
        if language in {'html','xml'} and node.type in {'script_element','style_element','raw_text'}:
            return FileMetric(**base,parse_error='Embedded source requires an injection adapter; retained as unknown')
        if node.type in CONTAINERS[language]:
            depth += 1; containers += 1; max_depth = max(max_depth,depth)
            if depth > 3:
                branches.append(BranchEvidence('nesting-excess',node.start_point.row+1,depth-3))
            # Fan-out means child structures, not scalar declarations. A flat
            # token palette or dependency manifest is not hundreds of decisions.
            children, pending = [], list(node.named_children)
            while pending:
                child = pending.pop()
                if child.type in CONTAINERS[language]:
                    children.append(child)
                elif 'comment' not in child.type:
                    pending.extend(child.named_children)
            if len(children)>8:
                branches.append(BranchEvidence('fanout-excess',node.start_point.row+1,len(children)-8))
        stack.extend((child,depth) for child in reversed(node.named_children))
    points = sum(b.contribution for b in branches)
    unit = FunctionMetric('<document>',1,1,max(1,base['lines']),points+1,tuple(branches))
    return FileMetric(**base,functions=(unit,),structural={'max_depth':max_depth,'containers':containers,
        'nesting_points':sum(b.contribution for b in branches if b.kind=='nesting-excess'),
        'fanout_points':sum(b.contribution for b in branches if b.kind=='fanout-excess')})
