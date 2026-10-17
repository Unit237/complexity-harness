"""Bundled CST adapters. Measurements never execute repository code."""
from collections import Counter
import hashlib
from importlib.metadata import version, PackageNotFoundError
from dataclasses import replace
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
    'groovy': {'method_declaration','constructor_declaration','closure','lambda_expression'},
    'nix': {'function_expression'}, 'starlark': {'function_definition','lambda'},
    'powershell': {'function_statement','script_block_expression'},
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
    'preproc_if','preproc_ifdef','preproc_elif','try_expression','elvis_expression','guard_statement','if_element',
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
    'gomod':{'module_directive','require_directive','replace_directive','exclude_directive','use_directive'},
}


def analyze_bytes(data, *, relative_path, language, _macro_depth=0):
    if language == 'python':
        return analyze_python_bytes(data, relative_path=relative_path)
    if language in {'javascript','typescript','tsx'}:
        return analyze_javascript_bytes(data, relative_path=relative_path, language=language)
    family = 'structure' if language in STRUCTURAL_LANGUAGES else 'control_flow'
    base = dict(path=relative_path, language=language, sha256=hashlib.sha256(data).hexdigest(),
                lines=len(data.splitlines()), metric_family=family)
    if language not in CONTROL_LANGUAGES | STRUCTURAL_LANGUAGES:
        return FileMetric(**base, parse_error='No validated complexity adapter')
    if language=='assembly':
        from .assembly_analyzer import analyze_assembly
        return analyze_assembly(data,base)
    if language=='c_header' and re.search(rb'(?m)^\s*(?:CMP[A-Z]*|MOVQ|CMOV[A-Z]+)\s+[^\n]*(?:\bAX\b|\bR\d+\b|\(SB\))',data):
        from .assembly_analyzer import analyze_assembly
        assembly=analyze_assembly(data,base)
        if not assembly.parse_error:return assembly
    if language=='batch':
        from .batch_analyzer import analyze_batch
        return analyze_batch(data,base)
    if language=='nsis':
        from .installer_analyzer import analyze_installer
        return analyze_installer(data,base)
    if language in {'procfile','just'}:
        functions=[]
        for line,source in enumerate(data.decode('utf-8-sig').splitlines(),1):
            if not source.strip() or source.lstrip().startswith('#'):continue
            if language=='procfile':
                match=re.fullmatch(r'[\w-]+:\s*(.+)',source)
                if not match:return FileMetric(**base,parse_error='Invalid Procfile process declaration')
                source=match[1]
            elif not source.startswith((' ','\t')):
                if not re.fullmatch(r'[\w-]+:\s*',source):return FileMetric(**base,parse_error='Unsupported Just directive or expansion')
                continue
            if language=='just' and '{{' in source:return FileMetric(**base,parse_error='Just expression adapter is not available')
            measured=analyze_bytes(source.lstrip().encode(),relative_path=relative_path,language='bash')
            if measured.parse_error:return FileMetric(**base,parse_error='Process shell syntax is not fully recognized')
            functions.extend(replace(f,symbol=f'<process:{line}>/{f.symbol}',line=f.line+line-1,end_line=f.end_line+line-1,
                branches=tuple(replace(b,line=b.line+line-1) for b in f.branches)) for f in measured.functions)
        return FileMetric(**base,functions=tuple(functions))
    if language=='gotemplate':
        from .template_analyzer import analyze_template
        return analyze_template(data,base,analyze_bytes)
    if language=='dockerfile':
        from .build_analyzer import analyze_docker
        return analyze_docker(data,base,analyze_bytes)
    if language=='make':
        from .make_analyzer import analyze_make
        return analyze_make(data,base,analyze_bytes)
    if language=='unknown':
        return _detect_source(data,base)
    if language=='yaml' and (relative_path.startswith('.github/workflows/') or relative_path.endswith(('/action.yml','/action.yaml'))):
        from .workflow_analyzer import analyze_workflow
        return analyze_workflow(data,base,analyze_bytes)
    if language in {'abnf','shell_cases'}:
        try:
            if language=='abnf':
                from abnf.parser import ABNFGrammarRule
                if version('abnf')!='2.9.0':raise ValueError('ABNF grammar differs from analysis contract')
                text=data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n').rstrip().replace('\n','\r\n')+'\r\n'
                root=ABNFGrammarRule('rulelist').parse_all(text)
                containers=sum(1 for line in text.splitlines() if re.match(r'^[A-Za-z][\w-]*\s*=',line))
            else:
                containers=0
                for source in data.decode('utf-8-sig').splitlines():
                    if not source or source.lstrip().startswith('#'):continue
                    if relative_path.endswith('envVarTest'):
                        if len(source.split('|'))!=3 or source.split('|')[0] not in {'A','U','W'}:raise ValueError('Invalid shell reference case')
                    elif not source.startswith('ENV ') and len(source.split('|'))!=2:raise ValueError('Invalid shell word reference case')
                    containers+=1
            return FileMetric(**base,functions=(FunctionMetric('<document>',1,1,max(1,base['lines']),1,()),),structural={'containers':containers,'max_depth':1,'nesting_points':0,'fanout_points':0})
        except Exception as exc:return FileMetric(**base,parse_error=f'Reference format syntax unavailable: {type(exc).__name__}')
    if language in {'html','vue'}:
        from .markup_analyzer import analyze_markup
        from .template_analyzer import template_parts
        try:
            vue=language=='vue' or bool(re.search(rb'\bv-(?:if|for|on|bind|model|show)\b',data))
            go_template=language=='html' and not vue and (data.startswith((b'---\n',b'+++\n')) or re.search(r'(?:^|/)(?:layouts|shortcodes)/',relative_path) or b'{{<' in data or b'{{%' in data)
            masked,functions,_=template_parts(data,base) if go_template and b'{{' in data and not re.search(rb'(?<!\{)\{%',data) else (data,(),0)
            document=analyze_markup(masked,base,analyze_bytes,vue=vue)
            if not functions or document.parse_error:return document
            diagnostics=tuple(b for f in document.functions for b in f.branches) if document.metric_family=='structure' else document.structure_branches
            return replace(document,metric_family='control_flow',functions=functions+(document.functions if document.metric_family=='control_flow' else ()),structure_branches=diagnostics)
        except ValueError as exc:return FileMetric(**base,parse_error=str(exc))
    if language in {'config','xml'}:
        from .document_analyzer import analyze_configuration
        return analyze_configuration(data,base,language)
    if language=='gomod' and relative_path.endswith('.work'):
        import shlex
        depth=0
        try:
            for source in data.decode('utf-8-sig').splitlines():
                tokens=shlex.split(source.split('//',1)[0])
                if not tokens:continue
                if tokens==[')']:
                    if not depth:raise ValueError('Unmatched workspace block')
                    depth=0
                elif depth:
                    if len(tokens)!=1:raise ValueError('Unsupported workspace use entry')
                elif tokens[0] not in {'go','toolchain','use','replace'}:raise ValueError('Unknown Go workspace directive')
                elif tokens[-1]=='(':depth=1
                elif len(tokens)<2:raise ValueError('Missing Go workspace directive value')
            if depth:raise ValueError('Unclosed workspace block')
            return FileMetric(**base,functions=(FunctionMetric('<document>',1,1,max(1,base['lines']),1,()),),structural={'containers':1,'max_depth':1,'nesting_points':0,'fanout_points':0})
        except ValueError as exc:return FileMetric(**base,parse_error=str(exc))
    if language=='sql':
        from .document_analyzer import analyze_sql
        return analyze_sql(data,base)
    if language in {'css','openstep'}:
        return analyze_document(data, base, language)
    source_line=None
    try:
        if version('tree-sitter-language-pack') != '0.13.0' or version('tree-sitter') != '0.25.2':
            raise ValueError('Parser bundle version does not match the analysis contract')
        from tree_sitter_language_pack import get_parser
        data.decode('utf-8')
        # A final line terminator is optional in these source formats. Some
        # bundled grammars require it; never invent source lines in evidence.
        parse_data = data.removeprefix(b'\xef\xbb\xbf') + b'\n'
        data=parse_data
        grammar = {'config':'ini','protobuf':'proto'}.get(language, language)
        template_functions=()
        preprocessor_branches=[]
        if language=='yaml' and b'{{' in data and b'{%' not in data:
            from .template_analyzer import template_parts
            parse_data,template_functions,_=template_parts(data,base)
            data=parse_data
        if language in {'groovy','kotlin','swift','powershell'}:
            from tree_sitter import Language, Parser
            import importlib
            module,distribution,expected = {
                'groovy':('dekobon_tree_sitter_groovy','dekobon-tree-sitter-groovy','0.3.0'),
                'kotlin':('tree_sitter_kotlin','tree-sitter-kotlin','1.1.0'),
                'swift':('tree_sitter_swift','tree-sitter-swift','0.7.4'),
                'powershell':('tree_sitter_powershell','tree-sitter-powershell','0.26.4'),
            }[language]
            if version(distribution)!=expected:
                raise ValueError('Grammar differs from the analysis contract')
            root=Parser(Language(importlib.import_module(module).language())).parse(parse_data).root_node
            if root.has_error and language=='powershell':
                # Native executables accept argv spellings such as -count=1
                # and ./pkg/..., which this grammar mistakes for expressions.
                # Normalize only data-only command arguments, never code,
                # subexpressions, script blocks or control/pipeline operators.
                keywords=set(b'begin break catch class clean configuration continue data define do dynamicparam else elseif end enum exit filter finally for foreach from function if in inlinescript param process return switch throw trap try until using var while workflow parallel sequence'.split())
                def argv(match):
                    if match[1].strip().lower() in keywords or re.search(rb'[(){};&|`]',match[2]):return match[0]
                    return match[1]+re.sub(rb'[^\s]',b'x',match[2])
                parse_data=re.sub(rb'(?m)^([ \t]*[A-Za-z_][\w.-]*)([ \t]+[^\r\n]*)$',argv,parse_data)
                root=Parser(Language(importlib.import_module(module).language())).parse(parse_data).root_node
            if root.has_error and language=='kotlin':
                # dynamic is a soft type keyword and a legal property name.
                parse_data=re.sub(rb'\bdynamic\b',b'dynamiC',parse_data)
                # A NUL in a block comment must not terminate the native input.
                # Keep all bytes/lines and reject NULs anywhere else normally.
                token=rb'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|//[^\r\n]*|/\*[\s\S]*?\*/'
                parse_data=re.sub(token,lambda m:m.group().replace(b'\0',b' ') if m.group().startswith((b'/*',b'//')) else m.group(),parse_data)
                root=Parser(Language(importlib.import_module(module).language())).parse(parse_data).root_node
            if root.has_error and language=='swift':
                # These constant spellings carry no runtime choices. The old
                # grammar lacks Void tuple constructor arguments and _runtime.
                parse_data=re.sub(rb'(?<=[(:=,])([ \t]*)\(\)(?=[ \t]*[),\r\n;])',rb'\g<1>0 ',parse_data)
                parse_data=re.sub(rb'(?m)^([ \t]*#(?:if|elseif)[^\r\n]*?)\b_runtime(?=\s*\()',rb'\1os      ',parse_data)
                root=Parser(Language(importlib.import_module(module).language())).parse(parse_data).root_node
            data=parse_data
        elif language == 'dart':
            from tree_sitter import Language, Parser
            import tree_sitter_dart
            if version('tree-sitter-dart') != '0.1.0':
                raise ValueError('Dart grammar differs from the analysis contract')
            root = Parser(Language(tree_sitter_dart.language())).parse(parse_data).root_node
        elif language in {'c','cpp','c_header'}:
            grammars = ('c','cpp') if language == 'c_header' else (grammar,)
            root = None
            for candidate in (parse_data, declaration_syntax(parse_data)):
                for grammar in grammars:
                    selected = candidate
                    if grammar == 'cpp':
                        from .c_family import alternative_operators
                        selected = alternative_operators(candidate, get_parser(grammar).parse(candidate).root_node)
                    root = get_parser(grammar).parse(selected).root_node
                    if not root.has_error: break
                if not root.has_error: break
            data = selected
        else:
            root = get_parser(grammar).parse(parse_data).root_node
            if language=='csharp' and root.has_error:
                from .c_family import conditional_compilation
                parse_data,preprocessor_branches=conditional_compilation(parse_data,root)
                # Index initializer entries with two simple identifiers have
                # equivalent collection-initializer syntax, with no decisions
                # in either operand. Keep all bytes and every surrounding node.
                def initializer(match):
                    replacement=b'{'+match[1]+b','+match[2]+b'}'
                    return replacement+b' '*(len(match[0])-len(replacement))
                parse_data=re.sub(rb'\[\s*([A-Za-z_]\w*)\s*\]\s*=\s*([A-Za-z_]\w*)(?=\s*})',initializer,parse_data)
                root=get_parser(grammar).parse(parse_data).root_node
            if language=='bash' and root.has_error:
                # POSIX permits an implicit "$@" list without a semicolon.
                parse_data=re.sub(rb'\bfor([ \t]+[A-Za-z_][A-Za-z_0-9]*)[ \t]do\b',rb'for\1;do',parse_data)
                root=get_parser(grammar).parse(parse_data).root_node
                # The grammar rejects concatenated quoted glob fragments in
                # case labels. Normalize only those literal ERROR nodes.
                spans=[];pending=[root]
                while pending:
                    node=pending.pop()
                    raw=parse_data[node.start_byte:node.end_byte]
                    if node.type=='ERROR' and node.parent and node.parent.type in {'case_item','case_statement'} and raw.startswith(b'*') and b'"' in raw and not re.search(rb'[$`;\n<>&|]',raw):spans.append((node.start_byte,node.end_byte))
                    else:pending.extend(node.named_children)
                if spans:
                    normalized=bytearray(parse_data)
                    for start,end in spans:normalized[start:end]=b'*'+b' '*(end-start-1)
                    parse_data=bytes(normalized);root=get_parser(grammar).parse(parse_data).root_node
                if root.has_error and re.search(rb'\\\r?\n',parse_data):
                    # Join shell continuations before parsing; preserve the
                    # physical source positions through compact offset maps.
                    from bisect import bisect_right
                    original=parse_data;protected=[];pending=[root]
                    while pending:
                        node=pending.pop()
                        if node.type in {'raw_string','heredoc_body'}:protected.append((node.start_byte,node.end_byte))
                        else:pending.extend(node.named_children)
                    protected.sort();starts=[p[0] for p in protected]
                    pieces=[];joins=[];removed=[0];position=0
                    for match in re.finditer(rb'\\\r?\n',original):
                        at=bisect_right(starts,match.start())-1
                        if at>=0 and protected[at][1]>match.start():continue
                        pieces.append(original[position:match.start()]);joins.append(match.start()-removed[-1])
                        removed.append(removed[-1]+len(match[0]));position=match.end()
                    pieces.append(original[position:]);parse_data=b''.join(pieces)
                    newlines=[m.start() for m in re.finditer(b'\n',original)]
                    def source_line(byte):return bisect_right(newlines,byte+removed[bisect_right(joins,byte)])+1
                    root=get_parser(grammar).parse(parse_data).root_node
                if root.has_error:
                    normalized=bytearray(parse_data);pending=[root]
                    while pending:
                        node=pending.pop()
                        # Bash accepts a compound `fi` immediately before the
                        # loop's `done`. This grammar requires a separator.
                        if node.type=='fi' and re.match(rb'[ \t]+done\b',parse_data[node.end_byte:]):normalized[node.end_byte]=ord(';')
                        else:pending.extend(node.children)
                    # Two adjacent subshell opens followed by a multiword
                    # command cannot be an arithmetic expression. Disambiguate
                    # using an existing space, without changing source offsets.
                    parse_data=re.sub(rb'[ \t]\(\((?=[A-Za-z_][\w.-]*[ \t]+[A-Za-z_/.-])',b'( (',bytes(normalized))
                    root=get_parser(grammar).parse(parse_data).root_node
            data=parse_data
    except (ImportError, PackageNotFoundError, LookupError, ValueError, UnicodeDecodeError) as exc:
        return FileMetric(**base, parse_error=f'Parser unavailable: {type(exc).__name__}')
    if root.has_error:
        if language in {'c','cpp','c_header'}:
            from .assembly_analyzer import analyze_assembly
            assembly=analyze_assembly(data,base)
            if not assembly.parse_error:return assembly
        return FileMetric(**base, parse_error='Syntax or dialect not fully recognized; no score assigned')
    if family == 'structure':
        document = _structural(root, base, language, data)
        if document.parse_error:return document
        if template_functions:
            diagnostic=tuple(branch for unit in document.functions for branch in unit.branches) if document.metric_family=='structure' else document.structure_branches
            return replace(document,metric_family='control_flow',functions=template_functions+(document.functions if document.metric_family=='control_flow' else ()),structure_branches=diagnostic)
        return document
    def line_at(node,ending=False):
        if source_line:return source_line(max(node.start_byte,node.end_byte-1) if ending else node.start_byte)
        return (node.end_point.row if ending else node.start_point.row)+1
    metrics, outside, units, occurrences = [], [BranchEvidence(kind,line) for kind,line in preprocessor_branches], [], Counter()
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
            if language=='powershell' and name is None:
                name=next((child for child in node.named_children if child.type=='function_name'),None)
            while name and name.child_by_field_name('declarator'):
                name = name.child_by_field_name('declarator')
            symbol = (data[name.start_byte:name.end_byte].decode()[:160] if name else '<'+node.type+'>')
            occurrences[symbol] += 1
            owner = {'symbol':symbol, 'occurrence':occurrences[symbol], 'line':line_at(node),
                     'end_line':min(max(1,base['lines']),max(line_at(node),line_at(node,ending=True))), 'branches':[]}
            units.append(owner)
        evidence = []
        if language=='dart' and node.type in {'conditional_assignable_selector','null_aware_element'}:
            evidence.append(BranchEvidence('null-aware-access',line_at(node)))
        if language=='groovy' and node.type=='safe_navigation_expression':
            evidence.append(BranchEvidence('null-aware-access',line_at(node)))
        if language=='starlark' and node.type in {'for_in_clause','if_clause'}:
            evidence.append(BranchEvidence(node.type,line_at(node)))
        if language=='powershell' and node.type in {'elseif_clause','trap_statement','switch_clause'}:
            condition=next((child for child in node.named_children if child.type=='switch_clause_condition'),None)
            if not condition or condition.text.strip().lower()!=b'default':evidence.append(BranchEvidence(node.type,line_at(node)))
        if node.type in BRANCHES - IGNORED_BRANCHES.get(language,set()):
            # Default cases do not add an alternative decision.
            if node.type not in {'switch_case','case_statement','case_switch_label','switch_label','switch_section','when_entry','switch_entry'} or not any(c.type in {'default','default_keyword','else'} for c in node.children):
                evidence.append(BranchEvidence(node.type,line_at(node)))
        if language in {'javascript','typescript','tsx'} and (
            node.type in {'assignment_pattern','object_assignment_pattern'}
            or node.type in {'required_parameter','optional_parameter'} and node.child_by_field_name('value') is not None
        ):
            evidence.append(BranchEvidence('default-evaluation',line_at(node)))
        for token in node.children:
            if language=='kotlin' and not token.is_named and token.type=='?:':
                evidence.append(BranchEvidence('elvis-expression',line_at(token)))
            if language=='nix' and not token.is_named and token.type=='->':
                evidence.append(BranchEvidence('implication',line_at(token)))
            if language=='powershell' and not token.is_named and token.type.lower() in {'-and','-or'}:
                evidence.append(BranchEvidence('short-circuit',line_at(token)))
            if language=='dart' and not token.is_named and token.type=='when':
                evidence.append(BranchEvidence('pattern-guard',line_at(token)))
            if language=='ruby' and not token.is_named and token.type in {'||=','&&='}:
                evidence.append(BranchEvidence('short-circuit-assignment',line_at(token)))
            if not token.is_named and token.type in {'&&','||','??','and','or'} and node.type not in {'reference_declarator','abstract_reference_declarator','operator_name','ref_qualifier'}:
                evidence.append(BranchEvidence('short-circuit',line_at(token)))
        (owner['branches'] if owner else outside).extend(evidence)
        stack.extend((child,owner) for child in reversed(node.named_children))
    for unit in units:
        branches = tuple(unit.pop('branches'))
        metrics.append(FunctionMetric(**unit,cyclomatic=1+sum(b.contribution for b in branches),branches=branches))
    # Script/module control flow is a measured unit too, never discarded.
    if outside:
        metrics.append(FunctionMetric('<module>',1,1,max(1,base['lines']),1+sum(b.contribution for b in outside),tuple(outside)))
    structural={}
    if language in {'c','cpp','c_header'}:
        try:
            macros,literals=_c_macro_units(root,data,base,_macro_depth)
            metrics.extend(macros)
            if literals:structural['unscored_source_sha256']=hashlib.sha256(repr(literals).encode()).hexdigest()
        except ValueError as exc:return FileMetric(**base,parse_error=str(exc))
    return FileMetric(**base,functions=tuple(metrics),structural=structural)


def _c_macro_units(root,data,base,depth):
    """Macro bodies are source too; grammar fragments use explicit contexts."""
    if depth>50:raise ValueError('Macro nesting exceeds the analysis budget')
    metrics=[];literals=[];pending=[root]
    while pending:
        node=pending.pop()
        if node.type not in {'preproc_def','preproc_function_def'}:
            pending.extend(reversed(node.named_children));continue
        value=node.child_by_field_name('value');name=node.child_by_field_name('name')
        if value is None:continue
        body=value.text;symbol='<macro:'+name.text.decode()+'>'
        if not re.search(rb'\b(?:if|for|while|case|catch|and|or)\b|\?|&&|\|\|',body):
            literals.append((symbol,body.decode()));continue
        from tree_sitter_language_pack import get_parser
        fragment=get_parser('cpp' if base['language']=='cpp' else 'c').parse(body).root_node
        braces=0;tokens=[fragment]
        while tokens:
            token=tokens.pop()
            if 'string' in token.type or 'comment' in token.type or 'char_literal' in token.type:continue
            if not token.is_missing:braces+=(token.type=='{')-(token.type=='}')
            tokens.extend(token.children)
        if braces<0 or braces>16:raise ValueError('Macro fragment needs its caller expansion before scoring')
        measured=None;prefixes=(b'void __macro(){\n',b'void __macro(){if(0){}\n',b'void __macro(){try{}\n')
        for prefix in prefixes:
            candidate=analyze_bytes(prefix+body+b'\n;\n'+b'}'*(braces+1),relative_path=base['path'],language=base['language'],_macro_depth=depth+1)
            if not candidate.parse_error:measured=candidate;break
        if measured is None:raise ValueError('Control flow in a macro body could not be fully analyzed')
        line=value.start_point.row+1;end=line+body.count(b'\n');branches=[]
        for unit in measured.functions:
            branches.extend(replace(branch,line=branch.line+line-2) for branch in unit.branches if 2<=branch.line<=body.count(b'\n')+2)
        if branches:metrics.append(FunctionMetric(symbol,len(metrics)+1,line,end,1+sum(b.contribution for b in branches),tuple(branches)))
        else:literals.append((symbol,body.decode()))
    return metrics,literals


def _detect_source(data,base):
    """Extensionless files use explicit content signatures, never text guesses."""
    source=data.decode('utf-8-sig',errors='replace')
    if not source.strip():return FileMetric(**(base|{'metric_family':'structure'}))
    language=None
    if source.startswith('#!'):
        command=source.splitlines()[0]
        for pattern,candidate in [(r'\b(?:ba|da|k|z)?sh\b','bash'),(r'\bpython(?:[23](?:\.\d+)?)?\b','python'),(r'\b(?:node|nodejs)\b','javascript'),(r'\bruby\b','ruby'),(r'\blua\b','lua')]:
            if re.search(pattern,command):language=candidate;break
    elif source.lstrip().startswith(('{','[')):
        import json
        try:json.loads(source);language='json'
        except ValueError:pass
    elif source.lstrip().startswith('<?xml'):language='xml'
    elif re.search(r'(?m)^package %[A-Z][A-Z_0-9]*%\s*$',source):
        normalized=re.sub(r'%[A-Z][A-Z_0-9]*%',lambda m:'x'+' '*(len(m.group())-1),source)
        measured=analyze_bytes(normalized.encode(),relative_path=base['path'],language='go')
        return replace(measured,language='unknown',sha256=base['sha256'])
    elif source.startswith(('---\n','+++\n')):
        marker=source[:3];end=source.find('\n'+marker+'\n',4)
        if end>=0:
            metadata=source[4:end]
            parsed=analyze_bytes(metadata.encode(),relative_path=base['path'],language='yaml' if marker=='---' else 'toml')
            if parsed.parse_error:return FileMetric(**base,parse_error='Invalid document front matter')
            normalized=re.sub(r'[^\r\n]',' ',source[:end+5])+source[end+5:]
            measured=analyze_bytes(normalized.encode(),relative_path=base['path'],language='html')
            return replace(measured,language='unknown',sha256=base['sha256'])
    if not language:return FileMetric(**base,parse_error='Unrecognized source format; no score assigned',unsupported=True)
    measured=analyze_bytes(data,relative_path=base['path'],language=language)
    return replace(measured,language='unknown')


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
