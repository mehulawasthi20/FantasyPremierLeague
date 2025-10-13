"""
Official Premier League Scout Selection Scraper

This module scrapes the official Premier League Scout Selection articles,
which provide the most authoritative FPL recommendations each gameweek.

The Scout Selection includes:
- Complete starting XI with formation
- Captain and Vice-Captain picks
- Detailed reasoning for each player

Usage:
    from fpl_scout_scraper import OfficialPremierLeagueScoutScraper
    
    # Provide the weekly Scout Selection URL
    scout_url = "https://www.premierleague.com/en/news/XXXXX/scout-selection-best-fantasy-team-for-gameweek-X"
    scraper = OfficialPremierLeagueScoutScraper(scout_url)
    recommendations = scraper.scrape_player_recommendations()
"""

import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional
from datetime import datetime
import time


class BaseFPLScraper:
    """
    Base class for FPL scrapers - minimal version for Scout scraper
    """
    
    def __init__(self, base_url: str, source_name: str):
        self.base_url = base_url
        self.source_name = source_name
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.delay = 2  # Seconds between requests
    
    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a webpage"""
        try:
            time.sleep(self.delay)
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def normalize_player_name(self, name: str) -> str:
        """Normalize player names for matching"""
        name = ' '.join(name.split())
        name = name.strip()
        return name


class OfficialPremierLeagueScoutScraper(BaseFPLScraper):
    """
    Scraper for Official Premier League Scout Selection
    
    The Scout Selection is published weekly (usually Wednesday/Thursday) and provides
    the official FPL recommended starting XI with captain and vice-captain picks.
    
    Args:
        scout_url: Full URL to the Scout Selection article for the current gameweek
                   Example: "https://www.premierleague.com/en/news/4431786/scout-selection-best-fantasy-team-for-gameweek-7"
    
    Attributes:
        scout_url: The URL of the Scout Selection article
        current_gameweek: Extracted gameweek number from the URL
    """
    
    def __init__(self, scout_url: str = None):
        super().__init__(
            base_url="https://www.premierleague.com",
            source_name="Official PL Scout Selection"
        )
        self.scout_url = scout_url
        self.current_gameweek = None
        
        # Extract gameweek from URL if possible
        if scout_url:
            gw_match = re.search(r'gameweek-(\d+)', scout_url.lower())
            if gw_match:
                self.current_gameweek = int(gw_match.group(1))
    
    def scrape_player_recommendations(self) -> List[Dict]:
        """
        Scrape the official Scout Selection team
        
        Returns:
            List of dictionaries containing player recommendations with:
            - source: "Official PL Scout Selection"
            - player_name: Player's name
            - recommendation_type: 'captain', 'essential', etc.
            - sentiment: Always 'positive' for Scout picks
            - article_title: Title with gameweek
            - article_url: URL of the Scout Selection
            - scraped_at: Timestamp
            - price: Player price (if available)
            - team: Team name (if available)
        """
        if not self.scout_url:
            print("    Warning: No Scout Selection URL provided. Skipping.")
            return []
        
        recommendations = []
        
        soup = self._fetch_page(self.scout_url)
        if not soup:
            print("    Error: Could not fetch Scout Selection page")
            return recommendations
        
        # Extract article content
        article = soup.find('article') or soup.find('div', class_=re.compile(r'article|content'))
        
        if not article:
            print("    Warning: Could not find article content")
            return recommendations
        
        text_content = article.get_text()
        
        # Extract captain
        captain_match = re.search(r'([\w\s]+)\s+earns?\s+the\s+armband', text_content, re.IGNORECASE)
        
        captain_name = None
        vice_captain_name = None
        
        if captain_match:
            captain_name = self.normalize_player_name(captain_match.group(1))
            print(f"    Found Captain: {captain_name}")
        
        # Find all player mentions with prices
        # Pattern: Player Name (Team) £X.Xm
        player_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+\(([^)]+)\)\s+£([\d.]+)m'
        player_matches = re.findall(player_pattern, text_content)
        
        print(f"    Found {len(player_matches)} players with prices")
        
        for player_name, team_name, price in player_matches:
            player_name = self.normalize_player_name(player_name)
            
            # Determine recommendation type
            rec_type = 'general'
            if captain_name and captain_name.lower() in player_name.lower():
                rec_type = 'captain'
            elif vice_captain_name and vice_captain_name.lower() in player_name.lower():
                rec_type = 'captain'  # Vice captain is also strong pick
            
            # All Scout Selection picks are essential (it's the official XI)
            if rec_type == 'general':
                rec_type = 'essential'
            
            recommendations.append({
                'source': self.source_name,
                'player_name': player_name,
                'recommendation_type': rec_type,
                'sentiment': 'positive',  # Scout Selection is always positive
                'article_title': f'Scout Selection GW{self.current_gameweek}' if self.current_gameweek else 'Scout Selection',
                'article_url': self.scout_url,
                'scraped_at': datetime.now().isoformat(),
                'price': float(price),
                'team': team_name
            })
        
        # Also extract player names from paragraph headers
        # Find paragraphs that describe each player
        paragraphs = article.find_all('p')
        
        for para in paragraphs:
            para_text = para.get_text()
            
            # Skip if too short
            if len(para_text) < 50:
                continue
            
            # Look for player names at start of paragraph
            first_line = para_text.split('\n')[0]
            potential_name = first_line.split('(')[0].strip()
            
            # Check if it looks like a player name (2-3 words, capitalized)
            words = potential_name.split()
            if 2 <= len(words) <= 3 and all(w[0].isupper() for w in words if w):
                player_name = self.normalize_player_name(potential_name)
                
                # Check if already added
                if not any(r['player_name'] == player_name for r in recommendations):
                    # Determine type from context
                    rec_type = 'essential'
                    if captain_name and captain_name.lower() in player_name.lower():
                        rec_type = 'captain'
                    
                    recommendations.append({
                        'source': self.source_name,
                        'player_name': player_name,
                        'recommendation_type': rec_type,
                        'sentiment': 'positive',
                        'article_title': f'Scout Selection GW{self.current_gameweek}' if self.current_gameweek else 'Scout Selection',
                        'article_url': self.scout_url,
                        'scraped_at': datetime.now().isoformat()
                    })
        
        print(f"    Total recommendations extracted: {len(recommendations)}")
        return recommendations
    
    def scrape_injury_news(self) -> List[Dict]:
        """
        Scout Selection doesn't typically contain injury news
        Players mentioned are expected to play
        
        Returns:
            Empty list (Scout Selection doesn't provide injury updates)
        """
        return []
    
    def scrape_expected_lineups(self) -> Dict[str, List[str]]:
        """
        Extract the Scout's recommended lineup
        
        Returns:
            Dictionary with key "Scout XI (GW#) - Formation" and list of player names
        """
        if not self.scout_url:
            return {}
        
        soup = self._fetch_page(self.scout_url)
        if not soup:
            return {}
        
        article = soup.find('article') or soup.find('div', class_=re.compile(r'article|content'))
        if not article:
            return {}
        
        text_content = article.get_text()
        
        # Extract formation
        formation_match = re.search(r'(\d-\d-\d)\s+formation', text_content)
        formation = formation_match.group(1) if formation_match else "Unknown"
        
        # Get all player names
        player_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+\([^)]+\)\s+£[\d.]+m'
        player_matches = re.findall(player_pattern, text_content)
        
        player_names = [self.normalize_player_name(name) for name in player_matches]
        
        if player_names:
            return {
                f'Scout XI (GW{self.current_gameweek}) - {formation}': player_names
            }
        
        return {}
    
    def get_scout_summary(self) -> Dict:
        """
        Get a summary of the Scout Selection
        
        Returns:
            Dictionary containing:
            - gameweek: Gameweek number
            - formation: Team formation
            - captain: Captain's name
            - vice_captain: Vice-captain's name
            - players_count: Number of players in XI
            - url: Article URL
        """
        if not self.scout_url:
            return {}
        
        soup = self._fetch_page(self.scout_url)
        if not soup:
            return {}
        
        article = soup.find('article') or soup.find('div', class_=re.compile(r'article|content'))
        if not article:
            return {}
        
        text_content = article.get_text()
        
        # Extract key information
        captain_match = re.search(r'([\w\s]+)\s+earns?\s+the\s+armband', text_content, re.IGNORECASE)
        vice_match = re.search(r'vice-captaincy?[:\s]+([\w\s]+)', text_content, re.IGNORECASE)
        formation_match = re.search(r'(\d-\d-\d)\s+formation', text_content)
        
        player_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+\([^)]+\)\s+£[\d.]+m'
        player_matches = re.findall(player_pattern, text_content)
        
        return {
            'gameweek': self.current_gameweek,
            'formation': formation_match.group(1) if formation_match else None,
            'captain': self.normalize_player_name(captain_match.group(1)) if captain_match else None,
            'vice_captain': self.normalize_player_name(vice_match.group(1)) if vice_match else None,
            'players_count': len(player_matches),
            'url': self.scout_url
        }


class OfficialPremierLeagueNewsScraper(BaseFPLScraper):
    """
    Auto-finder for Scout Selection articles
    
    Attempts to automatically find the latest Scout Selection article from
    the Premier League news page. Less reliable than providing the URL directly.
    """
    
    def __init__(self):
        super().__init__(
            base_url="https://www.premierleague.com",
            source_name="Official PL News"
        )
        self.news_url = f"{self.base_url}/news"
    
    def find_latest_scout_selection_url(self) -> Optional[str]:
        """
        Find the URL of the latest Scout Selection article
        
        Returns:
            URL string if found, None otherwise
        """
        soup = self._fetch_page(self.news_url)
        if not soup:
            return None
        
        # Look for Scout Selection links
        scout_links = soup.find_all('a', href=re.compile(r'scout-selection', re.IGNORECASE))
        
        for link in scout_links:
            href = link.get('href')
            if href:
                # Make absolute URL
                if not href.startswith('http'):
                    href = self.base_url + href
                
                # Check if it's recent (contains "gameweek")
                if 'gameweek' in href.lower():
                    return href
        
        return None
    
    def scrape_player_recommendations(self) -> List[Dict]:
        """
        Find and scrape latest Scout Selection automatically
        
        Returns:
            List of player recommendations from Scout Selection
        """
        scout_url = self.find_latest_scout_selection_url()
        
        if scout_url:
            print(f"    Auto-found Scout Selection: {scout_url}")
            # Use the dedicated scraper
            scout_scraper = OfficialPremierLeagueScoutScraper(scout_url)
            return scout_scraper.scrape_player_recommendations()
        else:
            print("    Could not auto-find latest Scout Selection")
            return []
    
    def scrape_injury_news(self) -> List[Dict]:
        """General PL news doesn't focus on injuries"""
        return []
    
    def scrape_expected_lineups(self) -> Dict[str, List[str]]:
        """Delegate to Scout Selection"""
        scout_url = self.find_latest_scout_selection_url()
        
        if scout_url:
            scout_scraper = OfficialPremierLeagueScoutScraper(scout_url)
            return scout_scraper.scrape_expected_lineups()
        
        return {}


# Example usage and testing
if __name__ == "__main__":
    print("Official Premier League Scout Selection Scraper")
    print("="*80)
    
    # Example: Scrape a specific Scout Selection
    SCOUT_URL = "https://www.premierleague.com/en/news/4431786/scout-selection-best-fantasy-team-for-gameweek-7"
    
    print(f"\nScraping Scout Selection from URL:")
    print(f"{SCOUT_URL}\n")
    
    scraper = OfficialPremierLeagueScoutScraper(scout_url=SCOUT_URL)
    
    # Get summary
    print("Scout Selection Summary:")
    print("-"*80)
    summary = scraper.get_scout_summary()
    print(f"Gameweek: {summary.get('gameweek')}")
    print(f"Formation: {summary.get('formation')}")
    print(f"Captain: {summary.get('captain')}")
    print(f"Vice-Captain: {summary.get('vice_captain')}")
    print(f"Players in XI: {summary.get('players_count')}")
    
    # Get recommendations
    print("\n\nPlayer Recommendations:")
    print("-"*80)
    recommendations = scraper.scrape_player_recommendations()
    
    if recommendations:
        # Group by type
        captains = [r for r in recommendations if r['recommendation_type'] == 'captain']
        essential = [r for r in recommendations if r['recommendation_type'] == 'essential']
        
        print(f"\nCaptain Picks ({len(captains)}):")
        for rec in captains:
            price = f"£{rec['price']}m" if 'price' in rec else ""
            team = f"({rec['team']})" if 'team' in rec else ""
            print(f"  - {rec['player_name']} {team} {price}")
        
        print(f"\nScout XI Players ({len(essential)}):")
        for rec in essential:
            price = f"£{rec['price']}m" if 'price' in rec else ""
            team = f"({rec['team']})" if 'team' in rec else ""
            print(f"  - {rec['player_name']} {team} {price}")
    else:
        print("No recommendations found")
    
    # Get lineup
    print("\n\nExpected Lineup:")
    print("-"*80)
    lineups = scraper.scrape_expected_lineups()
    for team_name, players in lineups.items():
        print(f"{team_name}:")
        for player in players:
            print(f"  - {player}")
    
    print("\n" + "="*80)
    print("Scraping complete!")
    
    # Example: Auto-find Scout Selection
    print("\n\nTrying to auto-find latest Scout Selection...")
    print("-"*80)
    auto_scraper = OfficialPremierLeagueNewsScraper()
    scout_url = auto_scraper.find_latest_scout_selection_url()
    
    if scout_url:
        print(f"Found: {scout_url}")
    else:
        print("Could not auto-find Scout Selection (this is expected)")
