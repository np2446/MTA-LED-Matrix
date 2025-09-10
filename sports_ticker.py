#!/usr/bin/env python3
"""
Multi-Sport Ticker for LED Matrix
Displays MLB, NFL, and College Football scores with betting lines and logos

What changed:
- Added ESPN team logos next to team names (cached, small PNGs).
- Robust Odds API integration:
    * Verifies the API key with /v4/sports at startup.
    * Pulls h2h (moneyline) for LIVE games and spreads + totals for SCHEDULED games.
    * Picks a sane bookmaker automatically if multiple are present.
    * Graceful fallback to ESPN pregame odds when Odds API is unavailable or 401.
    * Caches odds responses briefly to avoid burning quota.
- Better team name matching between ESPN and The Odds API using token overlap.
- Safer error handling and clearer log messages with reasons and headers.
- Added sport filtering so you can choose which leagues to display.

References:
- The Odds API v4 docs: endpoints, params, and usage headers.
- Bookmaker keys by region.
"""

import requests
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont
import threading
from io import BytesIO
import urllib.parse
import re

from advanced_matrix_display import AdvancedMatrixDisplay, Layer

logger = logging.getLogger(__name__)

# --------------------------- Data Models ---------------------------

@dataclass
class Game:
    """Represents a sports game"""
    sport: str  # MLB, NFL, CFB
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    status: str  # LIVE, FINAL, SCHEDULED
    period: str  # Inning/Quarter/Time
    game_time: datetime
    # Display names from ESPN, useful for odds matching
    home_name: Optional[str] = None
    away_name: Optional[str] = None
    # Odds results
    home_ml: Optional[int] = None          # live ML
    away_ml: Optional[int] = None
    spread: Optional[float] = None         # pregame spread relative to HOME team
    over_under: Optional[float] = None     # pregame total
    odds_source: Optional[str] = None      # which bookmaker or 'ESPN fallback'

# --------------------------- Main Class ---------------------------

class SportsTicker:
    """Multi-sport ticker display"""

    # Team colors
    MLB_COLORS = {
        'ARI': (167, 25, 48), 'ATL': (206, 17, 65), 'BAL': (252, 76, 2),
        'BOS': (189, 48, 57), 'CHC': (14, 51, 134), 'CWS': (39, 37, 31),
        'CIN': (198, 1, 31), 'CLE': (227, 25, 55), 'COL': (51, 0, 114),
        'DET': (250, 70, 22), 'HOU': (235, 110, 31), 'KC': (0, 70, 135),
        'LAA': (186, 0, 33), 'LAD': (0, 90, 156), 'MIA': (0, 163, 224),
        'MIL': (18, 40, 75), 'MIN': (0, 43, 92), 'NYM': (0, 45, 114),
        'NYY': (0, 48, 135), 'OAK': (0, 56, 49), 'PHI': (232, 24, 40),
        'PIT': (253, 184, 39), 'SD': (47, 36, 29), 'SF': (253, 90, 30),
        'SEA': (12, 44, 86), 'STL': (196, 30, 58), 'TB': (143, 188, 230),
        'TEX': (0, 50, 120), 'TOR': (19, 74, 142), 'WSH': (171, 0, 3)
    }

    NFL_COLORS = {
        'ARI': (151, 35, 63), 'ATL': (167, 25, 48), 'BAL': (26, 25, 95),
        'BUF': (0, 51, 141), 'CAR': (0, 133, 202), 'CHI': (11, 22, 42),
        'CIN': (251, 79, 20), 'CLE': (49, 29, 0), 'DAL': (0, 34, 68),
        'DEN': (251, 79, 20), 'DET': (0, 118, 182), 'GB': (24, 48, 40),
        'HOU': (3, 32, 47), 'IND': (0, 44, 95), 'JAX': (0, 103, 120),
        'KC': (227, 24, 55), 'LAC': (0, 128, 198), 'LAR': (0, 53, 148),
        'LV': (165, 172, 175), 'MIA': (0, 142, 151), 'MIN': (79, 38, 131),
        'NE': (0, 34, 68), 'NO': (211, 188, 141), 'NYG': (1, 35, 82),
        'NYJ': (18, 87, 64), 'PHI': (0, 76, 84), 'PIT': (255, 182, 18),
        'SEA': (0, 34, 68), 'SF': (170, 0, 0), 'TB': (213, 10, 10),
        'TEN': (68, 149, 209), 'WAS': (90, 20, 20)
    }

    # Preferred bookmaker order
    BOOKMAKER_PRIORITY = [
        "draftkings", "fanduel", "espnbet", "betmgm",
        "caesars", "betrivers", "betonlineag", "bovada", "betus"
    ]

    # ESPN logo league path
    ESPN_LOGO_LEAGUE_PATH = {
        "MLB": "mlb",
        "NFL": "nfl",
        "CFB": None,  # school codes vary a lot
    }

    def __init__(self, display: AdvancedMatrixDisplay, odds_api_key: Optional[str] = None,
                 enabled_sports: Optional[List[str]] = None):
        self.display = display
        self.odds_api_key = odds_api_key
        self.games: List[Game] = []
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        self.scroll_speed = 1.5
        self.update_interval = 60
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.logo_cache: Dict[Tuple[str, str], Image.Image] = {}
        self.font_cache: Dict[str, ImageFont.FreeTypeFont] = {}

        # Sport filter
        default = {'MLB', 'NFL', 'CFB'}
        if enabled_sports:
            self.enabled_sports: Set[str] = {s.upper() for s in enabled_sports} & default
            if not self.enabled_sports:
                self.enabled_sports = set(default)
        else:
            self.enabled_sports = set(default)

        # Odds API state
        self.odds_key_valid = None  # None unknown, True ok, False invalid
        self._odds_cache: Dict[str, Tuple[float, dict]] = {}

    def set_enabled_sports(self, sports: List[str]):
        default = {'MLB', 'NFL', 'CFB'}
        sel = {s.upper() for s in sports} & default
        self.enabled_sports = sel if sel else default

    # --------------------------- Fetching ---------------------------

    def fetch_all_games(self) -> List[Game]:
        """Fetch games for the selected sports and enrich with odds if possible."""
        all_games: List[Game] = []

        if 'MLB' in self.enabled_sports:
            try:
                all_games.extend(self.fetch_espn_games('baseball', 'mlb', 'MLB'))
            except Exception as e:
                logger.error(f"Error fetching MLB: {e}")

        if 'NFL' in self.enabled_sports:
            try:
                all_games.extend(self.fetch_espn_games('football', 'nfl', 'NFL'))
            except Exception as e:
                logger.error(f"Error fetching NFL: {e}")

        if 'CFB' in self.enabled_sports:
            try:
                all_games.extend(self.fetch_espn_games('football', 'college-football', 'CFB'))
            except Exception as e:
                logger.error(f"Error fetching CFB: {e}")

        # Odds
        try:
            if self.odds_api_key:
                self.ensure_odds_key_valid()
            if self.odds_key_valid:
                self.apply_odds_from_oddsapi(all_games)
            else:
                self.apply_espn_pregame_fallback(all_games)
        except Exception as e:
            logger.error(f"Error applying odds - using ESPN fallback: {e}")
            self.apply_espn_pregame_fallback(all_games)

        # Sort
        def sort_key(game: Game):
            status_order = {'LIVE': 0, 'SCHEDULED': 1, 'FINAL': 2}
            sport_order = {'NFL': 0, 'CFB': 1, 'MLB': 2}
            return (status_order.get(game.status, 3), sport_order.get(game.sport, 3))

        all_games.sort(key=sort_key)
        logger.info(f"Fetched {len(all_games)} total games for sports {sorted(self.enabled_sports)}")
        return all_games

    def fetch_espn_games(self, sport_type: str, league: str, sport_label: str) -> List[Game]:
        """Fetch games from ESPN's public scoreboard JSON."""
        games: List[Game] = []
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_type}/{league}/scoreboard"
        params = {'groups': '80'} if league == 'college-football' else {}
        resp = self.session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for event in data.get('events', []):
            try:
                comp = event.get('competitions', [{}])[0]
                competitors = comp.get('competitors', [])
                if len(competitors) < 2:
                    continue
                home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                if not home or not away:
                    continue

                # Status
                status_info = event.get('status', {})
                status_type = status_info.get('type', {}).get('name', '')
                if status_type == 'STATUS_FINAL':
                    status = 'FINAL'
                    period = 'Final'
                elif status_type == 'STATUS_IN_PROGRESS':
                    status = 'LIVE'
                    period = status_info.get('type', {}).get('shortDetail', '') or status_info.get('type', {}).get('detail', '')
                else:
                    status = 'SCHEDULED'
                    game_time_utc = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
                    # crude ET conversion for display
                    month = game_time_utc.month
                    offset = timedelta(hours=-4) if 3 <= month <= 10 else timedelta(hours=-5)
                    game_time_et = game_time_utc + offset
                    period = game_time_et.strftime('%I:%M %p ET')

                def to_int(x):
                    try:
                        return int(x)
                    except:
                        return 0

                game = Game(
                    sport=sport_label,
                    home_team=home['team'].get('abbreviation', '').upper(),
                    away_team=away['team'].get('abbreviation', '').upper(),
                    home_score=to_int(home.get('score', 0)),
                    away_score=to_int(away.get('score', 0)),
                    status=status,
                    period=period,
                    game_time=datetime.fromisoformat(event['date'].replace('Z', '+00:00')),
                    home_name=home['team'].get('displayName'),
                    away_name=away['team'].get('displayName')
                )

                # ESPN pregame odds fallback
                odds_list = comp.get('odds', [])
                if odds_list:
                    o0 = odds_list[0]
                    spread_val = None
                    if 'spread' in o0:
                        try:
                            spread_val = float(o0['spread'])
                        except:
                            pass
                    if spread_val is None and isinstance(o0.get('details'), str):
                        m = re.search(r'([+-]?\d+(?:\.\d+)?)', o0['details'])
                        if m:
                            try:
                                spread_val = float(m.group(1))
                            except:
                                pass
                    if spread_val is not None:
                        det = str(o0.get('details', ''))
                        if det and game.home_team and game.home_team in det:
                            game.spread = spread_val
                        elif det and game.away_team and game.away_team in det:
                            game.spread = -spread_val
                        else:
                            game.spread = spread_val
                    try:
                        game.over_under = float(o0.get('overUnder'))
                    except:
                        pass
                    prov = o0.get('provider', {}).get('name')
                    if prov:
                        game.odds_source = f"ESPN:{prov}"

                games.append(game)
            except Exception as e:
                logger.error(f"Error parsing ESPN game: {e}")
                continue

        return games

    # --------------------------- Odds API Integration ---------------------------

    def ensure_odds_key_valid(self):
        """Ping /v4/sports to verify the Odds API key once."""
        if self.odds_key_valid is not None:
            return
        url = "https://api.the-odds-api.com/v4/sports/"
        try:
            r = self.session.get(url, params={"apiKey": self.odds_api_key}, timeout=8)
            if r.status_code == 200:
                self.odds_key_valid = True
                self._log_quota_headers(r.headers)
                logger.info("The Odds API key verified OK")
            else:
                self.odds_key_valid = False
                logger.error(f"Odds API key check failed: {r.status_code} {r.text[:200]}")
        except requests.HTTPError as e:
            self.odds_key_valid = False
            logger.error(f"Odds API key check HTTPError: {e}")
        except Exception as e:
            self.odds_key_valid = False
            logger.error(f"Odds API key check error: {e}")

    def apply_odds_from_oddsapi(self, games: List[Game]):
        """Fetch odds for each selected sport and merge into games."""
        sport_map = {
            'MLB': 'baseball_mlb',
            'NFL': 'americanfootball_nfl',
            'CFB': 'americanfootball_ncaaf'
        }

        games_by_sport: Dict[str, List[Game]] = {}
        for g in games:
            games_by_sport.setdefault(g.sport, []).append(g)

        for sport_label, list_games in games_by_sport.items():
            api_sport = sport_map.get(sport_label)
            if not api_sport:
                continue

            need_h2h = any(g.status == 'LIVE' for g in list_games)
            need_spreads_totals = any(g.status == 'SCHEDULED' for g in list_games)
            markets = []
            if need_h2h:
                markets.append('h2h')
            if need_spreads_totals:
                markets.extend(['spreads', 'totals'])
            if not markets:
                markets = ['spreads', 'totals']

            odds_json = self._get_odds_api_payload(api_sport, markets)
            if odds_json is None:
                logger.warning(f"No Odds API data for {sport_label}, using ESPN fallback")
                continue

            for event in odds_json:
                try:
                    ev_home = event.get('home_team', '')
                    ev_away = event.get('away_team', '')
                    ev_books = event.get('bookmakers', [])
                    if not ev_home or not ev_away or not ev_books:
                        continue

                    candidates = [g for g in list_games if self._event_matches_game(ev_home, ev_away, g)]
                    if not candidates:
                        continue

                    book = self._choose_bookmaker(ev_books)
                    if not book:
                        continue
                    markets_by_key = {m.get('key'): m for m in book.get('markets', [])}

                    for g in candidates:
                        if g.status == 'LIVE':
                            ml = markets_by_key.get('h2h')
                            if ml:
                                home_ml, away_ml = self._extract_moneyline(ml, g)
                                g.home_ml = home_ml if home_ml is not None else g.home_ml
                                g.away_ml = away_ml if away_ml is not None else g.away_ml
                                if home_ml is not None or away_ml is not None:
                                    g.odds_source = book.get('title') or book.get('key')

                        if g.status == 'SCHEDULED':
                            sp = markets_by_key.get('spreads')
                            to = markets_by_key.get('totals')
                            if sp:
                                sp_val = self._extract_home_spread(sp, g)
                                if sp_val is not None:
                                    g.spread = sp_val
                                    g.odds_source = g.odds_source or (book.get('title') or book.get('key'))
                            if to:
                                ou_val = self._extract_total(to)
                                if ou_val is not None:
                                    g.over_under = ou_val
                                    g.odds_source = g.odds_source or (book.get('title') or book.get('key'))
                except Exception as e:
                    logger.error(f"Error merging odds for {sport_label}: {e}")

    def _get_odds_api_payload(self, api_sport: str, markets: List[str]) -> Optional[List[dict]]:
        """Fetch and cache the odds payload for a sport."""
        cache_key = f"{api_sport}|{','.join(sorted(markets))}"
        now = time.time()
        if cache_key in self._odds_cache:
            ts, payload = self._odds_cache[cache_key]
            if now - ts < 45:
                return payload

        url = f"https://api.the-odds-api.com/v4/sports/{api_sport}/odds"
        params = {
            'apiKey': self.odds_api_key,
            'regions': 'us,us2',
            'markets': ','.join(markets),
            'oddsFormat': 'american',
            'dateFormat': 'iso'
        }
        try:
            r = self.session.get(url, params=params, timeout=10)
            if r.status_code == 200:
                self._log_quota_headers(r.headers)
                data = r.json()
                self._odds_cache[cache_key] = (now, data)
                return data
            elif r.status_code == 401:
                self.odds_key_valid = False
                logger.error("401 Unauthorized from The Odds API - check your apiKey and subscription status")
                logger.error(f"Endpoint: {url} Params: markets={params['markets']} regions={params['regions']}")
                return None
            else:
                logger.error(f"Odds API error {r.status_code}: {r.text[:200]}")
                return None
        except requests.HTTPError as e:
            logger.error(f"HTTPError fetching Odds API for {api_sport}: {e}")
        except Exception as e:
            logger.error(f"Error fetching odds for {api_sport}: {e}")
        return None

    def _log_quota_headers(self, headers: Dict[str, str]):
        try:
            used = headers.get('x-requests-used')
            remaining = headers.get('x-requests-remaining')
            last = headers.get('x-requests-last')
            if used or remaining or last:
                logger.info(f"Odds API quota - used:{used} remaining:{remaining} last_cost:{last}")
        except Exception:
            pass

    # --------------------------- ESPN Fallback ---------------------------

    def apply_espn_pregame_fallback(self, games: List[Game]):
        """Keep any spreads and totals parsed from ESPN when Odds API is unavailable."""
        return

    # --------------------------- Matching Helpers ---------------------------

    def _event_matches_game(self, ev_home: str, ev_away: str, g: Game) -> bool:
        """Loose token-based matching between Odds API event teams and our ESPN game."""
        def norm_tokens(s: str) -> set:
            s = s.lower()
            s = re.sub(r'[^a-z0-9 ]+', ' ', s)
            toks = set(t for t in s.split() if len(t) > 1)
            return toks

        g_home = g.home_name or g.home_team
        g_away = g.away_name or g.away_team

        t_ev_home = norm_tokens(ev_home)
        t_ev_away = norm_tokens(ev_away)
        t_g_home = norm_tokens(g_home)
        t_g_away = norm_tokens(g_away)

        overlap_home = len(t_ev_home & t_g_home)
        overlap_away = len(t_ev_away & t_g_away)

        ab_ok = (g.home_team.lower() in ev_home.lower() or ev_home.lower() in g.home_team.lower()) and \
                (g.away_team.lower() in ev_away.lower() or ev_away.lower() in g.away_team.lower())

        return ab_ok or (overlap_home >= 1 and overlap_away >= 1)

    def _choose_bookmaker(self, books: List[dict]) -> Optional[dict]:
        """Pick a bookmaker by priority, else return the first."""
        by_key = {b.get('key'): b for b in books if b.get('key')}
        for k in self.BOOKMAKER_PRIORITY:
            if k in by_key:
                return by_key[k]
        return books[0] if books else None

    def _extract_moneyline(self, ml_market: dict, g: Game) -> Tuple[Optional[int], Optional[int]]:
        """Return (home_ml, away_ml) from a 'h2h' market."""
        home_ml = None
        away_ml = None
        for outcome in ml_market.get('outcomes', []):
            name = outcome.get('name', '')
            price = outcome.get('price', None)
            if price is None:
                continue
            if self._name_refers_to_team(name, g.home_name, g.home_team):
                home_ml = int(price)
            elif self._name_refers_to_team(name, g.away_name, g.away_team):
                away_ml = int(price)
        return home_ml, away_ml

    def _extract_home_spread(self, sp_market: dict, g: Game) -> Optional[float]:
        """Return spread relative to HOME team from a 'spreads' market."""
        for outcome in sp_market.get('outcomes', []):
            name = outcome.get('name', '')
            point = outcome.get('point', None)
            if point is None:
                continue
            if self._name_refers_to_team(name, g.home_name, g.home_team):
                try:
                    return float(point)
                except:
                    pass
            if self._name_refers_to_team(name, g.away_name, g.away_team):
                try:
                    return float(-float(point))
                except:
                    pass
        return None

    def _extract_total(self, tot_market: dict) -> Optional[float]:
        """Return O/U total from a 'totals' market using the Over point."""
        for outcome in tot_market.get('outcomes', []):
            if str(outcome.get('name', '')).lower() == 'over':
                try:
                    return float(outcome.get('point'))
                except:
                    return None
        return None

    def _name_refers_to_team(self, name: str, display: Optional[str], abbr: Optional[str]) -> bool:
        name_l = name.lower()
        if abbr and abbr.lower() in name_l:
            return True
        if display:
            disp_tokens = re.sub(r'[^a-z0-9 ]+', ' ', display.lower()).split()
            return any(tok and tok in name_l for tok in disp_tokens)
        return False

    # --------------------------- Fonts & Logos ---------------------------

    def get_font(self, style: str = 'regular', size: int = 10) -> ImageFont.FreeTypeFont:
        """Get cached font."""
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

    def get_team_color(self, team: str, sport: str) -> Tuple[int, int, int]:
        """Get team color."""
        if sport == 'MLB':
            return self.MLB_COLORS.get(team, (150, 150, 150))
        elif sport == 'NFL':
            return self.NFL_COLORS.get(team, (150, 150, 150))
        else:
            return (100, 100, 100)

    def get_team_logo(self, team_abbr: str, sport: str, size: int = 20) -> Optional[Image.Image]:
        """Fetch and cache a small square team logo image."""
        cache_key = (sport, team_abbr.upper())
        if cache_key in self.logo_cache:
            return self.logo_cache[cache_key]

        league_path = self.ESPN_LOGO_LEAGUE_PATH.get(sport)
        if not league_path:
            return None

        ab = team_abbr.lower()
        url = "https://a.espncdn.com/combiner/i"
        params = {"img": f"/i/teamlogos/{league_path}/500/{ab}.png"}
        try:
            r = self.session.get(url, params=params, timeout=6)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            img = img.resize((size, size), Image.LANCZOS)
            self.logo_cache[cache_key] = img
            return img
        except Exception:
            self.logo_cache[cache_key] = None
            return None

    # --------------------------- Rendering ---------------------------

    def create_game_segment(self, game: Game) -> Image.Image:
        """Create visual segment for one game with logos and odds."""
        width = 280
        height = 32
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        sport_font = self.get_font('regular', 7)
        team_font = self.get_font('bold', 11)
        score_font = self.get_font('bold', 14)
        info_font = self.get_font('regular', 9)

        sport_colors = {'MLB': (200, 0, 0), 'NFL': (0, 100, 200), 'CFB': (128, 0, 128)}
        draw.text((5, 2), game.sport, fill=sport_colors.get(game.sport, (150, 150, 150)), font=sport_font)

        x = 35

        logo_size = 16
        away_logo = self.get_team_logo(game.away_team, game.sport, size=logo_size)
        home_logo = self.get_team_logo(game.home_team, game.sport, size=logo_size)
        if away_logo:
            img.paste(away_logo, (x, 1), away_logo)
        if home_logo:
            img.paste(home_logo, (x, 17), home_logo)

        x_text = x + (logo_size + 4)

        away_color = self.get_team_color(game.away_team, game.sport)
        draw.text((x_text, 1), game.away_team, fill=away_color, font=team_font)
        if game.status in ['LIVE', 'FINAL']:
            score_color = (255, 255, 255) if game.away_score > game.home_score else (150, 150, 150)
            draw.text((x_text + 42, 0), str(game.away_score), fill=score_color, font=score_font)

        home_color = self.get_team_color(game.home_team, game.sport)
        draw.text((x_text, 16), game.home_team, fill=home_color, font=team_font)
        if game.status in ['LIVE', 'FINAL']:
            score_color = (255, 255, 255) if game.home_score > game.away_score else (150, 150, 150)
            draw.text((x_text + 42, 15), str(game.home_score), fill=score_color, font=score_font)

        status_x = x_text + 70
        if game.status == 'LIVE':
            draw.ellipse([status_x, 10, status_x + 6, 16], fill=(255, 0, 0))
            draw.text((status_x + 10, 9), game.period, fill=(255, 255, 0), font=info_font)
            ml_x = status_x + 85
            if game.home_ml is not None or game.away_ml is not None:
                hm = f"H {game.home_ml:+d}" if game.home_ml is not None else ""
                am = f"A {game.away_ml:+d}" if game.away_ml is not None else ""
                draw.text((ml_x, 1), hm, fill=(200, 220, 255), font=info_font)
                draw.text((ml_x, 16), am, fill=(200, 220, 255), font=info_font)
        elif game.status == 'FINAL':
            draw.text((status_x, 9), 'FINAL', fill=(150, 150, 150), font=info_font)
        else:
            draw.text((status_x, 9), game.period, fill=(200, 200, 200), font=info_font)
            bet_x = status_x + 85
            if game.spread is not None:
                draw.text((bet_x, 2), f"{game.home_team} {game.spread:+.1f}", fill=(100, 200, 100), font=info_font)
            if game.over_under is not None:
                draw.text((bet_x, 17), f"O/U {game.over_under:.1f}", fill=(100, 200, 100), font=info_font)

        if game.odds_source:
            src = str(game.odds_source)
            src = src if len(src) <= 14 else src[:13]
            # draw.text((width - 58, 0), src, fill=(120, 120, 120), font=self.get_font('regular', 7))

        draw.line([(width - 2, 5), (width - 2, height - 5)], fill=(100, 100, 100), width=1)
        return img

    def create_ticker_image(self) -> Image.Image:
        """Create full ticker image."""
        if not self.games:
            img = Image.new('RGBA', (200, 32), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), "No games today", fill=(200, 200, 200),
                      font=self.get_font('regular', 12))
            return img

        segment_width = 280
        total_width = len(self.games) * segment_width + 120

        ticker = Image.new('RGBA', (total_width, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ticker)

        draw.text((10, 10), "SPORTS", fill=(255, 255, 255), font=self.get_font('bold', 12))
        draw.text((70, 11), "LIVE", fill=(255, 0, 0), font=self.get_font('bold', 10))

        x = 120
        for game in self.games[:30]:
            segment = self.create_game_segment(game)
            ticker.paste(segment, (x, 0), segment)
            x += segment_width

        return ticker

    # --------------------------- Run Loop ---------------------------

    def update_games(self):
        """Update games periodically."""
        while self.running:
            try:
                self.games = self.fetch_all_games()
                logger.info(f"Updated with {len(self.games)} games")
            except Exception as e:
                logger.error(f"Error updating games: {e}")
            time.sleep(self.update_interval)

    def start(self):
        """Start the ticker."""
        self.running = True
        self.update_thread = threading.Thread(target=self.update_games, daemon=True)
        self.update_thread.start()
        time.sleep(2)

        def scroll():
            while self.running:
                ticker_img = self.create_ticker_image()
                layer = Layer(ticker_img)
                self.display.clear()
                self.display.add_layer(layer)

                x = self.display.width
                while x > -ticker_img.width and self.running:
                    layer.x = int(x)
                    self.display.render()
                    x -= self.scroll_speed
                    time.sleep(1/30)
                time.sleep(0.5)

        self.display.start_animation(scroll)

    def stop(self):
        """Stop the ticker."""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=5)
        self.display.stop_animation()
        self.display.clear()