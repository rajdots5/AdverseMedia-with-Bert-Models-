from googlenewsdecoder import gnewsdecoder
import trafilatura
import json
from observability import mark_span_error, traced_span

def scrape_article(google_news_url: str):
    """
    1. Google News ke URL ko decode karta hai.
    2. Trafilatura library ka use karke clean article text nikalta hai.
    """
    print(f"🔄 Decoding URL: {google_news_url[:60]}...")

    with traced_span("decode_google_news_url", "TOOL") as span:
        if span:
            span.set_attribute("input.value", json.dumps({"google_news_url": google_news_url}, ensure_ascii=True))
        try:
            decoded = gnewsdecoder(google_news_url)
            if decoded.get("status"):
                original_url = decoded["decoded_url"]
                decode_succeeded = True
                print(f"✅ Decoded to: {original_url}")
            else:
                print("⚠️ Decode fail hua, raw URL try kar rahe hain.")
                original_url = google_news_url
                decode_succeeded = False
        except Exception as error:
            print(f"⚠️ Decoding error: {error}")
            original_url = google_news_url
            decode_succeeded = False
            if span:
                mark_span_error(span, "url_decode", type(error).__name__)
        if span:
            span.set_attribute("url_decode.succeeded", decode_succeeded)
            span.set_attribute("decoded.url", original_url)
            span.set_attribute("output.value", json.dumps({"url": original_url, "decoded": decode_succeeded}, ensure_ascii=True))

    with traced_span("fetch_and_extract_article", "TOOL", {"article.url": original_url}) as span:
        if span:
            span.set_attribute("input.value", json.dumps({"url": original_url}, ensure_ascii=True))
        try:
            downloaded_html = trafilatura.fetch_url(original_url)
            if not downloaded_html:
                error = "Could not download page HTML."
                if span:
                    span.set_attribute("scrape.outcome", "empty_download")
                    mark_span_error(span, "article_download", "EmptyResponse")
                    span.set_attribute("output.value", json.dumps({"error": error}))
                return {"url": original_url, "text": "", "error": error}

            text = trafilatura.extract(downloaded_html)
            if not text:
                error = "No text extracted (Ho sakta hai page paywalled ho ya bot-blocker laga ho)"
                if span:
                    span.set_attribute("scrape.outcome", "empty_extraction")
                    span.set_attribute("scrape.html_characters", len(downloaded_html))
                    mark_span_error(span, "article_extraction", "EmptyExtraction")
                    span.set_attribute("output.value", json.dumps({
                        "error": error,
                        "downloaded_html": downloaded_html,
                        "html_characters": len(downloaded_html),
                    }, ensure_ascii=True))
                return {"url": original_url, "text": "", "error": error}

            if span:
                span.set_attribute("scrape.outcome", "success")
                span.set_attribute("scrape.html_characters", len(downloaded_html))
                span.set_attribute("scrape.article_characters", len(text))
                span.set_attribute("output.value", json.dumps({
                    "url": original_url,
                    "downloaded_html": downloaded_html,
                    "html_characters": len(downloaded_html),
                    "article_text": text,
                    "error": None,
                }, ensure_ascii=True))
            return {"url": original_url, "text": text, "error": None}
        except Exception as error:
            print(f"❌ Scraping error on {original_url}: {error}")
            if span:
                span.set_attribute("scrape.outcome", "exception")
                mark_span_error(span, "article_download_or_extraction", type(error).__name__)
                span.set_attribute("output.value", json.dumps({"error": str(error)}, ensure_ascii=True))
            return {"url": original_url, "text": "", "error": str(error)}

if __name__ == "__main__":
    # Test ke liye wahi LiveLaw wala URL le rahe hain
    test_url = "https://news.google.com/rss/articles/CBMi7AFBVV95cUxPRzFFaUF1SkNzbkE3Mk8zaEp5T3p4ekdsLXRnM2U1Y0Q2U3otckYtbTllWjdlQUpWa0NNYkVnNmxnVHlZRDVfQjJjZE5ZUkFEUjctSU5OcVlLRkRMNkI2X3NteW96YVRNUjM0VFhFWnRIT0NmMDEtNF9Zd2M5STJpT0tsdUlYZ0o2cnJPdDZOaUtZcndvak9aUVZDWC11MzBobWxpNmh4QzRnYnM1aWU0MndTSWtSMENaRDg5QVdPUjJyaXRjaDVCME51WW5RN1d3bVpuRFVLTDNSY0RxRVRneG5PZnNCU1pGWGlUY9IB7AFBVV95cUxPRzFFaUF1SkNzbkE3Mk8zaEp5T3p4ekdsLXRnM2U1Y0Q2U3otckYtbTllWjdlQUpWa0NNYkVnNmxnVHlZRDVfQjJjZE5ZUkFEUjctSU5OcVlLRkRMNkI2X3NteW96YVRNUjM0VFhFWnRIT0NmMDEtNF9Zd2M5STJpT0tsdUlYZ0o2cnJPdDZOaUtZcndvak9aUVZDWC11MzBobWxpNmh4QzRnYnM1aWU0MndTSWtSMENaRDg5QVdPUjJyaXRjaDVCME51WW5RN1d3bVpuRFVLTDNSY0RxRVRneG5PZnNCU1pGWGlUYw?oc=5"
    
    result = scrape_article(test_url)
    
    if not result["error"]:
        print("\n📄 --- EXTRACTED TEXT --- 📄\n")
        # Start ke 500 characters print kar rahe hain check karne ke liye
        print(result["text"][:500] + "...\n\n✅ (Text successfully scraped!)")
    else:
        print(f"\n❌ Failed: {result['error']}")

        