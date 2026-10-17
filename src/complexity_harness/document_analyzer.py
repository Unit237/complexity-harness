"""Syntax-aware diagnostics for CSS and OpenStep project documents."""
from importlib.metadata import version

from .models import BranchEvidence, FileMetric, FunctionMetric


def analyze_sql(data,base):
    try:
        import sqlglot
        from sqlglot import exp
        if version('sqlglot')!='30.23.0':raise ValueError('SQL parser differs from analysis contract')
        source=data.decode('utf-8-sig');trees=None
        for dialect in (None,'postgres','mysql','snowflake','tsql'):
            try:
                candidate=sqlglot.parse(source,read=dialect,error_level=sqlglot.ErrorLevel.RAISE)
                if any(tree and tree.find(exp.Command) for tree in candidate):continue
                trees=candidate;break
            except sqlglot.errors.ParseError:continue
        if trees is None:raise ValueError('Unsupported SQL dialect')
        branches=[];containers=depth=0
        for tree in trees:
            if tree is None:continue
            stack=[(tree,0)]
            while stack:
                node,level=stack.pop()
                if isinstance(node,(exp.Query,exp.Join,exp.CTE,exp.Case,exp.Subquery)):
                    level+=1;containers+=1;depth=max(depth,level)
                    line=min(max(1,base['lines']),node.meta.get('line',1))
                    if level>3:branches.append(BranchEvidence('nesting-excess',line,level-3))
                stack.extend((child,level) for child in node.iter_expressions())
        return FileMetric(**base,functions=(FunctionMetric('<document>',1,1,max(1,base['lines']),1+sum(b.contribution for b in branches),tuple(branches)),),structural={'containers':containers,'max_depth':depth,'nesting_points':sum(b.contribution for b in branches),'fanout_points':0})
    except Exception as exc:return FileMetric(**base,parse_error=f'SQL syntax unavailable: {type(exc).__name__}')


def analyze_configuration(data,base,language):
    """Real INI/XML readers handle optional newlines, continuation lines and BOMs."""
    try:
        if language=='config':
            import configparser
            parser=configparser.ConfigParser(interpolation=None,strict=False)
            parser.read_string('[DEFAULT]\n'+data.decode('utf-8-sig'))
            root={section:dict(parser[section]) for section in parser.sections()}
            root['DEFAULT']=dict(parser.defaults())
            pending=[(root,1)]
        else:
            import plistlib
            from xml.etree import ElementTree
            if data.startswith(b'bplist'):
                pending=[(plistlib.loads(data),1)]
            else:
                pending=[(ElementTree.fromstring(data),1)]
        depth=containers=0;branches=[]
        while pending:
            item,level=pending.pop()
            if isinstance(item,(dict,list)):
                children=[child for child in (item.values() if isinstance(item,dict) else item) if isinstance(child,(dict,list))]
            elif hasattr(item,'tag'):children=list(item)
            else:continue
            containers+=1;depth=max(depth,level)
            if level>3:branches.append(BranchEvidence('nesting-excess',1,level-3))
            if len(children)>8:branches.append(BranchEvidence('fanout-excess',1,len(children)-8))
            pending.extend((child,level+1) for child in children)
        unit=FunctionMetric('<document>',1,1,max(1,base['lines']),1+sum(b.contribution for b in branches),tuple(branches))
        return FileMetric(**base,functions=(unit,),structural={'containers':containers,'max_depth':depth,
            'nesting_points':sum(b.contribution for b in branches if b.kind=='nesting-excess'),
            'fanout_points':sum(b.contribution for b in branches if b.kind=='fanout-excess')})
    except Exception as exc:
        return FileMetric(**base,parse_error=f'Configuration syntax unavailable: {type(exc).__name__}')


def analyze_document(data, base, language):
    try:
        text = data.decode("utf-8-sig")
        if language == "css":
            import tinycss2
            if version("tinycss2") != "1.5.1":
                raise ValueError("CSS parser differs from the analysis contract")
            roots = tinycss2.parse_component_value_list(text, skip_comments=True)
            stack = [(node, 0) for node in reversed(roots)]
        else:
            from openstep_parser import OpenStepDecoder
            if version("openstep-parser") != "2.0.3":
                raise ValueError("OpenStep parser differs from the analysis contract")
            stack = [(OpenStepDecoder.ParseFromString(text), 0)]
        branches, containers, max_depth = [], 0, 0
        while stack:
            node, depth = stack.pop()
            if language == "css":
                if node.type == "error":
                    raise ValueError("Invalid CSS token")
                children = getattr(node, "content", None) or getattr(node, "arguments", None) or []
                container = node.type == "{} block"
                child_count = sum(child.type == "{} block" for child in children)
                line = node.source_line
            else:
                children = list(node.values()) if isinstance(node, dict) else node if isinstance(node, list) else []
                container = isinstance(node, (dict, list))
                child_count = sum(isinstance(child, (dict, list)) for child in children)
                line = 1  # OpenStep exposes document structure, not token locations.
            if container:
                depth += 1
                containers += 1
                max_depth = max(max_depth, depth)
                if depth > 3:
                    branches.append(BranchEvidence("nesting-excess", line, depth-3))
                if child_count > 8:
                    branches.append(BranchEvidence("fanout-excess", line, child_count-8))
            stack.extend((child, depth) for child in reversed(children))
        unit = FunctionMetric("<document>", 1, 1, max(1, base["lines"]),
            1+sum(b.contribution for b in branches), tuple(branches))
        return FileMetric(**base, functions=(unit,), structural={"containers":containers,"max_depth":max_depth,
            "nesting_points":sum(b.contribution for b in branches if b.kind=="nesting-excess"),
            "fanout_points":sum(b.contribution for b in branches if b.kind=="fanout-excess")})
    except Exception as exc:
        return FileMetric(**base, parse_error=f"Document analysis unavailable: {type(exc).__name__}")
