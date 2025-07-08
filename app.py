import streamlit as st
import fitz  # PyMuPDF
from email import policy
from email.parser import BytesParser
import pytesseract
from PIL import Image
import io
import difflib
import re
import pandas as pd
import openai

# Utility to clean and normalize text
def clean_text(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# Extract and clean PDF content
def extract_pdf_text_comments(pdf_file):
    pdf = fitz.open(stream=pdf_file.read(), filetype="pdf")
    comments = []
    full_text = ''
    urls = []

    for page in pdf:
        text = page.get_text()
        full_text += clean_text(text)
        urls += re.findall(r'https?://\S+', text)
        annot = page.first_annot
        while annot:
            if annot.info.get("content"):
                comments.append(annot.info["content"].strip())
            annot = annot.next

    return full_text, comments, urls

# Extract and clean EML content
def extract_eml_content(eml_file):
    msg = BytesParser(policy=policy.default).parse(eml_file)

    text_content = ''
    images_text = ''
    urls = []

    for part in msg.walk():
        content_type = part.get_content_type()

        if content_type in ['text/plain', 'text/html']:
            text = part.get_content()
            urls += re.findall(r'https?://\S+', text)
            text_content += clean_text(text)

        if content_type.startswith('image/'):
            image_data = part.get_payload(decode=True)
            image = Image.open(io.BytesIO(image_data))
            images_text += clean_text(pytesseract.image_to_string(image))

    return text_content, images_text, urls

# Structured comparison
def structured_differences(pdf_text, eml_text, pdf_urls, eml_urls):
    diffs = []
    sm = difflib.SequenceMatcher(None, pdf_text.lower(), eml_text.lower())
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != 'equal':
            diffs.append({
                'Type': 'Text',
                'Source': 'PDF',
                'Extracted': pdf_text[i1:i2],
                'Status': 'Not Found in Email'
            })
    for url in pdf_urls:
        if url not in eml_urls:
            diffs.append({
                'Type': 'URL',
                'Source': 'PDF',
                'Extracted': url,
                'Status': 'Missing in Email'
            })
    return diffs

# Check PDF comments
def compare_comments_to_eml(comments, eml_text):
    results = []
    for comment in comments:
        match_ratio = difflib.SequenceMatcher(None, comment.lower(), eml_text.lower()).ratio()
        implemented = match_ratio > 0.6
        results.append((comment, implemented, match_ratio))
    return results

# Use OpenAI API for semantic similarity
def semantic_similarity(pdf_text, eml_text, openai_key):
    openai.api_key = openai_key
    prompt = f"""Compare the following two texts for semantic similarity. Give a similarity score (0–100) and summarize major differences.

--- PDF Content ---\n{pdf_text[:3000]}

--- EML Content ---\n{eml_text[:3000]}"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        return f"OpenAI API Error: {e}"

# Streamlit UI
st.title('Email QA Proof vs Legal Comparision')

eml_file = st.file_uploader('Upload .eml File', type=['eml'])
pdf_file = st.file_uploader('Upload Legal Review PDF', type=['pdf'])
import os
openai_key = os.getenv("OPENAI_API_KEY")

if st.button('Submit'):
    if eml_file and pdf_file:
        pdf_text, pdf_comments, pdf_urls = extract_pdf_text_comments(pdf_file)
        eml_text, eml_images_text, eml_urls = extract_eml_content(eml_file)

        combined_eml_text = eml_text + " " + eml_images_text

        match_ratio = difflib.SequenceMatcher(None, pdf_text.lower(), combined_eml_text.lower()).ratio()
        match_score = match_ratio * 100

        differences = structured_differences(pdf_text, combined_eml_text, pdf_urls, eml_urls)
        comment_results = compare_comments_to_eml(pdf_comments, combined_eml_text)

        st.header("Comparison Results")
        st.metric("Basic Text Match Score (%)", f"{match_score:.2f}%")

        if openai_key:
            st.subheader("Semantic Match (via OpenAI GPT-4) - Using Env Key")
            semantic_result = semantic_similarity(pdf_text, combined_eml_text, openai_key)
            st.text_area("GPT-4 Comparison Result", semantic_result, height=250)

        st.subheader("Structured Differences")
        if differences:
            df = pd.DataFrame(differences)
            st.dataframe(df)
        else:
            st.success("No major content or URL differences found!")

        st.subheader("Comments Not Implemented")
        for idx, (comment, implemented, ratio) in enumerate(comment_results):
            if not implemented:
                st.error(f"❌ Comment {idx+1}: '{comment}' not implemented (Match ratio: {ratio:.2f})")

        st.subheader("Detailed Comment Check")
        for idx, (comment, implemented, ratio) in enumerate(comment_results):
            status = "Implemented ✅" if implemented else "Not Implemented ❌"
            st.write(f"{status}: {comment} (Match ratio: {ratio:.2f})")
            st.divider()

        st.header("PDF Text Content")
        st.text_area("Extracted PDF Text", pdf_text, height=150)

        st.header("Email Text Content")
        st.text_area("Extracted Email Text", combined_eml_text, height=150)
    else:
        st.warning('Please upload both .eml and PDF files to proceed.')
