"""Synthetic public demo PDFs; no personal or employer data."""
import pymupdf
def scanned_pdf():
    original=pymupdf.open();page=original.new_page(width=700,height=250)
    page.insert_text((30,70),"The experiment used 30 random seeds.",fontsize=20)
    page.insert_text((30,120),"Results were compared across all methods.",fontsize=20)
    image=page.get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False).tobytes("png")
    scan=pymupdf.open();page=scan.new_page(width=700,height=250);page.insert_image(page.rect,stream=image)
    return scan.tobytes()
def structured_pdf():
    doc=pymupdf.open();page=doc.new_page()
    for x in (50,200,350):page.draw_line((x,50),(x,150))
    for y in (50,100,150):page.draw_line((50,y),(350,y))
    for x,y,text in ((60,80,"Method"),(210,80,"Seeds"),(60,130,"Baseline"),(210,130,"30")):page.insert_text((x,y),text)
    page.insert_text((50,220),"f(x) = x + 1")
    page.insert_textbox(pymupdf.Rect(50,270,545,360),
        "The table reports the number of random seeds used by the baseline method. "
        "The expression above is a simple formula included to verify source-region "
        "rendering and structured extraction from a research document.",fontsize=11)
    return doc.tobytes()
