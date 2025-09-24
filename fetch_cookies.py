import http.cookiejar
import urllib.request
from urllib.parse import urlencode


def fetch_cookies(url: str) -> http.cookiejar.CookieJar:
    """Send a GET request to the given URL and return collected cookies."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(url, timeout=10) as response:
        # Force reading the body so the request completes before we return cookies.
        response.read()
    return jar


def main() -> None:
    base_url = "https://www.realtor.com/"
    query = urlencode({"session": "sample-session"})
    url = f"{base_url}?{query}"
    cookies = fetch_cookies(url)
    if not cookies:
        print("No cookies were returned.")
        return

    print("Cookies from", url)
    for cookie in cookies:
        print(f"{cookie.name}={cookie.value}")


if __name__ == "__main__":
    main()
