"""HTML fragments and Vue source retain inline code without rendering them."""
from dataclasses import replace
from html import unescape
from html.parser import HTMLParser
import re
from .models import BranchEvidence,FileMetric,FunctionMetric

VOID=set('area base br col embed hr img input link meta param source track wbr'.split())
ATTR=re.compile(r'''([^\s=<>/]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?''')


class Markup(HTMLParser):
    def __init__(self,text,base,analyze,vue=False,angular=False):
        super().__init__(convert_charrefs=False)
        self.text,self.base,self.analyze,self.vue=text,base,analyze,vue
        self.angular=angular or bool(re.search(r'\b(?:data-|x-)?ng-(?:app|controller|repeat|if)\s*=',text))
        self.functions=[];self.branches=[];self.structure=[];self.stack=[];self.active=None
        self.containers=0;self.depth=0;self.serial=0
        self.pending=[];self.pending_line=1;self.has_expressions=False

    def code(self,source,line,language='javascript',body=False,line_map=None):
        self.serial+=1
        prefix='function __handler__(){' if body else 'void('
        suffix='\n}' if body else ')'
        if language=='angular-expression' or self.angular and language=='handler':
            source=source.removeprefix('::')
            tokens=re.sub(r'"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27','',source)
            if re.search(r'(?<!\|)\|(?!\|)',tokens):raise ValueError('Angular filter syntax needs a validated expression reader')
            if re.search(r'\b(?:if|for|while|function|class|new|return|throw|try|switch|yield|await|let|const|var)\b|\?\.|\?\?|=>|\*\*|\.\.\.',tokens):raise ValueError('Unsupported Angular expression syntax')
        raw=source if language not in {'expression','angular-expression','handler'} else prefix+source+suffix
        parsed=self.analyze(raw.encode(),relative_path=self.base['path'],language='typescript' if language=='expression' else 'javascript' if language in {'handler','angular-expression'} else language)
        if parsed.parse_error:raise ValueError('Inline source syntax is not fully recognized')
        line_map=line_map or physical_lines(source,line)
        end=line_map[-1]
        def physical(at):return line_map[min(at-1,len(line_map)-1)]
        if language in {'expression','angular-expression'}:self.has_expressions=True
        for function in parsed.functions:
            result=replace(function,symbol=f'<inline:{self.serial}>/{function.symbol}',line=physical(function.line),
                end_line=physical(function.end_line),branches=tuple(replace(b,line=physical(b.line)) for b in function.branches))
            if language in {'expression','angular-expression'} and function.symbol=='<module>':self.branches.extend(result.branches)
            else:self.functions.append(result)

    def flush_text(self):
        if not self.pending:return
        data=''.join(self.pending);self.pending=[]
        if self.vue or self.angular:
            for match in re.finditer(r'{{([\s\S]*?)}}',data):
                line=self.pending_line+data.count('\n',0,match.start());source,positions=decode_source(match[1],line)
                self.code(source,line,'angular-expression' if self.angular else 'expression',line_map=positions)
            if '{{' in re.sub(r'{{[\s\S]*?}}','',data):raise ValueError('Unclosed template expression')
        elif '{{' in data or '{%' in data:raise ValueError('Inline template language is not identified')

    def handle_starttag(self,tag,attrs):
        self.flush_text()
        line=self.getpos()[0];self.containers+=1
        if self.stack:
            self.stack[-1]['children']+=1
            if self.stack[-1]['children']>8:self.structure.append(BranchEvidence('fanout-excess',line))
        if tag not in VOID:
            self.stack.append({'tag':tag,'children':0});depth=len(self.stack);self.depth=max(depth,self.depth)
            if depth>3:self.structure.append(BranchEvidence('nesting-excess',line,depth-3))
        attributes=dict(attrs)
        if tag in {'script','style'}:
            self.active={'tag':tag,'attributes':attributes,'source':[],'line':None};return
        raw=self.get_starttag_text()
        for match in list(ATTR.finditer(raw))[1:]:
            name,value=match.groups()
            if value is None:continue
            at_line=line+raw.count('\n',0,match.start(2))
            value,line_map=decode_source(value,at_line,quoted=True)
            if name.lower().startswith('on'):self.code(value,at_line,'handler',body=True,line_map=line_map)
            elif name.lower() in {'href','src','action','formaction','xlink:href'} and re.match(r'^\s*javascript:',value,re.I):
                prefix=re.match(r'^\s*javascript:',value,re.I).end()
                self.code(value[prefix:],at_line,'handler',body=True,line_map=line_map[value[:prefix].count('\n'):])
            elif self.vue and name in {'v-if','v-else-if','v-for'}:
                self.branches.append(BranchEvidence('vue-'+name,at_line))
                if name=='v-for':
                    parts=re.split(r'\s+(?:in|of)\s+',value,maxsplit=1)
                    if len(parts)!=2:raise ValueError('Invalid Vue loop expression')
                    value=parts[1]
                self.code(value,at_line,'expression',line_map=line_map)
            elif self.vue and (name.startswith((':','@','v-bind:','v-on:')) or name in {'v-show','v-model','v-text','v-html'}):
                self.code(value,at_line,'handler' if name.startswith(('@','v-on:')) else 'expression',body=name.startswith(('@','v-on:')),line_map=line_map)
            elif self.angular:
                directive=re.sub(r'^(?:data-|x-)?ng-','',name)
                if directive in {'repeat','if','switch-when'}:
                    self.branches.append(BranchEvidence('angular-'+directive,at_line))
                if directive=='repeat':
                    match=re.fullmatch(r'(?:[\w$]+|\([\w$]+\s*,\s*[\w$]+\))\s+in\s+(.+?)(?:\s+as\s+[\w$]+)?(?:\s+track\s+by\s+(.+))?',value)
                    if not match:raise ValueError('Unsupported Angular repeat expression')
                    self.code(match[1],at_line,'angular-expression',line_map=line_map)
                    if match[2]:self.code(match[2],at_line,'angular-expression',line_map=line_map)
                elif directive in {'click','change','submit','init','keydown','keyup','keypress','blur','focus','dblclick','mousedown','mouseup','mousemove','mouseenter','mouseleave','mouseover'} and name!=directive:
                    self.code(value,at_line,'handler',body=True,line_map=line_map)
                elif directive in {'if','show','hide','model','bind','bind-html','value','disabled','checked','readonly','selected','required','class','style','switch'} and name!=directive:
                    self.code(value,at_line,'angular-expression',line_map=line_map)
                else:
                    for expression in re.finditer(r'{{([\s\S]*?)}}',value):self.code(expression[1],at_line,'angular-expression',line_map=line_map)

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_endtag(self,tag):
        self.flush_text()
        if self.active and self.active['tag']==tag:
            active=self.active;self.active=None;source=''.join(active['source']);attrs=active['attributes'];line=active['line'] or self.getpos()[0]
            mime=(attrs.get('type') or '').split(';')[0].strip().lower()
            if source.strip() and 'src' not in attrs:
                if tag=='style':
                    language=attrs.get('lang','css')
                elif mime in {'application/json','application/ld+json','importmap','speculationrules'}:language='json'
                elif mime in {'text/x-template','text/html'}:
                    self.serial+=1;serial=self.serial
                    parsed=analyze_markup(source.encode(),self.base|{'lines':len(source.splitlines())},self.analyze,vue=not self.angular,angular=self.angular)
                    if parsed.parse_error:raise ValueError(parsed.parse_error)
                    self.functions.extend(replace(f,symbol=f'<template-script:{serial}>/{f.symbol}',line=f.line+line-1,end_line=f.end_line+line-1,
                        branches=tuple(replace(b,line=b.line+line-1) for b in f.branches)) for f in parsed.functions if parsed.metric_family=='control_flow')
                    language=None
                elif mime in {'','module','text/javascript','application/javascript','text/ecmascript','application/ecmascript','text/typescript'}:
                    language=attrs.get('lang','typescript' if mime=='text/typescript' else 'javascript')
                    language={'js':'javascript','ts':'typescript','jsx':'javascript'}.get(language,language)
                    if language not in {'javascript','typescript','tsx'}:raise ValueError('Inline script language is not supported')
                else:raise ValueError('Inline script language is not supported')
                if language:
                    parsed=self.analyze(source.encode(),relative_path=self.base['path'],language=language)
                    if parsed.parse_error:raise ValueError('Inline source syntax is not fully recognized')
                    if parsed.metric_family=='structure':
                        self.structure.extend(replace(b,line=b.line+line-1) for f in parsed.functions for b in f.branches)
                    if parsed.metric_family!='structure':
                        self.serial+=1;positions=physical_lines(source,line)
                        self.functions.extend(replace(f,symbol=f'<script:{self.serial}>/{f.symbol}',line=positions[min(f.line-1,len(positions)-1)],end_line=positions[min(f.end_line-1,len(positions)-1)],
                            branches=tuple(replace(b,line=positions[min(b.line-1,len(positions)-1)]) for b in f.branches)) for f in parsed.functions)
        for index in range(len(self.stack)-1,-1,-1):
            if self.stack[index]['tag']==tag:self.stack=self.stack[:index];break

    def handle_data(self,data):
        if self.active:
            if self.active['line'] is None:self.active['line']=self.getpos()[0]
            self.active['source'].append(data)
        else:
            if not self.pending:self.pending_line=self.getpos()[0]
            self.pending.append(data)

    def handle_entityref(self,name):self.handle_data('&'+name+';')
    def handle_charref(self,name):self.handle_data('&#'+name+';')
    def handle_comment(self,data):self.flush_text()
    def handle_decl(self,data):self.flush_text()
    def handle_pi(self,data):self.flush_text()


def decode_source(text,line,quoted=False):
    if quoted and text[:1] in {'"',"'"}:text=text[1:-1]
    text=text.replace('\r\n','\n').replace('\r','\n');positions=[line];pieces=[]
    for index,part in enumerate(re.split(r'(&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);?)',text)):
        decoded=unescape(part) if index%2 else part;pieces.append(decoded)
        for char in decoded:
            if char in '\n\r\u2028\u2029':
                if not index%2 and char in '\n\r':line+=1
                positions.append(line)
    return ''.join(pieces),positions


def physical_lines(source,line):
    positions=[line]
    for match in re.finditer(r'\r\n|[\r\n\u2028\u2029]',source):
        if match.group() not in {'\u2028','\u2029'}:line+=1
        positions.append(line)
    return positions


def analyze_markup(data,base,analyze,vue=False,angular=False):
    try:
        text=data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n');parser=Markup(text,base,analyze,vue,angular)
        if vue:
            from tree_sitter_language_pack import get_parser
            raw=text.encode();root=get_parser('vue').parse(raw).root_node;pending=[root];spans=[]
            while pending:
                node=pending.pop()
                if node.type=='interpolation':
                    source=raw[node.start_byte+2:node.end_byte-2].decode()
                    source,positions=decode_source(source,node.start_point.row+1)
                    parser.code(source,node.start_point.row+1,'expression',line_map=positions);spans.append((node.start_byte,node.end_byte))
                else:pending.extend(reversed(node.named_children))
            masked=bytearray(raw)
            for start,end in spans:masked[start:end]=re.sub(rb'[^\r\n]',b' ',raw[start:end])
            text=bytes(masked).decode()
        parser.feed(text);parser.close();parser.flush_text()
        if parser.active:parser.handle_endtag(parser.active['tag'])
        if parser.branches or parser.has_expressions:parser.functions.append(FunctionMetric('<template>',1,1,max(1,base['lines']),1+sum(b.contribution for b in parser.branches),tuple(parser.branches)))
        structural={'containers':parser.containers,'max_depth':parser.depth,
            'nesting_points':sum(b.contribution for b in parser.structure if b.kind=='nesting-excess'),
            'fanout_points':sum(b.contribution for b in parser.structure if b.kind=='fanout-excess')}
        if parser.functions:return FileMetric(**(base|{'metric_family':'control_flow'}),functions=tuple(parser.functions),structural=structural,structure_branches=tuple(parser.structure))
        return FileMetric(**(base|{'metric_family':'structure'}),functions=(FunctionMetric('<document>',1,1,max(1,base['lines']),1+sum(b.contribution for b in parser.structure),tuple(parser.structure)),),structural=structural)
    except (ValueError,UnicodeDecodeError) as exc:return FileMetric(**base,parse_error=str(exc))
