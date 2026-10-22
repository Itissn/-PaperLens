"""Bounded PDF OCR and structured inspection. Original PDF remains the source."""
import io,re,threading
import numpy as np
MAX_OCR_PAGES=30
_OCR=None
_LOCK=threading.Lock()
def ocr_image(image):
    global _OCR
    with _LOCK:
        if _OCR is None:
            from rapidocr_onnxruntime import RapidOCR
            _OCR=RapidOCR(intra_op_num_threads=4,inter_op_num_threads=1)
        result,_=_OCR(image)
    return [{"bbox":row[0],"text":row[1],"confidence":float(row[2])} for row in (result or []) if float(row[2])>=0.5]
def extract_pdf(data,ocr=False):
    import pymupdf
    pages=[];ocr_pages=0;characters=0
    with pymupdf.open(stream=data,filetype="pdf") as doc:
        if doc.is_encrypted:raise ValueError("Encrypted PDFs are not supported.")
        if not 0<len(doc)<=200:raise ValueError("PDF must contain 1-200 pages.")
        for page in doc:
            text=page.get_text(sort=True);method="text";confidence=None
            if len(text.strip())<40 and ocr and page.get_images():
                ocr_pages+=1
                if ocr_pages>MAX_OCR_PAGES:raise ValueError("OCR is limited to 30 pages per upload.")
                scale=min(2.0,1800/max(page.rect.width,page.rect.height))
                pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
                image=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
                lines=ocr_image(image)
                text="\n".join(line["text"] for line in lines);method="ocr"
                confidence=sum(x["confidence"] for x in lines)/len(lines) if lines else None
            characters+=len(text)
            if characters>2_000_000:raise ValueError("Extracted PDF text exceeds the limit.")
            pages.append({"page":page.number+1,"text":text,"method":method,"ocr_confidence":confidence})
    return pages
def inspect_page(data,number,ocr=False):
    import pymupdf
    with pymupdf.open(stream=data,filetype="pdf") as doc:
        if not 1<=number<=len(doc):raise ValueError("Unknown PDF page.")
        page=doc[number-1]
        blocks=[];formulas=[]
        for block in page.get_text("dict",sort=True)["blocks"]:
            if block["type"]!=0:continue
            for line in block["lines"]:
                text="".join(span["text"] for span in line["spans"]).strip()
                if not text:continue
                item={"text":text,"bbox":list(line["bbox"])}
                blocks.append(item)
                math_font=any(re.search("math|symbol|cmmi|cmsy",span.get("font",""),re.I) for span in line["spans"])
                if math_font or re.search(r"[=\u2211\u222b\u2264\u2265\u2208]",text):
                    from .formulas import parse_formula
                    formulas.append({**item,"kind":"formula_candidate","symbolic":parse_formula(text),"recognition":"Restricted symbolic parser plus original text/region; complex notation requires source review."})
        finder=page.find_tables()
        tables=[{"bbox":list(t.bbox),"rows":t.extract(),"method":"pdf_geometry"} for t in finder.tables]
        ocr_lines=[]
        if ocr:
            if page.rect.width*page.rect.height*4>16_000_000:raise ValueError("Page is too large for OCR inspection.")
            pix=page.get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False)
            if pix.width*pix.height>16_000_000:raise ValueError("Page is too large for OCR inspection.")
            image=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
            ocr_lines=ocr_image(image)
        return {"page":number,"width":page.rect.width,"height":page.rect.height,"blocks":blocks,"tables":tables,"formulas":formulas,"ocr_lines":ocr_lines,"limitations":"OCR confidence is not accuracy. Tables use PDF geometry; formulas use a restricted symbolic grammar and retain original regions. No mathematical verification."}
def render_region(data,number,bbox=None):
    import pymupdf
    with pymupdf.open(stream=data,filetype="pdf") as doc:
        if not 1<=number<=len(doc):raise ValueError("Unknown PDF page.")
        page=doc[number-1]
        clip=pymupdf.Rect(bbox) if bbox else page.rect
        clip=clip & page.rect
        if clip.is_empty:raise ValueError("Invalid page region.")
        scale=min(2.0,1600/max(clip.width,clip.height))
        return page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=clip,alpha=False).tobytes("png")
