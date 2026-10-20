"""Common platform declaration syntax, with byte/line-preserving normalization.

This does not expand macros or remove statements, conditions or macro bodies.
Unrecognized declaration DSLs and remaining grammar errors stay unmeasured.
"""
import re


def alternative_operators(data, root):
    """C++ keyword operators have identical, byte-preserving token spellings.

    The bundled grammar misreads parenthesized `and` operands as calls. Only
    syntax tokens are normalized; literals, comments and macro bodies remain
    intact. Macro bodies are parsed separately in their own expression context.
    """
    spellings = {b'and': b'&&', b'or': b'||', b'not': b'!', b'not_eq': b'!=',
                 b'and_eq': b'&=', b'or_eq': b'|=', b'xor_eq': b'^=',
                 b'bitand': b'&', b'bitor': b'|', b'xor': b'^', b'compl': b'~'}
    result = bytearray(data)
    pending = [root]
    while pending:
        node = pending.pop()
        if any(kind in node.type for kind in ('string', 'comment', 'char_literal', 'preproc_arg')):
            continue
        if node.children:
            pending.extend(node.children)
        elif node.text in spellings:
            replacement = spellings[node.text]
            result[node.start_byte:node.end_byte] = replacement.ljust(node.end_byte-node.start_byte, b' ')
    return bytes(result)


def conditional_compilation(data,root):
    """Keep every branch body when directives split expressions/initializers.

    This succeeds only if the combined source passes the complete grammar.
    Alternative bodies that cannot coexist syntactically remain unmeasured.
    """
    from bisect import bisect_right
    protected=[];pending=[root]
    while pending:
        node=pending.pop()
        if 'string' in node.type or 'comment' in node.type:protected.append((node.start_byte,node.end_byte))
        else:pending.extend(node.named_children)
    protected.sort();starts=[start for start,_ in protected];branches=[];depth=0
    def directive(match):
        nonlocal depth
        at=bisect_right(starts,match.start())-1
        if at>=0 and protected[at][1]>match.start():return match[0]
        kind=match[1]
        if kind in {b'if',b'elif'}:
            if kind==b'if':depth+=1
            elif not depth:raise ValueError('Unmatched conditional compilation alternative')
            line=data.count(b'\n',0,match.start())+1;branches.append(('preprocessor-'+kind.decode(),line))
            branches.extend(('short-circuit',line) for _ in re.finditer(rb'&&|\|\|',match[2]))
        elif kind==b'endif':
            depth-=1
            if depth<0:raise ValueError('Unmatched conditional compilation end')
        return re.sub(rb'[^\r\n]',b' ',match[0])
    result=re.sub(rb'(?m)^[ \t]*#(if|elif|else|endif)\b([^\r\n]*)',directive,data)
    if depth:raise ValueError('Unclosed conditional compilation block')
    return result,branches


def declaration_syntax(data):
    def spaces(match):
        return re.sub(rb"[^\r\n]", b" ", match.group())

    # Windows calling-convention modifiers decorate function declarations.
    data = re.sub(rb"\b(?:APIENTRY|CALLBACK|WINAPI|NTAPI|__cdecl|__stdcall|__fastcall|__vectorcall|_In_|_In_opt_|_Out_|_Out_opt_|_Inout_|_Inout_opt_)\b", spaces, data)
    # GCC assembler symbol names permit concatenated string-valued macros.
    # Only the declaration's string prefix is normalized, never asm bodies.
    data = re.sub(rb'(?<=__asm__\()[ \t]*[A-Z_][A-Z_0-9]*(?:[ \t]+[A-Z_][A-Z_0-9]*)*[ \t]+(?=")',spaces,data)
    # GLib type/registration macros contain declarations, not source statements.
    data = re.sub(rb"(?m)^[ \t]*G_(?:DECLARE_FINAL_TYPE|DECLARE_DERIVABLE_TYPE|DECLARE_INTERFACE|DEFINE_TYPE|DEFINE_TYPE_WITH_PRIVATE|DEFINE_INTERFACE)\([A-Za-z0-9_, \t\r\n:]+\)[ \t]*;?", spaces, data)
    # GLib automatic-cleanup type constructors. Keep the actual type token and
    # every byte after the type; runtime calls named similarly cannot match.
    pattern = rb"(?m)^(?P<prefix>[ \t]*(?:(?:const|static)[ \t]+)?)(?P<macro>g_auto(?:ptr|free)?)[ \t]*\([ \t]*(?P<type>[A-Za-z_][A-Za-z_0-9:]*)[ \t]*\)(?=[ \t]+[A-Za-z_][A-Za-z_0-9]*[ \t]*(?:=|;))"
    def type_token(match):
        replacement = bytearray(spaces(match))
        start = match.start("type") - match.start()
        replacement[start:start+len(match["type"])] = match["type"]
        return bytes(replacement)
    return re.sub(pattern, type_token, data)
