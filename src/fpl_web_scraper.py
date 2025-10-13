import requests
from bs4 import BeautifulSoup
import pandas as pd
from typing import Dict, List, Optional
import time
import re
from abc import ABC, abstractmethod
from datetime import datetime
import json

class BaseFPLScraper(ABC):
    """
    TODO: ACTUAL IMPLEMENTATION OF SCRAPER. THIS IS A TEMPORARY BOILERPLATE IMPLEMENTATION
    Abstract base class for FPL website scrapers
    Provides common functionality and enforces consistent interface
    """
    
    def __init__(self, base_url: str, source_name: str):
        self.base_url = base_url
        self.source_name = source_name
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.delay = 2  # Seconds between requests (be respectful)
    
    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a webpage"""
        try:
            time.sleep(self.delay)  # Rate limiting
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    @abstractmethod
    def scrape_player_recommendations(self) -> List[Dict]:
        """Extract player recommendations from the website"""
        pass
    
    @abstractmethod
    def scrape_injury_news(self) -> List[Dict]:
        """Extract injury and availability news"""
        pass
    
    @abstractmethod
    def scrape_expected_lineups(self) -> Dict[str, List[str]]:
        """Extract expected/predicted lineups"""
        pass
    
    def normalize_player_name(self, name: str) -> str:
        """Normalize player names for matching"""
        # Remove extra whitespace, convert to title case
        name = ' '.join(name.split())
        name = name.strip()
        return name
    
    def extract_player_names_from_text(self, text: str) -> List[str]:
        """Extract potential player names from text using patterns"""
        # This is a simple implementation - can be enhanced with NLP
        # Look for capitalized words (likely names)
        potential_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        return [self.normalize_player_name(name) for name in potential_names]


class FantasyFootballScoutScraper(BaseFPLScraper):
    """
    Scraper for Fantasy Football Scout (fantasyfootballscout.co.uk)
    Extracts player recommendations, injury news, expected lineups, and odds
    """
    
    def __init__(self):
        super().__init__(
            base_url="https://www.fantasyfootballscout.co.uk",
            source_name="Fantasy Football Scout"
        )
        self.recommendations_url = f"{self.base_url}/fantasy-football-tips/"
        self.team_news_url = f"{self.base_url}/team-news/"
        self.lineups_url = f"{self.base_url}/predicted-lineups/"
    
    def scrape_player_recommendations(self) -> List[Dict]:
        """
        Scrape player recommendations from FFS articles
        Returns list of recommended players with context
        """
        recommendations = []
        
        # Try to get latest articles
        soup = self._fetch_page(self.recommendations_url)
        if not soup:
            return recommendations
        
        # Find article links (adjust selectors based on actual site structure)
        articles = soup.find_all('article', limit=5)  # Get top 5 articles
        
        for article in articles:
            try:
                # Extract article title and link
                title_elem = article.find(['h2', 'h3', 'a'])
                if not title_elem:
                    continue
                
                article_title = title_elem.get_text(strip=True)
                article_link = title_elem.get('href') if title_elem.name == 'a' else None
                
                if not article_link and title_elem.find('a'):
                    article_link = title_elem.find('a').get('href')
                
                # Make absolute URL
                if article_link and not article_link.startswith('http'):
                    article_link = self.base_url + article_link
                
                # Fetch article content
                if article_link:
                    article_soup = self._fetch_page(article_link)
                    if article_soup:
                        # Extract content
                        content = article_soup.find('article') or article_soup.find('div', class_='entry-content')
                        
                        if content:
                            text_content = content.get_text()
                            
                            # Extract player names (simple approach)
                            player_names = self.extract_player_names_from_text(text_content)
                            
                            # Determine recommendation type from title
                            rec_type = self._classify_recommendation_type(article_title)
                            
                            # Determine sentiment (positive/negative)
                            sentiment = self._analyze_sentiment(text_content)
                            
                            for player_name in player_names:
                                recommendations.append({
                                    'source': self.source_name,
                                    'player_name': player_name,
                                    'recommendation_type': rec_type,
                                    'sentiment': sentiment,
                                    'article_title': article_title,
                                    'article_url': article_link,
                                    'scraped_at': datetime.now().isoformat()
                                })
            
            except Exception as e:
                print(f"Error processing article: {e}")
                continue
        
        return recommendations
    
    def scrape_injury_news(self) -> List[Dict]:
        """
        Scrape injury and availability news
        """
        injury_news = []
        
        soup = self._fetch_page(self.team_news_url)
        if not soup:
            return injury_news
        
        # Look for team news sections
        news_items = soup.find_all(['article', 'div'], class_=re.compile(r'news|team|injury'))
        
        for item in news_items[:20]:  # Limit to recent items
            try:
                text = item.get_text()
                
                # Look for injury keywords
                injury_keywords = ['injury', 'doubt', 'suspended', 'banned', 'out', 'ruled out', 
                                 'fitness', 'unavailable', 'sidelined', 'red card']
                
                if any(keyword in text.lower() for keyword in injury_keywords):
                    # Extract player names
                    player_names = self.extract_player_names_from_text(text)
                    
                    for player_name in player_names:
                        # Determine status
                        status = 'unknown'
                        if 'ruled out' in text.lower() or 'out' in text.lower():
                            status = 'out'
                        elif 'doubt' in text.lower():
                            status = 'doubtful'
                        elif 'suspended' in text.lower() or 'banned' in text.lower():
                            status = 'suspended'
                        
                        injury_news.append({
                            'source': self.source_name,
                            'player_name': player_name,
                            'status': status,
                            'news_text': text[:200],  # First 200 chars
                            'scraped_at': datetime.now().isoformat()
                        })
            
            except Exception as e:
                print(f"Error processing injury news: {e}")
                continue
        
        return injury_news
    
    def scrape_expected_lineups(self) -> Dict[str, List[str]]:
        """
        Scrape predicted lineups for each team
        Returns dict with team_name: [list of expected starters]
        """
        lineups = {}
        
        soup = self._fetch_page(self.lineups_url)
        if not soup:
            return lineups
        
        # Look for team sections
        team_sections = soup.find_all(['div', 'section'], class_=re.compile(r'team|lineup'))
        
        for section in team_sections:
            try:
                # Extract team name
                team_header = section.find(['h2', 'h3', 'h4'])
                if not team_header:
                    continue
                
                team_name = team_header.get_text(strip=True)
                
                # Extract player names in lineup
                players_text = section.get_text()
                player_names = self.extract_player_names_from_text(players_text)
                
                lineups[team_name] = player_names
            
            except Exception as e:
                print(f"Error processing lineup: {e}")
                continue
        
        return lineups
    
    def scrape_bookies_odds(self) -> List[Dict]:
        """
        Scrape bookmaker odds for goals/assists/clean sheets
        Note: This would need to be adapted based on where FFS displays odds
        """
        odds_data = []
        
        # FFS may have odds in their stats/tips sections
        # This is a placeholder - actual implementation depends on their layout
        
        try:
            soup = self._fetch_page(self.base_url)
            if not soup:
                return odds_data
            
            # Look for odds-related content
            odds_sections = soup.find_all(text=re.compile(r'odds|bet|probability'))
            
            # Extract and parse odds data
            # This would need custom logic based on actual structure
            
        except Exception as e:
            print(f"Error scraping odds: {e}")
        
        return odds_data
    
    def _classify_recommendation_type(self, title: str) -> str:
        """Classify the type of recommendation based on article title"""
        title_lower = title.lower()
        
        if 'captain' in title_lower:
            return 'captain'
        elif 'differential' in title_lower:
            return 'differential'
        elif 'transfer' in title_lower:
            return 'transfer'
        elif 'budget' in title_lower or 'cheap' in title_lower:
            return 'budget'
        elif 'avoid' in title_lower:
            return 'avoid'
        elif 'must' in title_lower or 'essential' in title_lower:
            return 'essential'
        else:
            return 'general'
    
    def _analyze_sentiment(self, text: str) -> str:
        """Simple sentiment analysis (positive/negative/neutral)"""
        text_lower = text.lower()
        
        positive_words = ['recommend', 'great', 'excellent', 'best', 'strong', 'essential', 
                         'must-have', 'fantastic', 'form', 'fixture']
        negative_words = ['avoid', 'poor', 'doubt', 'injury', 'rotation', 'risk', 
                         'benched', 'dropped', 'concern']
        
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        if pos_count > neg_count * 1.5:
            return 'positive'
        elif neg_count > pos_count * 1.5:
            return 'negative'
        else:
            return 'neutral'


class ScraperAggregator:
    
    def __init__(self):
        self.scrapers = []
        self.player_data = {
            'recommendations': [],
            'injury_news': [],
            'lineups': {},
            'odds': []
        }
    
    def add_scraper(self, scraper: BaseFPLScraper):
        """Add a scraper to the aggregator"""
        self.scrapers.append(scraper)
    
    def scrape_all(self):
        """Run all scrapers and aggregate data"""
        print(f"\nScraping data from {len(self.scrapers)} source(s)...")
        
        for scraper in self.scrapers:
            print(f"\nScraping {scraper.source_name}...")
            
            # Recommendations
            print("  - Player recommendations...")
            try:
                recs = scraper.scrape_player_recommendations()
                self.player_data['recommendations'].extend(recs)
                print(f"    ✓ Found {len(recs)} recommendations")
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # Injury news
            print("  - Injury news...")
            try:
                injuries = scraper.scrape_injury_news()
                self.player_data['injury_news'].extend(injuries)
                print(f"    ✓ Found {len(injuries)} injury updates")
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # Expected lineups
            print("  - Expected lineups...")
            try:
                lineups = scraper.scrape_expected_lineups()
                self.player_data['lineups'].update(lineups)
                print(f"    ✓ Found {len(lineups)} team lineups")
            except Exception as e:
                print(f"    ✗ Error: {e}")
            
            # Odds (if available)
            if hasattr(scraper, 'scrape_bookies_odds'):
                print("  - Bookmaker odds...")
                try:
                    odds = scraper.scrape_bookies_odds()
                    self.player_data['odds'].extend(odds)
                    print(f"    ✓ Found {len(odds)} odds entries")
                except Exception as e:
                    print(f"    ✗ Error: {e}")
        
        self.scraped_at = datetime.now().isoformat()
        print(f"\nScraping completed at {self.scraped_at}")
    
    def get_player_consensus_score(self, player_name: str) -> Dict:
        """
        Calculate consensus score for a player based on all scraped data
        """
        recs_df = pd.DataFrame(self.player_data['recommendations'])
        
        if recs_df.empty:
            return {'consensus_score': 0, 'mention_count': 0, 'sentiment': 'neutral'}
        
        # Filter for this player
        player_recs = recs_df[recs_df['player_name'].str.contains(player_name, case=False, na=False)]
        
        if player_recs.empty:
            return {'consensus_score': 0, 'mention_count': 0, 'sentiment': 'neutral'}
        
        # Count mentions
        mention_count = len(player_recs)
        
        # Calculate sentiment score
        sentiment_scores = {'positive': 1, 'neutral': 0, 'negative': -1}
        avg_sentiment = player_recs['sentiment'].map(sentiment_scores).mean()
        
        # Type weights
        type_weights = {
            'captain': 3.0,
            'essential': 2.5,
            'transfer': 2.0,
            'differential': 1.5,
            'general': 1.0,
            'budget': 1.0,
            'avoid': -2.0
        }
        
        weighted_score = 0
        for _, rec in player_recs.iterrows():
            rec_type = rec['recommendation_type']
            weight = type_weights.get(rec_type, 1.0)
            sentiment_mult = sentiment_scores.get(rec['sentiment'], 0)
            weighted_score += weight * (sentiment_mult + 1)  # Make positive
        
        # Normalize
        consensus_score = weighted_score / max(mention_count, 1)
        
        overall_sentiment = 'positive' if avg_sentiment > 0.3 else ('negative' if avg_sentiment < -0.3 else 'neutral')
        
        return {
            'consensus_score': consensus_score,
            'mention_count': mention_count,
            'sentiment': overall_sentiment,
            'avg_sentiment': avg_sentiment
        }
    
    def get_injury_status(self, player_name: str) -> Optional[str]:
        """Get injury status for a player"""
        injuries_df = pd.DataFrame(self.player_data['injury_news'])
        
        if injuries_df.empty:
            return None
        
        player_injuries = injuries_df[injuries_df['player_name'].str.contains(player_name, case=False, na=False)]
        
        if player_injuries.empty:
            return None
        
        # Return most recent status
        return player_injuries.iloc[0]['status']
    
    def is_expected_to_start(self, player_name: str) -> bool:
        """Check if player is in expected lineups"""
        for team, players in self.player_data['lineups'].items():
            if any(player_name.lower() in p.lower() for p in players):
                return True
        return False
    
    def export_to_json(self, filename: str = 'fpl_scraped_data.json'):
        """Export scraped data to JSON"""
        with open(filename, 'w') as f:
            json.dump(self.player_data, f, indent=2)
        print(f"\nData exported to {filename}")
    
    def get_summary_dataframe(self) -> pd.DataFrame:
        """Get summary of all recommendations"""
        if not self.player_data['recommendations']:
            return pd.DataFrame()
        
        df = pd.DataFrame(self.player_data['recommendations'])
        
        # Aggregate by player
        summary = df.groupby('player_name').agg({
            'recommendation_type': lambda x: ', '.join(x.unique()),
            'sentiment': lambda x: x.mode()[0] if not x.empty else 'neutral',
            'player_name': 'count'
        }).rename(columns={'player_name': 'mention_count'})
        
        summary = summary.sort_values('mention_count', ascending=False)
        
        return summary


# Example usage
if __name__ == "__main__":
    print("FPL Web Scraper System")
    print("="*80)
    
    # Initialize aggregator
    aggregator = ScraperAggregator()
    
    # Add Fantasy Football Scout scraper
    ffs_scraper = FantasyFootballScoutScraper()
    aggregator.add_scraper(ffs_scraper)
    
    # Add more scrapers here in the future:
    # aggregator.add_scraper(FPLWireScraper())
    # aggregator.add_scraper(LetsTalkFPLScraper())
    
    # Scrape all sources
    aggregator.scrape_all()
    
    # Get summary
    print("\n" + "="*80)
    print("SCRAPING SUMMARY")
    print("="*80)
    
    summary_df = aggregator.get_summary_dataframe()
    if not summary_df.empty:
        print("\nTop Recommended Players:")
        print(summary_df.head(15))
    
    # Example: Get consensus for specific player
    print("\n" + "="*80)
    print("EXAMPLE: Player Consensus Analysis")
    print("="*80)
    
    test_player = "Salah"  # Example player
    consensus = aggregator.get_player_consensus_score(test_player)
    injury_status = aggregator.get_injury_status(test_player)
    expected_start = aggregator.is_expected_to_start(test_player)
    
    print(f"\nPlayer: {test_player}")
    print(f"Consensus Score: {consensus['consensus_score']:.2f}")
    print(f"Mentions: {consensus['mention_count']}")
    print(f"Sentiment: {consensus['sentiment']}")
    print(f"Injury Status: {injury_status or 'No issues'}")
    print(f"Expected to Start: {'Yes' if expected_start else 'Unknown'}")
    
    # Export data
    aggregator.export_to_json()
    
    print("\n" + "="*80)
    print("Scraping complete!")
    print("\nTo add more scrapers, create new classes inheriting from BaseFPLScraper")
    print("="*80)
