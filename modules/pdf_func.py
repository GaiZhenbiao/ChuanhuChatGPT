from types import SimpleNamespace
import pdfplumber
import logging
from llama_index import Document

def prepare_table_config(crop_page):
    """Prepare table查找边界, 要求page为原始page
    
    From https://github.com/jsvine/pdfplumber/issues/242
    """
    page = crop_page.root_page # root/parent
    cs = page.curves + page.edges
    def curves_to_edges():
        """See https://github.com/jsvine/pdfplumber/issues/127"""
        edges = []
        for c in cs:
            edges += pdfplumber.utils.rect_to_edges(c)
        return edges
    edges = curves_to_edges()
    return {
        "vertical_strategy": "explicit",
        "horizontal_strategy": "explicit",
        "explicit_vertical_lines": edges,
        "explicit_horizontal_lines": edges,
        "intersection_y_tolerance": 10,
    }

def get_text_outside_table(crop_page):
    ts = prepare_table_config(crop_page)
    if len(ts["explicit_vertical_lines"]) == 0 or len(ts["explicit_horizontal_lines"]) == 0:
        return crop_page

    ### Get the bounding boxes of the tables on the page.
    bboxes = [table.bbox for table in crop_page.root_page.find_tables(table_settings=ts)]
    def not_within_bboxes(obj):
        """Check if the object is in any of the table's bbox."""
        def obj_in_bbox(_bbox):
            """See https://github.com/jsvine/pdfplumber/blob/stable/pdfplumber/table.py#L404"""
            v_mid = (obj["top"] + obj["bottom"]) / 2
            h_mid = (obj["x0"] + obj["x1"]) / 2
            x0, top, x1, bottom = _bbox
            return (h_mid >= x0) and (h_mid < x1) and (v_mid >= top) and (v_mid < bottom)
        return not any(obj_in_bbox(__bbox) for __bbox in bboxes)

    return crop_page.filter(not_within_bboxes)
# 请使用 LaTeX 表达公式，行内公式以 $ 包裹，行间公式以 $$ 包裹

extract_words = lambda page: page.extract_words(keep_blank_chars=True, y_tolerance=0, x_tolerance=1, extra_attrs=["fontname", "size", "object_type"])
# dict_keys(['text', 'x0', 'x1', 'top', 'doctop', 'bottom', 'upright', 'direction', 'fontname', 'size'])

def get_title_with_cropped_page(first_page):
    title = [] # 处理标题
    x0,top,x1,bottom = first_page.bbox # 获取页面边框

    for word in extract_words(first_page):
        word = SimpleNamespace(**word)

        if word.size >= 14:
            title.append(word.text)
            title_bottom = word.bottom
        elif word.text == "Abstract": # 获取页面abstract
            top = word.top
    
    user_info = [i["text"] for i in extract_words(first_page.within_bbox((x0,title_bottom,x1,top)))]
    # 裁剪掉上半部分, within_bbox: full_included; crop: partial_included
    return title, user_info, first_page.within_bbox((x0,top,x1,bottom))

def get_column_cropped_pages(pages, two_column=True):
    new_pages = []
    for page in pages:
        if two_column:
            left = page.within_bbox((0, 0, page.width/2, page.height),relative=True)
            right = page.within_bbox((page.width/2, 0, page.width, page.height), relative=True)
            new_pages.append(left)
            new_pages.append(right)
        else:
            new_pages.append(page)
    
    return new_pages

def parse_pdf(filename, two_column = True):
    level = logging.getLogger().level
    if level == logging.getLevelName("DEBUG"):
        logging.getLogger().setLevel("INFO")

    with pdfplumber.open(filename) as pdf:
        title, user_info, first_page = get_title_with_cropped_page(pdf.pages[0])
        new_pages = get_column_cropped_pages([first_page] + pdf.pages[1:], two_column)

        chapters = []
        # tuple (chapter_name, [pageid] (start,stop), chapter_text)
        create_chapter = lambda page_start,name_top,name_bottom: SimpleNamespace(
            name=[],
            name_top=name_top,
            name_bottom=name_bottom,
            record_chapter_name = True,
            
            page_start=page_start,
            page_stop=None,

            text=[],
        )
        cur_chapter = None

        # 按页遍历PDF文档
        for idx, page in enumerate(new_pages):
            page = get_text_outside_table(page)

            # 按行遍历页面文本
            for word in extract_words(page):
                word = SimpleNamespace(**word)

                # 检查行文本是否以12号字体打印，如果是，则将其作为新章节开始
                if word.size >= 11: # 出现chapter name
                    if cur_chapter is None:
                        cur_chapter = create_chapter(page.page_number, word.top, word.bottom)
                    elif not cur_chapter.record_chapter_name or (cur_chapter.name_bottom != cur_chapter.name_bottom and cur_chapter.name_top != cur_chapter.name_top): 
                        # 不再继续写chapter name
                        cur_chapter.page_stop = page.page_number # stop id
                        chapters.append(cur_chapter)
                        # 重置当前chapter信息
                        cur_chapter = create_chapter(page.page_number, word.top, word.bottom)

                    # print(word.size, word.top, word.bottom, word.text)
                    cur_chapter.name.append(word.text)
                else:
                    cur_chapter.record_chapter_name = False # chapter name 结束
                    cur_chapter.text.append(word.text)
        else:
            # 处理最后一个章节
            cur_chapter.page_stop = page.page_number # stop id
            chapters.append(cur_chapter)

        for i in chapters:
            logging.info(f"section: {i.name} pages:{i.page_start, i.page_stop} word-count:{len(i.text)}")
            logging.debug(" ".join(i.text))

    title = " ".join(title)
    user_info = " ".join(user_info)
    text = f"Article Title: {title}, Information:{user_info}\n"
    for idx, chapter in enumerate(chapters):
        chapter.name = " ".join(chapter.name)
        text += f"The {idx}th Chapter {chapter.name}: " + " ".join(chapter.text) + "\n"

    logging.getLogger().setLevel(level)
    return Document(text=text, extra_info={"title": title})

BASE_POINTS = """
1. Who are the authors?
2. What is the process of the proposed method?
3. What is the performance of the proposed method? Please note down its performance metrics.
4. What are the baseline models and their performances? Please note down these baseline methods.
5. What dataset did this paper use?
"""

READING_PROMPT = """
You are a researcher helper bot. You can help the user with research paper reading and summarizing. \n
Now I am going to send you a paper. You need to read it and summarize it for me part by part. \n
When you are reading, You need to focus on these key points:{}
"""

READING_PROMT_V2 = """
You are a researcher helper bot. You can help the user with research paper reading and summarizing. \n
Now I am going to send you a paper. You need to read it and summarize it for me part by part. \n
When you are reading, You need to focus on these key points:{},

And You need to generate a brief but informative title for this part.
Your return format:
- title: '...'
- summary: '...'
"""

SUMMARY_PROMPT = "You are a researcher helper bot. Now you need to read the summaries of a research paper."


if __name__ == '__main__':
    # Test code
    z = parse_pdf("./build/test.pdf")
    print(z["user_info"])
    print(z["title"])