#!/usr/bin/env python3
"""
News Headlines Ticker for LED Matrix
Displays breaking news from major sources including Israeli news outlets
"""

import requests
import feedparser
import time
import logging
import calendar
import re
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont
import threading

from advanced_matrix_display import AdvancedMatrixDisplay, Layer

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


@dataclass
class Article:
    """Represents a news article"""
    title: str
    source: str
    source_id: str
    published: datetime
    description: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None


@dataclass
class NewsSource:
    """Configuration for a news source"""
    name: str
    source_id: str
    color: Tuple[int, int, int]
    rss_feed: Optional[str] = None


class NewsTicker:
    """News headlines ticker display"""

    # News sources configuration
    SOURCES = {
        'cnn': NewsSource(
            name='CNN',
            source_id='cnn',
            color=(204, 0, 0),
            rss_feed='http://rss.cnn.com/rss/cnn_topstories.rss'
        ),
        'bbc': NewsSource(
            name='BBC',
            source_id='bbc-news',
            color=(187, 25, 25),
            rss_feed='http://feeds.bbci.co.uk/news/rss.xml'
        ),
        'reuters': NewsSource(
            name='Reuters',
            source_id='reuters',
            color=(255, 102, 0),
            rss_feed='https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best'
        ),
        'ap': NewsSource(
            name='AP',
            source_id='associated-press',
            color=(255, 0, 0),
            rss_feed='https://feeds.apnews.com/rss/apf-topnews'
        ),
        'bloomberg': NewsSource(
            name='BBG',
            source_id='bloomberg',
            color=(0, 0, 0),
            rss_feed='https://feeds.bloomberg.com/markets/news.rss'
        ),
        'wsj': NewsSource(
            name='WSJ',
            source_id='the-wall-street-journal',
            color=(0, 0, 0),
            rss_feed='https://feeds.a.dj.com/rss/RSSWorldNews.xml'
        ),
        'guardian': NewsSource(
            name='Guardian',
            source_id='the-guardian',
            color=(0, 86, 137),
            rss_feed='https://www.theguardian.com/world/rss'
        ),
        'nytimes': NewsSource(
            name='NYT',
            source_id='the-new-york-times',
            color=(0, 0, 0),
            rss_feed='https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml'
        ),
        'foxnews': NewsSource(
            name='Fox',
            source_id='fox-news',
            color=(0, 51, 102),
            rss_feed='https://moxie.foxnews.com/google-publisher/latest.xml'
        ),
        'aljazeera': NewsSource(
            name='AJ',
            source_id='al-jazeera-english',
            color=(255, 152, 0),
            rss_feed='https://www.aljazeera.com/xml/rss/all.xml'
        ),
        'cnbc': NewsSource(
            name='CNBC',
            source_id='cnbc',
            color=(10, 87, 165),
            rss_feed='https://www.cnbc.com/id/100003114/device/rss/rss.html'
        ),
        'npr': NewsSource(
            name='NPR',
            source_id='npr',
            color=(227, 28, 35),
            rss_feed='https://feeds.npr.org/1001/rss.xml'
        ),
        'jpost': NewsSource(
            name='JPost',
            source_id='jerusalem-post',
            color=(0, 56, 168),
            rss_feed='https://www.jpost.com/rss/rssfeedsfrontpage.aspx'
        ),
        'haaretz': NewsSource(
            name='Haaretz',
            source_id='haaretz',
            color=(0, 113, 179),
            rss_feed='https://www.haaretz.com/cmlink/1.628765'
        ),
        'toi': NewsSource(
            name='TOI',
            source_id='times-of-israel',
            color=(0, 100, 164),
            rss_feed='https://www.timesofisrael.com/feed/'
        )
    }

    CATEGORY_COLORS = {
        'breaking': (255, 0, 0),
        'business': (0, 128, 0),
        'technology': (0, 123, 255),
        'politics': (148, 0, 211),
        'health': (255, 105, 180),
        'science': (0, 191, 255),
        'sports': (255, 165, 0),
        'entertainment': (255, 20, 147),
        'world': (70, 130, 180),
        'general': (128, 128, 128)
    }

    def __init__(self, display: AdvancedMatrixDisplay, news_api_key: Optional[str] = None):
        self.display = display
        self.news_api_key = news_api_key
        self.articles: List[Article] = []
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        self.scroll_speed = 1.2
        self.update_interval = 300  # 5 minutes
        self.breaking_only = False
        self.category_filter: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.font_cache: Dict[str, ImageFont.FreeTypeFont] = {}
        self.last_fetch: Dict[str, datetime] = {}

    def set_breaking_only(self, enabled: bool):
        """Toggle breaking news only mode"""
        self.breaking_only = enabled
        logger.info(f"Breaking news only: {enabled}")

    def set_category_filter(self, category: Optional[str]):
        """Set category filter"""
        self.category_filter = category
        logger.info(f"Category filter: {category}")

    def fetch_all_articles(self) -> List[Article]:
        """Fetch articles from all sources with timezone-aware datetimes"""
        all_articles: List[Article] = []

        # Fetch from NewsAPI if available
        if self.news_api_key:
            try:
                api_articles = self.fetch_newsapi()
                all_articles.extend(api_articles)
            except Exception as e:
                logger.error(f"Error fetching from NewsAPI: {e}")

        # Fetch from RSS feeds
        for source_id, source in self.SOURCES.items():
            if source.rss_feed:
                # Rate limit - only fetch every 5 minutes per source
                last = self.last_fetch.get(source_id, datetime.min.replace(tzinfo=timezone.utc))
                if now_utc() - last < timedelta(minutes=5):
                    continue

                try:
                    articles = self.fetch_rss(source_id, source)
                    all_articles.extend(articles)
                    self.last_fetch[source_id] = now_utc()
                except Exception as e:
                    logger.error(f"Error fetching {source.name} RSS: {e}")

                time.sleep(0.5)  # Small delay between feeds

        # Sort by published date (newest first)
        all_articles.sort(key=lambda x: x.published, reverse=True)

        # Remove duplicates based on title similarity
        unique: List[Article] = []
        seen_titles = set()

        for article in all_articles:
            normalized = re.sub(r'[^\w\s]', '', article.title.lower())
            normalized = ' '.join(normalized.split())

            if normalized not in seen_titles and len(normalized) > 10:
                unique.append(article)
                seen_titles.add(normalized)

        logger.info(f"Fetched {len(unique)} unique articles")
        return unique

    def fetch_newsapi(self) -> List[Article]:
        """Fetch articles from NewsAPI with UTC-aware timestamps"""
        articles: List[Article] = []

        url = 'https://newsapi.org/v2/top-headlines'
        params = {
            'apiKey': self.news_api_key,
            'language': 'en',
            'pageSize': 100
        }

        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        for item in data.get('articles', []):
            source_name = item.get('source', {}).get('name', 'Unknown') or 'Unknown'
            source_id = item.get('source', {}).get('id', 'unknown') or 'unknown'

            # Map to our configured sources if possible
            configured_source: Optional[str] = None
            for key, src in self.SOURCES.items():
                if src.source_id == source_id or (src.name and src.name in source_name):
                    configured_source = key
                    break

            if not configured_source:
                configured_source = 'general'

            published = now_utc()
            if item.get('publishedAt'):
                try:
                    # fromisoformat handles offset when Z is replaced
                    published = datetime.fromisoformat(
                        item['publishedAt'].replace('Z', '+00:00')
                    ).astimezone(timezone.utc)
                except Exception:
                    published = now_utc()

            article = Article(
                title=item.get('title', '') or '',
                source=source_name[:20],
                source_id=configured_source,
                published=published,
                description=item.get('description'),
                url=item.get('url')
            )
            articles.append(article)

        return articles

    def fetch_rss(self, source_id: str, source: NewsSource) -> List[Article]:
        """Fetch articles from RSS feed with UTC-aware timestamps"""
        articles: List[Article] = []

        feed = feedparser.parse(source.rss_feed)

        for entry in feed.entries[:20]:  # Limit to 20 latest
            # Default to now in UTC
            published = now_utc()

            # Prefer structured times
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                # struct_time is treated as UTC
                published = datetime.fromtimestamp(
                    calendar.timegm(entry.published_parsed),
                    tz=timezone.utc
                )
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published = datetime.fromtimestamp(
                    calendar.timegm(entry.updated_parsed),
                    tz=timezone.utc
                )
            else:
                # Try parsing RFC 2822 style strings
                date_str = entry.get('published') or entry.get('updated')
                if date_str:
                    try:
                        dt = parsedate_to_datetime(date_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        published = dt.astimezone(timezone.utc)
                    except Exception:
                        pass  # keep fallback

            # Clean HTML from text
            title = self.clean_html(entry.get('title', '') or '')
            description = self.clean_html(entry.get('summary', '') or '')

            article = Article(
                title=title,
                source=source.name,
                source_id=source_id,
                published=published,
                description=description,
                url=entry.get('link')
            )
            articles.append(article)

        return articles

    def clean_html(self, text: str) -> str:
        """Remove HTML tags from text"""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)

    def get_font(self, style: str = 'regular', size: int = 10) -> ImageFont.FreeTypeFont:
        """Get cached font"""
        key = f"{style}_{size}"
        if key not in self.font_cache:
            try:
                if style == 'bold':
                    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                else:
                    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                self.font_cache[key] = ImageFont.truetype(path, size)
            except Exception:
                self.font_cache[key] = ImageFont.load_default()
        return self.font_cache[key]

    def create_headline_segment(self, article: Article) -> Image.Image:
        """Create visual segment for one headline"""
        # Calculate width based on title length
        headline_font = self.get_font('regular', 11)

        test_img = Image.new('RGBA', (1, 1))
        test_draw = ImageDraw.Draw(test_img)
        bbox = test_draw.textbbox((0, 0), article.title, font=headline_font)
        text_width = bbox[2] - bbox[0]

        # Create segment
        width = text_width + 150
        height = 32

        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        x = 5

        # Draw source logo or name block
        source = self.SOURCES.get(article.source_id)
        if source:
            # Simple text logo
            logo_font = self.get_font('bold', 8)
            draw.rectangle([x, 8, x + 35, 24], fill=source.color)
            draw.text((x + 2, 10), source.name, fill=(255, 255, 255), font=logo_font)
            x += 40

        # Check if breaking (within last hour)
        seconds_since = (now_utc() - article.published).total_seconds()
        is_breaking = 0 <= seconds_since < 3600

        if is_breaking:
            # Breaking label
            breaking_font = self.get_font('bold', 8)
            draw.rectangle([x, 2, x + 50, 12], fill=(255, 0, 0))
            draw.text((x + 2, 2), "BREAKING", fill=(255, 255, 255), font=breaking_font)
            x += 55

        # Headline text
        draw.text((x, 10), article.title, fill=(255, 255, 255), font=headline_font)

        # Time ago
        time_ago = self.get_time_ago(article.published)
        time_font = self.get_font('regular', 7)
        draw.text((width - 50, 24), time_ago, fill=(150, 150, 150), font=time_font)

        # Category bar at bottom
        if article.category:
            color = self.CATEGORY_COLORS.get(
                article.category.lower(), self.CATEGORY_COLORS['general']
            )
            draw.rectangle([0, height - 2, width, height], fill=color)

        # Separator
        draw.line([(width - 2, 5), (width - 2, height - 5)], fill=(100, 100, 100), width=1)

        return img

    def get_time_ago(self, published: datetime) -> str:
        """Get human-readable time ago, safe for aware datetimes"""
        # Ensure aware UTC
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        delta = now_utc() - published
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "Just now"
        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        else:
            return f"{seconds // 86400}d ago"

    def create_ticker_image(self) -> Image.Image:
        """Create full ticker image"""
        if not self.articles:
            img = Image.new('RGBA', (300, 32), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), "Loading news...", fill=(200, 200, 200),
                      font=self.get_font('regular', 12))
            return img

        # Filter articles
        display_articles = self.articles

        if self.breaking_only:
            display_articles = [
                a for a in self.articles
                if 0 <= (now_utc() - a.published).total_seconds() < 3600
            ]

        if self.category_filter:
            display_articles = [
                a for a in display_articles
                if a.category and a.category.lower() == self.category_filter.lower()
            ]

        if not display_articles:
            display_articles = self.articles[:20]

        # Create segments
        segments: List[Image.Image] = []
        total_width = 100

        for article in display_articles[:50]:  # Limit to 50 headlines
            segment = self.create_headline_segment(article)
            segments.append(segment)
            total_width += segment.width

        # Create ticker
        ticker = Image.new('RGBA', (total_width, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ticker)

        # Header
        draw.rectangle([5, 10, 45, 22], fill=(255, 0, 0))
        draw.text((10, 10), "LIVE", fill=(255, 255, 255), font=self.get_font('bold', 10))
        draw.text((50, 11), "NEWS", fill=(200, 200, 200), font=self.get_font('regular', 10))

        # Add segments
        x = 100
        for segment in segments:
            ticker.paste(segment, (x, 0), segment)
            x += segment.width

        return ticker

    def update_articles(self):
        """Update articles periodically"""
        while self.running:
            try:
                self.articles = self.fetch_all_articles()
                logger.info(f"Updated with {len(self.articles)} articles")
            except Exception as e:
                logger.error(f"Error updating articles: {e}")

            time.sleep(self.update_interval)

    def start(self):
        """Start the ticker"""
        self.running = True

        # Start update thread
        self.update_thread = threading.Thread(target=self.update_articles, daemon=True)
        self.update_thread.start()

        # Initial fetch wait
        logger.info("Fetching initial headlines...")
        time.sleep(3)

        # Scrolling animation
        def scroll():
            while self.running:
                ticker_img = self.create_ticker_image()
                layer = Layer(ticker_img)

                self.display.clear()
                self.display.add_layer(layer)

                # Scroll left
                x = self.display.width
                while x > -ticker_img.width and self.running:
                    layer.x = int(x)
                    self.display.render()
                    x -= self.scroll_speed
                    time.sleep(1 / 30)

                time.sleep(0.5)

        self.display.start_animation(scroll)

    def stop(self):
        """Stop the ticker"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=5)
        self.display.stop_animation()
        self.display.clear()