"""Pinned cmd.exe CST grammar, including source inside FOR /F commands."""
from importlib.metadata import version
import re
from .models import BranchEvidence,FileMetric,FunctionMetric


def analyze_batch(data,base,depth=0):
    try:
        from tree_sitter import Language,Parser
        import tree_sitter_batch
        if version('tree-sitter-batch')!='0.11.1':raise ValueError('Batch grammar differs from analysis contract')
        if depth>50:raise ValueError('Batch command nesting exceeds the analysis budget')
        source=data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode()+b'\n'
        parser=Parser(Language(tree_sitter_batch.language()));root=parser.parse(source).root_node
        if root.has_error:
            # exit without /b is a valid unconditional command. This grammar
            # rejects that command when it follows IF; no choice is removed.
            pending=[root];normalized=bytearray(source)
            while pending:
                node=pending.pop()
                if node.type=='ERROR' and source[node.start_byte:node.end_byte].lower()==b'exit':normalized[node.start_byte:node.end_byte]=b'noop'
                pending.extend(node.named_children)
            # Quoted path prefixes can concatenate with an unquoted suffix in
            # EXIST operands. Treat that operand as one opaque value.
            pattern=rb'(?im)^(\s*@?if\s+(?:not\s+)?exist\s+)("[^"\r\n]*"[\\/][^\s<>&|]+)'
            source=re.sub(pattern,lambda m:m[1]+b'x'+b' '*(len(m[2])-1),bytes(normalized))
            root=parser.parse(source).root_node
        if root.has_error:raise ValueError('Batch syntax or dialect is not fully recognized')
        branches=[];functions=[];pending=[root]
        while pending:
            node=pending.pop();line=node.start_point.row+1
            if node.type in {'if_stmt','for_stmt'}:branches.append(BranchEvidence('batch-'+node.type,line))
            if node.type=='cond_exec':
                branches.extend(BranchEvidence('batch-short-circuit',child.start_point.row+1) for child in node.children if child.type in {'&&','||'})
            if node.type=='for_stmt':
                options=next((child.text.decode().lower() for child in node.named_children if child.type=='for_options'),'')
                if '/f' in options:
                    delimiter='`' if 'usebackq' in options else "'"
                    nested=[child for child in node.named_children if child.type=='for_set']
                    while nested:
                        child=nested.pop()
                        if child.type=='for_set_literal':
                            text=child.text.decode()
                            if text.startswith(delimiter) and text.endswith(delimiter):
                                raw=re.sub(r'\^(.)',r'\1',text[1:-1]);at=child.start_point.row+1
                                parsed=analyze_batch(raw.encode(),base|{'lines':len(raw.splitlines())},depth+1)
                                if parsed.parse_error:raise ValueError('Batch FOR /F command could not be fully analyzed')
                                for f in parsed.functions:
                                    functions.append(FunctionMetric(f'<for-f:{len(functions)+1}>/{f.symbol}',1,
                                        f.line+at-1,f.end_line+at-1,f.cyclomatic,
                                        tuple(BranchEvidence(b.kind,b.line+at-1,b.contribution) for b in f.branches)))
                        else:nested.extend(child.named_children)
            pending.extend(reversed(node.named_children))
        if branches or any(child.type!='comment' for child in root.named_children):
            functions.append(FunctionMetric('<module>',1,1,max(1,base['lines']),1+len(branches),tuple(branches)))
        return FileMetric(**base,functions=tuple(functions))
    except (ValueError,UnicodeDecodeError,ImportError) as exc:return FileMetric(**base,parse_error=str(exc))
