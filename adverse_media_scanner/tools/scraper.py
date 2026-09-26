from googlenewsdecoder import gnewsdecoder
import trafilatura

def scrape_article(google_news_url: str):
    """
    1. Google News ke URL ko decode karta hai.
    2. Trafilatura library ka use karke clean article text nikalta hai.
    """
    print(f"🔄 Decoding URL: {google_news_url[:60]}...")
    
    # Step 1: URL Decode karna
    try:
        decoded = gnewsdecoder(google_news_url)
        if decoded.get("status"):
            original_url = decoded["decoded_url"]
            print(f"✅ Decoded to: {original_url}")
        else:
            print("⚠️ Decode fail hua, raw URL try kar rahe hain.")
            original_url = google_news_url
    except Exception as e:
        print(f"⚠️ Decoding error: {e}")
        original_url = google_news_url
        
    # Step 2: Actual Text Scrape karna using Trafilatura
    try:
        # Website ka HTML download karna
        downloaded_html = trafilatura.fetch_url(original_url)
        
        if not downloaded_html:
            return {"url": original_url, "text": "", "error": "Could not download page HTML."}
            
        # HTML se sirf actual news content nikalna (ads/menus hatakar)
        text = trafilatura.extract(downloaded_html)
        
        if not text:
            return {
                "url": original_url, 
                "text": "", 
                "error": "No text extracted (Ho sakta hai page paywalled ho ya bot-blocker laga ho)"
            }
            
        return {"url": original_url, "text": text, "error": None}
        
    except Exception as e:
        print(f"❌ Scraping error on {original_url}: {e}")
        return {"url": original_url, "text": "", "error": str(e)}

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

        