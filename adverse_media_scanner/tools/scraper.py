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
---------------------------------------------------------------------------------------------------------------------------------------------

# ============================================================
# SSL BYPASS FOR TCS CORPORATE NETWORK
# ============================================================
#
# IMPORTANT:
# This must be executed BEFORE importing googlenewsdecoder.
#
# Your TCS network is causing:
#
# SSL: CERTIFICATE_VERIFY_FAILED
# unable to get local issuer certificate
#
# The googlenewsdecoder package internally performs HTTPS
# requests and does not expose a verify=False option.
#
# This workaround disables certificate verification for the
# current Python process.
#
# For production, the proper solution is to configure the
# organization's trusted CA certificate.
# ============================================================

import ssl


# Save original SSL context function
_original_create_default_context = ssl.create_default_context


def insecure_create_default_context(*args, **kwargs):
    context = _original_create_default_context(*args, **kwargs)

    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    return context


# Patch SSL context
ssl.create_default_context = insecure_create_default_context


# ------------------------------------------------------------
# Patch SSLContext.wrap_socket
# ------------------------------------------------------------

_original_wrap_socket = ssl.SSLContext.wrap_socket


def insecure_wrap_socket(self, *args, **kwargs):

    self.check_hostname = False
    self.verify_mode = ssl.CERT_NONE

    return _original_wrap_socket(
        self,
        *args,
        **kwargs
    )


ssl.SSLContext.wrap_socket = insecure_wrap_socket


# ============================================================
# IMPORTS
# ============================================================

from googlenewsdecoder import gnewsdecoder

import trafilatura
import json

from observability import (
    mark_span_error,
    traced_span
)


# ============================================================
# SCRAPE ARTICLE
# ============================================================

def scrape_article(google_news_url: str):
    """
    Scrape an article from a Google News RSS URL.

    Flow:

        Google News URL
              ↓
        gnewsdecoder
              ↓
        Original publisher URL
              ↓
        Trafilatura
              ↓
        Clean article text

    The SSL workaround above is required for the current
    corporate/TCS network environment.
    """

    print(
        f"🔄 Decoding URL: "
        f"{google_news_url[:100]}..."
    )


    # ========================================================
    # STEP 1: GOOGLE NEWS URL DECODING
    # ========================================================

    with traced_span(
        "decode_google_news_url",
        "TOOL"
    ) as span:

        if span:

            span.set_attribute(
                "input.value",
                json.dumps(
                    {
                        "google_news_url": google_news_url
                    },
                    ensure_ascii=True
                )
            )

        try:

            decoded = gnewsdecoder(
                google_news_url
            )

            # ------------------------------------------------
            # IMPORTANT:
            # Your installed version returns:
            #
            # {
            #     "success": True,
            #     "decoded_url": "..."
            # }
            #
            # not necessarily:
            #
            # {
            #     "status": True,
            #     ...
            # }
            # ------------------------------------------------

            if (
                decoded
                and decoded.get("success")
                and decoded.get("decoded_url")
            ):

                original_url = decoded[
                    "decoded_url"
                ]

                decode_succeeded = True

                print(
                    f"✅ Decoded to: "
                    f"{original_url}"
                )

            else:

                print(
                    "⚠️ Decode failed, "
                    "raw URL try kar rahe hain."
                )

                print(
                    f"Decoder response: {decoded}"
                )

                original_url = google_news_url

                decode_succeeded = False


        except Exception as error:

            print(
                f"⚠️ Decoding error: {error}"
            )

            original_url = google_news_url

            decode_succeeded = False

            if span:

                mark_span_error(
                    span,
                    "url_decode",
                    type(error).__name__
                )


        # ----------------------------------------------------
        # Observability
        # ----------------------------------------------------

        if span:

            span.set_attribute(
                "url_decode.succeeded",
                decode_succeeded
            )

            span.set_attribute(
                "decoded.url",
                original_url
            )

            span.set_attribute(
                "output.value",
                json.dumps(
                    {
                        "url": original_url,
                        "decoded": decode_succeeded
                    },
                    ensure_ascii=True
                )
            )


    # ========================================================
    # STEP 2: DOWNLOAD + ARTICLE EXTRACTION
    # ========================================================

    with traced_span(
        "fetch_and_extract_article",
        "TOOL",
        {
            "article.url": original_url
        }
    ) as span:

        if span:

            span.set_attribute(
                "input.value",
                json.dumps(
                    {
                        "url": original_url
                    },
                    ensure_ascii=True
                )
            )

        try:

            print(
                f"🌐 Fetching article: "
                f"{original_url[:120]}"
            )


            # ------------------------------------------------
            # Download HTML using Trafilatura
            # ------------------------------------------------

            downloaded_html = (
                trafilatura.fetch_url(
                    original_url
                )
            )


            # ------------------------------------------------
            # Download failed
            # ------------------------------------------------

            if not downloaded_html:

                error = (
                    "Could not download page HTML."
                )

                print(
                    f"❌ {error}"
                )

                if span:

                    span.set_attribute(
                        "scrape.outcome",
                        "empty_download"
                    )

                    mark_span_error(
                        span,
                        "article_download",
                        "EmptyResponse"
                    )

                    span.set_attribute(
                        "output.value",
                        json.dumps(
                            {
                                "error": error
                            },
                            ensure_ascii=True
                        )
                    )

                return {
                    "url": original_url,
                    "text": "",
                    "error": error
                }


            # ------------------------------------------------
            # Extract article text
            # ------------------------------------------------

            print(
                "📝 Extracting article text..."
            )

            text = trafilatura.extract(
                downloaded_html
            )


            # ------------------------------------------------
            # Extraction failed
            # ------------------------------------------------

            if not text:

                error = (
                    "No text extracted "
                    "(Ho sakta hai page paywalled "
                    "ho ya bot-blocker laga ho)"
                )

                print(
                    f"⚠️ {error}"
                )

                if span:

                    span.set_attribute(
                        "scrape.outcome",
                        "empty_extraction"
                    )

                    span.set_attribute(
                        "scrape.html_characters",
                        len(downloaded_html)
                    )

                    mark_span_error(
                        span,
                        "article_extraction",
                        "EmptyExtraction"
                    )

                    span.set_attribute(
                        "output.value",
                        json.dumps(
                            {
                                "error": error,
                                "html_characters":
                                    len(downloaded_html)
                            },
                            ensure_ascii=True
                        )
                    )

                return {
                    "url": original_url,
                    "text": "",
                    "error": error
                }


            # =================================================
            # SUCCESS
            # =================================================

            print(
                f"✅ Article extracted successfully "
                f"({len(text)} characters)"
            )


            if span:

                span.set_attribute(
                    "scrape.outcome",
                    "success"
                )

                span.set_attribute(
                    "scrape.html_characters",
                    len(downloaded_html)
                )

                span.set_attribute(
                    "scrape.article_characters",
                    len(text)
                )

                span.set_attribute(
                    "output.value",
                    json.dumps(
                        {
                            "url": original_url,
                            "html_characters":
                                len(downloaded_html),
                            "article_characters":
                                len(text),
                            "error": None
                        },
                        ensure_ascii=True
                    )
                )


            return {
                "url": original_url,
                "text": text,
                "error": None
            }


        # ====================================================
        # EXCEPTION
        # ====================================================

        except Exception as error:

            print(
                f"❌ Scraping error on "
                f"{original_url}: {error}"
            )

            if span:

                span.set_attribute(
                    "scrape.outcome",
                    "exception"
                )

                mark_span_error(
                    span,
                    "article_download_or_extraction",
                    type(error).__name__
                )

                span.set_attribute(
                    "output.value",
                    json.dumps(
                        {
                            "error": str(error)
                        },
                        ensure_ascii=True
                    )
                )

            return {
                "url": original_url,
                "text": "",
                "error": str(error)
            }


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    # Same Google News URL that we successfully decoded
    # during our isolated decoder test.

    test_url = (
        "https://news.google.com/rss/articles/"
        "CBMi2wFBVV95cUxNNXhmUWd1MHRFUl93SHZKdWZGQU1a"
        "YzRnYTF2aTJUSllLNnFudDItME9NdnJSSkljLXM0UlZE"
        "c2s4ZDFCUE5xYno2ajZodTZ4a2RyTUJ1TW5iYk5wbTJEd"
        "2hIY2J1WXQ4dG50RDVPLTJ1MV8yRzR3d3U0a2VOR0hpLU"
        "ZQdE9sRFRURTRRamd6Yzk1MWtOM2YyZDlBZU9QYWZ1b21"
        "OcmlMcDAtaGtGNFl1TjNaV3pZemxZSmw4Ulpya3A4ZUtZ"
        "b3J5SDI4Z3E5dTNvVVBJU05GYWliTjTSAdsBQVVfeXFMT"
        "TV4ZlFndTB0RVJfd0h2SnVmRkFNWmM0Z2ExdmkyVEpZSz"
        "ZxbnQyLTBPTXZyUkpJYy1zNFJWRHNrOGQxQlBOcWJ6Nmo2"
        "aHU2eGtkck1CdU1uYmJOcG0yRHdoSGNidVl0OHRudEQ1Ty"
        "0ydTFfMkc0d3d1NGtlTkdIaS1GUHRPbERUVEU0UWpnemM5"
        "NTFrTjNmMmQ5QWVPUGFmdW9tTnJpTHAwLWhrRjRZdU4z"
        "Wld6WXpsWUpsOFJacmtwOGVLWW9yeUgyOGdxOXUzb1VQ"
        "SVNORmFpYk40?oc=5"
    )


    result = scrape_article(
        test_url
    )


    if not result["error"]:

        print(
            "\n📄 --- EXTRACTED TEXT --- 📄\n"
        )

        print(
            result["text"][:1000]
        )

        print(
            "\n...\n\n"
            "✅ Text successfully scraped!"
        )

    else:

        print(
            f"\n❌ Failed: "
            f"{result['error']}"
        )
        
