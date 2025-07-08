import streamlit as st
import fitz  # PyMuPDF
from email import policy
from email.parser import BytesParser
import pytesseract
from PIL import Image
import io
import difflib
import re

# PDF text and annotation extraction with cleaning
def extract_pdf_text_comments(pdf_file):
    pdf = fitz.open(stream=pdf_file.read(), filetype="pdf")
    comments = []
    full_text = ''

    for page in pdf:
        text = page.get_text()
        text = re.sub(r'\s+', ' ', text).strip()
        full_text += text
        annot = page.first_annot
        while annot:
            if annot.info["content"]:
                comments.append(annot.info["content"].strip())
            annot = annot.next

    return full_text, comments

# Email text and image extraction with cleaning
def extract_eml_content(eml_file):
    msg = BytesParser(policy=policy.default).parse(eml_file)

    text_content = ''
    images_text = ''

    for part in msg.walk():
        content_type = part.get_content_type()

        if content_type in ['text/plain', 'text/html']:
            text = part.get_content()
            text = re.sub(r'<[^>]+>', '', text)
            text_content += re.sub(r'\s+', ' ', text).strip()

        if content_type.startswith('image/'):
            image_data = part.get_payload(decode=True)
            image = Image.open(io.BytesIO(image_data))
            images_text += re.sub(r'\s+', ' ', pytesseract.image_to_string(image)).strip()

    return text_content, images_text

# Comparing cleaned PDF text to EML file content
def compare_texts(pdf_text, eml_text):
    seq_matcher = difflib.SequenceMatcher(None, pdf_text.lower(), eml_text.lower())
    match_ratio = seq_matcher.ratio()
    diff = [pdf_text[a:a+n] for op, a, b, i, n in seq_matcher.get_opcodes() if op != 'equal']
    overall_score = match_ratio * 100
    return overall_score, diff

# Comparing PDF comments to EML file content
def compare_comments_to_eml(comments, eml_text):
    results = []

    for comment in comments:
        match_ratio = difflib.SequenceMatcher(None, comment.lower(), eml_text.lower()).ratio()
        implemented = match_ratio > 0.6
        results.append((comment, implemented, match_ratio))

    return results

# Streamlit UI
st.title('Email Legal Review Comparison App')

# File uploaders
eml_file = st.file_uploader('Upload .eml File', type=['eml'])
pdf_file = st.file_uploader('Upload Legal Review PDF', type=['pdf'])

if eml_file and pdf_file:
    # Extracting content
    pdf_text, pdf_comments = extract_pdf_text_comments(pdf_file)
    eml_text, eml_images_text = extract_eml_content(eml_file)

    combined_eml_text = eml_text + " " + eml_images_text

    # Text comparison for match score and differences
    match_score, differences = compare_texts(pdf_text, combined_eml_text)

    # Comparison of comments implementation
    comparison_results = compare_comments_to_eml(pdf_comments, combined_eml_text)

    st.header("Comparison Results")
    st.metric("Overall Text Match Score (%)", f"{match_score:.2f}%")

    st.subheader("Text Differences")
    if differences:
        for diff in differences:
            st.warning(diff)
    else:
        st.success("No differences found!")

    st.subheader("Comments Not Implemented")
    for idx, (comment, implemented, ratio) in enumerate(comparison_results):
        if not implemented:
            st.error(f"❌ Comment {idx+1}: '{comment}' not implemented (Match ratio: {ratio:.2f})")

    st.subheader("Detailed Comment Check")
    for idx, (comment, implemented, ratio) in enumerate(comparison_results):
        status = "Implemented ✅" if implemented else "Not Implemented ❌"
        highlight = "🔴" if not implemented else "🟢"
        st.write(f"{highlight} Comment: {comment}")
        st.write(f"Status: {status} (Match ratio: {ratio:.2f})")
        st.divider()

    st.header("View PDF Content")
    st.text_area("PDF Text Content", pdf_text, height=200)

    st.header("View Extracted Email Text")
    st.text_area("Email Text Content", combined_eml_text, height=200)

else:
    st.warning('Please upload both .eml and PDF files to proceed.')
