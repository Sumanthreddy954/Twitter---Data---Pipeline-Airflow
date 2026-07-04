import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import tweepy

XQUIK_TWEET_SEARCH_URL = os.getenv(
    "XQUIK_TWEET_SEARCH_URL",
    "https://xquik.com/api/v1/x/tweets/search",
)
XQUIK_QUERY = os.getenv("XQUIK_QUERY", "from:elonmusk")
XQUIK_LIMIT = os.getenv("XQUIK_LIMIT", "200")
OUTPUT_CSV = os.getenv("TWITTER_OUTPUT_CSV", "refined_tweets.csv")
TWEET_COLUMNS = [
    "user",
    "text",
    "favorite_count",
    "retweet_count",
    "created_at",
]


def _tweet_text(tweet):
    return (
        tweet.get("text")
        or tweet.get("full_text")
        or tweet.get("content")
        or tweet.get("body")
        or ""
    )


def _tweet_author(tweet):
    author = tweet.get("author")
    if isinstance(author, dict):
        return author.get("username") or author.get("screen_name") or ""
    return tweet.get("user") or tweet.get("username") or ""


def _xquik_rows():
    api_key = os.getenv("XQUIK_API_KEY")
    if not api_key:
        return None

    query = urlencode({"q": XQUIK_QUERY, "limit": XQUIK_LIMIT})
    request = Request(
        f"{XQUIK_TWEET_SEARCH_URL}?{query}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("Xquik tweet search request failed") from exc

    return [
        {
            "user": _tweet_author(tweet),
            "text": _tweet_text(tweet),
            "favorite_count": tweet.get("like_count") or tweet.get("likeCount"),
            "retweet_count": tweet.get("retweet_count") or tweet.get("retweetCount"),
            "created_at": tweet.get("created_at") or tweet.get("createdAt"),
        }
        for tweet in payload.get("tweets", [])
    ]


def _required_twitter_credentials():
    credentials = {
        "TWITTER_CONSUMER_KEY": os.getenv("TWITTER_CONSUMER_KEY"),
        "TWITTER_CONSUMER_SECRET": os.getenv("TWITTER_CONSUMER_SECRET"),
        "TWITTER_ACCESS_TOKEN": os.getenv("TWITTER_ACCESS_TOKEN"),
        "TWITTER_ACCESS_SECRET": os.getenv("TWITTER_ACCESS_SECRET"),
    }
    missing = [name for name, value in credentials.items() if not value]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Set XQUIK_API_KEY or these Twitter API variables first: {joined}"
        )
    return credentials


def _tweepy_rows():
    credentials = _required_twitter_credentials()
    auth = tweepy.OAuthHandler(
        credentials["TWITTER_CONSUMER_KEY"],
        credentials["TWITTER_CONSUMER_SECRET"],
    )
    auth.set_access_token(
        credentials["TWITTER_ACCESS_TOKEN"],
        credentials["TWITTER_ACCESS_SECRET"],
    )
    api = tweepy.API(auth)
    screen_name = os.getenv("TWITTER_SCREEN_NAME", "elonmusk").lstrip("@")
    count = int(os.getenv("TWITTER_COUNT", "200"))
    tweets = api.user_timeline(
        screen_name=screen_name,
        count=count,
        include_rts=False,
        tweet_mode="extended",
    )

    rows = []
    for tweet in tweets:
        refined_tweet = {
            "user": tweet.user.screen_name,
            "text": tweet._json["full_text"],
            "favorite_count": tweet.favorite_count,
            "retweet_count": tweet.retweet_count,
            "created_at": tweet.created_at,
        }
        rows.append(refined_tweet)
    return rows


def run_twitter_etl():
    rows = _xquik_rows()
    if rows is None:
        rows = _tweepy_rows()

    df = pd.DataFrame(rows, columns=TWEET_COLUMNS)
    df.to_csv(OUTPUT_CSV, index=False)
