"""Bundled CST adapters. Measurements never execute repository code."""
from collections import Counter
import hashlib
from importlib.metadata import version, PackageNotFoundError
from dataclasses import replace
from html import unescape
import re

from .burden import CONTROL_LANGUAGES, STRUCTURAL_LANGUAGES
from .models import BranchEvidence, FileMetric, FunctionMetric
from .python_analyzer import analyze_python_bytes
from .javascript_analyzer import analyze_javascript_bytes
from .document_analyzer import analyze_document
from .c_family import declaration_syntax

# Grammar-specific node names: closures own their branches exactly once.
FUNCTIONS = {
    'javascript': {'function_declaration','function_expression','generator_function_declaration','generator_function','arrow_function','method_definition'},
    'typescript': {'function_declaration','function_expression','generator_function_declaration','generator_function','arrow_function','method_definition'},
    'tsx': {'function_declaration','function_expression','generator_function_declaration','generator_function','arrow_function','method_definition'},
    'c': {'function_definition'}, 'cpp': {'function_definition','lambda_expression'},
    'c_header': {'function_definition','lambda_expression'},
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
    'for_statement','for_in_statement','for_expression','for','for_range_loop','enhanced_for_statement',
    'while_statement','while_expression','while','while_modifier','until','until_modifier',
    'do_statement','do_while_statement','repeat_statement',
    'catch_clause','catch_block','catch','rescue','rescue_modifier',
    'case_statement','switch_case','case_switch_label','switch_label','switch_section','switch_statement_case','expression_case','type_case','switch_expression_arm',
    'match_arm','when_entry','when','case_item','switch_entry','select_case','communication_case','foreach_statement',
    'conditional_expression','ternary_expression','conditional','ternary','optional_chain','conditional_access_expression',
    'preproc_if','preproc_ifdef','try_expression','elvis_expression','guard_statement','if_element',
}
# Avoid double counting wrapper and label nodes in the same grammar.
IGNORED_BRANCHES = {'java':{'switch_block_statement_group'}, 'csharp':{'switch_block_statement_group'},
                    'ruby':{'case_statement'}, 'bash':{'case_statement'}, 'dart':{'switch_entry'},
                    'swift':{'try_expression'}}
CONTAINERS = {
    'hcl':{'block','tuple','object','for_tuple_expr','for_object_expr','conditional'},
    'sql':{'statement','select','subquery','join','case','cte','binary_expression'},
    'css':{'rule_set','media_statement','supports_statement','block'},
    'json':{'object','array'}, 'yaml':{'block_mapping','block_sequence','flow_mapping','flow_sequence'},
    'html':{'element'}, 'xml':{'element'}, 'toml':{'table','table_array_element','array','inline_table'},
    'dockerfile':{'stage','run_instruction','if_statement','for_statement'},
    'make':{'rule','conditional','conditional_directive'},
    'graphql':{'selection_set','object_type_definition','input_object_type_definition','list_type'},
    'cmake':{'if_condition','foreach_loop','while_loop','function_def','macro_def','normal_command'},
    'protobuf':{'message','message_body','enum','enum_body','service','oneof','extend'},
    'config':{'section'}, 'properties':{'file'},
}


def analyze_bytes(data, *, relative_path, language):
    if language == 'python':
        return analyze_python_bytes(data, relative_path=relative_path)
    if language in {'javascript','typescript','tsx'}:
        return analyze_javascript_bytes(data, relative_path=relative_path, language=language)
    family = 'structure' if language in STRUCTURAL_LANGUAGES else 'control_flow'
    base = dict(path=relative_path, language=language, sha256=hashlib.sha256(data).hexdigest(),
                lines=len(data.splitlines()), metric_family=family)
    if language not in CONTROL_LANGUAGES | STRUCTURAL_LANGUAGES:
        return FileMetric(**base, parse_error='No validated complexity adapter')
    if language in {'css','openstep'}:
        return analyze_document(data, base, language)
    try:
        if version('tree-sitter-language-pack') != '0.13.0' or version('tree-sitter') != '0.25.2':
            raise ValueError('Parser bundle version does not match the analysis contract')
        from tree_sitter_language_pack import get_parser
        data.decode('utf-8')
        grammar = {'config':'ini','protobuf':'proto'}.get(language, language)
        if language == 'dart':
            from tree_sitter import Language, Parser
            import tree_sitter_dart
            if version('tree-sitter-dart') != '0.1.0':
                raise ValueError('Dart grammar differs from the analysis contract')
            root = Parser(Language(tree_sitter_dart.language())).parse(data).root_node
        elif language in {'c','cpp','c_header'}:
            grammars = ('c','cpp') if language == 'c_header' else (grammar,)
            root = None
            for candidate in (data, declaration_syntax(data)):
                for grammar in grammars:
                    root = get_parser(grammar).parse(candidate).root_node
                    if not root.has_error: break
                if not root.has_error: break
        else:
            root = get_parser(grammar).parse(data).root_node
    except (ImportError, PackageNotFoundError, LookupError, ValueError, UnicodeDecodeError) as exc:
        return FileMetric(**base, parse_error=f'Parser unavailable: {type(exc).__name__}')
    if root.has_error:
        return FileMetric(**base, parse_error='Syntax or dialect not fully recognized; no score assigned')
    if family == 'structure':
        document = _structural(root, base, language, data)
        return _embedded(root, document, data) if language == 'html' else document
    metrics, outside, units, occurrences = [], [], [], Counter()
    # Iterative traversal bounds Python stack use for deeply nested customer code.
    stack = [(root, None)]
    while stack:
        node, owner = stack.pop()
        if node.type in FUNCTIONS[language]:
            name = node.child_by_field_name('name') or node.child_by_field_name('declarator')
            if language == 'kotlin' and name is None:
                name = next((child for child in node.named_children if child.type == 'simple_identifier'), None)
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
        if language=='dart' and node.type in {'conditional_assignable_selector','null_aware_element'}:
            evidence.append(BranchEvidence('null-aware-access',node.start_point.row+1))
        if node.type in BRANCHES - IGNORED_BRANCHES.get(language,set()):
            # Default cases do not add an alternative decision.
            if node.type not in {'switch_case','case_statement','case_switch_label','switch_label','switch_section','when_entry','switch_entry'} or not any(c.type in {'default','default_keyword','else'} for c in node.children):
                evidence.append(BranchEvidence(node.type,node.start_point.row+1))
        if language in {'javascript','typescript','tsx'} and (
            node.type in {'assignment_pattern','object_assignment_pattern'}
            or node.type in {'required_parameter','optional_parameter'} and node.child_by_field_name('value') is not None
        ):
            evidence.append(BranchEvidence('default-evaluation',node.start_point.row+1))
        for token in node.children:
            if language=='dart' and not token.is_named and token.type=='when':
                evidence.append(BranchEvidence('pattern-guard',token.start_point.row+1))
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


def _embedded(root, document, data):
    """Inline scripts retain original source lines and their own function scope."""
    functions, script_count, has_script = [], 0, False
    structure_branches = list(document.functions[0].branches)
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type=='attribute':
            parts=node.named_children
            name=data[parts[0].start_byte:parts[0].end_byte].decode().lower() if parts else ''
            if len(parts)>1:
                source,line_map=_attribute_source(parts[-1],data)
                url=re.match(r'^\s*javascript:',source,re.IGNORECASE) if name in {'href','src','action','formaction','xlink:href'} else None
                if name.startswith('on') or url:
                    if url:
                        line_map=line_map[len(source[:url.end()].splitlines())-1:]
                        source=source[url.end():]
                    embedded=analyze_bytes(source.encode(),relative_path=document.path,language='javascript')
                    if embedded.parse_error:
                        return replace(document,functions=(),parse_error='Inline event or URL source could not be fully analyzed; no score assigned')
                    has_script=True;script_count+=1
                    for function in embedded.functions:
                        functions.append(replace(function,symbol=f'<inline:{script_count}>/{function.symbol}',
                            line=line_map[function.line-1],end_line=line_map[function.end_line-1],
                            branches=tuple(replace(branch,line=line_map[branch.line-1]) for branch in function.branches)))
        if node.type in {'script_element','style_element'}:
            tag = next((child for child in node.named_children if child.type=='start_tag'), None)
            attributes = {}
            for attr in tag.named_children if tag else ():
                if attr.type=='attribute':
                    parts=attr.named_children
                    key=data[parts[0].start_byte:parts[0].end_byte].decode().lower()
                    attributes[key]=data[parts[-1].start_byte:parts[-1].end_byte].decode().strip('\"\'').lower() if len(parts)>1 else ''
            body=next((child for child in node.named_children if child.type=='raw_text'),None)
            if body and data[body.start_byte:body.end_byte].strip() and 'src' not in attributes:
                raw=data[body.start_byte:body.end_byte]
                mime=attributes.get('type','').split(';')[0].strip()
                if node.type=='style_element':
                    if attributes.get('lang','css')!='css':
                        return replace(document,functions=(),parse_error='Inline stylesheet language is not supported; no score assigned')
                    embedded=analyze_bytes(raw,relative_path=document.path,language='css')
                elif mime in {'application/json','application/ld+json','importmap','speculationrules'}:
                    embedded=analyze_bytes(raw,relative_path=document.path,language='json')
                elif mime in {'','module','text/javascript','application/javascript','text/ecmascript','application/ecmascript','text/typescript'}:
                    if attributes.get('lang','javascript') not in {'js','javascript','jsx','ts','typescript','tsx'}:
                        return replace(document,functions=(),parse_error='Inline script language is not supported; no score assigned')
                    language='tsx' if attributes.get('lang')=='tsx' else 'typescript' if mime=='text/typescript' or attributes.get('lang') in {'ts','typescript'} else 'javascript'
                    embedded=analyze_bytes(raw,relative_path=document.path,language=language)
                    has_script=True;script_count+=1
                    offset=body.start_point.row
                    for function in embedded.functions:
                        functions.append(replace(function,symbol=f'<script:{script_count}>/{function.symbol}',
                            line=function.line+offset,end_line=function.end_line+offset,
                            branches=tuple(replace(branch,line=branch.line+offset) for branch in function.branches)))
                else:
                    return replace(document,functions=(),parse_error='Inline script language is not supported; no score assigned')
                if embedded.parse_error:
                    return replace(document,functions=(),parse_error='Inline source could not be fully analyzed; no score assigned')
                if embedded.metric_family=='structure':
                    structure_branches.extend(replace(branch,line=branch.line+body.start_point.row)
                        for function in embedded.functions for branch in function.branches)
        stack.extend(reversed(node.named_children))
    if not has_script:
        return replace(document,functions=(replace(document.functions[0],branches=tuple(structure_branches),
            cyclomatic=1+sum(branch.contribution for branch in structure_branches)),))
    return replace(document,metric_family='control_flow',functions=tuple(functions),
        structure_branches=tuple(structure_branches))


def _attribute_source(node, data):
    """Decode HTML entities while mapping virtual JS newlines to physical lines."""
    text=data[node.start_byte:node.end_byte].decode()
    if text[:1] in {'\"',"'"}:
        text=text[1:-1]
    text=text.replace('\r\n','\n').replace('\r','\n')
    line=node.start_point.row+1
    lines,pieces=[line],[]
    parts=re.split(r'(&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);?)',text)
    for index,part in enumerate(parts):
        decoded=unescape(part) if index%2 else part
        pieces.append(decoded)
        for char in decoded:
            if char in '\n\r\u2028\u2029':
                if not index%2:
                    line+=1
                lines.append(line)
    return ''.join(pieces),lines
