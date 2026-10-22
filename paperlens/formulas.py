"""Restricted symbolic parsing for simple extracted formulas; never evaluates source text."""
import ast,re,math
def parse_formula(text):
    text=text.strip().replace("\u2212","-").replace("\u00d7","*").replace("^","**")
    if len(text)>300:return {"parsed":False,"reason":"Formula is outside the small supported grammar."}
    count=0
    def convert(node,depth=0):
        nonlocal count
        count+=1
        if count>80 or depth>20:raise ValueError("Expression limit exceeded")
        if isinstance(node,ast.Name) and re.fullmatch(r"[^\W\d]\w{0,39}",node.id) and not node.id.startswith("_"):
            return {"type":"symbol","name":node.id},node.id.replace("_",r"\_")
        if isinstance(node,ast.Constant) and type(node.value) in (int,float) and len(str(node.value))<30 and math.isfinite(node.value):
            return {"type":"number","value":node.value},str(node.value)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value,latex=convert(node.operand,depth+1);sign="-" if isinstance(node.op,ast.USub) else "+"
            return {"type":"unary","operator":sign,"value":value},sign+"("+latex+")"
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow)):
            left,l=convert(node.left,depth+1);right,r=convert(node.right,depth+1)
            op={ast.Add:"+",ast.Sub:"-",ast.Mult:"*",ast.Div:"/",ast.Pow:"**"}[type(node.op)]
            latex={"+":f"({l})+({r})","-":f"({l})-({r})","*":f"({l})\\cdot({r})","/":f"\\frac{{{l}}}{{{r}}}","**":f"{{({l})}}^{{{r}}}"}[op]
            return {"type":"binary","operator":op,"left":left,"right":right},latex
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords and 1<=len(node.args)<=3:
            function,_=convert(node.func,depth+1);args=[convert(a,depth+1) for a in node.args]
            return {"type":"function","name":function["name"],"arguments":[a[0] for a in args]},function["name"]+r"\left("+",".join(a[1] for a in args)+r"\right)"
        raise ValueError("Unsupported formula syntax")
    try:
        parts=text.split("=")
        if len(parts)>2:raise ValueError("Multiple equalities")
        parsed=[convert(ast.parse(part.strip(),mode="eval").body) for part in parts]
        tree={"type":"equality","left":parsed[0][0],"right":parsed[1][0]} if len(parsed)==2 else parsed[0][0]
        return {"parsed":True,"expression":tree,"latex":" = ".join(p[1] for p in parsed),"scope":"Restricted symbolic structure; no numerical evaluation or guarantee about PDF/OCR fidelity."}
    except (ValueError,SyntaxError,RecursionError):
        return {"parsed":False,"reason":"Unsupported syntax; use the original source crop."}
