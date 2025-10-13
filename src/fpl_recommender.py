import requests
import pandas as pd
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime, timedelta
import time
import pickle
import os
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

class FPLRecommender:
    """
    Fantasy Premier League Transfer Recommendation System
    Analyzes your current team and suggests optimal transfers based on:
    - Fixture difficulty (current and upcoming)
    - Player form
    - Historical performance against opponents
    - Web consensus from expert sources
    - Budget constraints
    """
    
    def __init__(self, team_id: int, use_web_data: bool = True, cache_duration_hours: int = 6):
        self.base_url = "https://fantasy.premierleague.com/api/"
        self.team_id = team_id
        self.data = None
        self.players_df = None
        self.current_team = None
        self.budget = None
        self.free_transfers = None
        self.current_gameweek = None
        self.use_web_data = use_web_data
        self.web_aggregator = None
        self.cache_duration_hours = cache_duration_hours
        self.cache_dir = '.fpl_cache'
        
        # Create cache directory
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def _get_cache_path(self, cache_type: str) -> str:
        """Get cache file path"""
        return os.path.join(self.cache_dir, f'{cache_type}_{self.team_id}.pkl')
    
    def _is_cache_valid(self, cache_path: str) -> bool:
        """Check if cache file exists and is still valid"""
        if not os.path.exists(cache_path):
            return False
        
        file_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
        age = datetime.now() - file_time
        
        return age < timedelta(hours=self.cache_duration_hours)
    
    def _save_cache(self, cache_type: str, data: any):
        """Save data to cache"""
        cache_path = self._get_cache_path(cache_type)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            print(f"  ✓ Cached {cache_type}")
        except Exception as e:
            print(f"  ✗ Cache save failed for {cache_type}: {e}")
    
    def _load_cache(self, cache_type: str) -> Optional[any]:
        """Load data from cache"""
        cache_path = self._get_cache_path(cache_type)
        
        if not self._is_cache_valid(cache_path):
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            print(f"  ✓ Loaded {cache_type} from cache")
            return data
        except Exception as e:
            print(f"  ✗ Cache load failed for {cache_type}: {e}")
            return None
    
    def clear_cache(self):
        """Clear all cached data"""
        import glob
        cache_files = glob.glob(os.path.join(self.cache_dir, '*.pkl'))
        for file in cache_files:
            try:
                os.remove(file)
                print(f"Removed cache: {file}")
            except:
                pass
        print("Cache cleared!")
    
    def fetch_fpl_data(self, use_cache: bool = True) -> Dict:
        """Fetch current season data from FPL API with caching"""
        if use_cache:
            cached_data = self._load_cache('fpl_data')
            if cached_data:
                self.data = cached_data
                self.current_gameweek = next(
                    (gw['id'] for gw in self.data['events'] if gw['is_current']), 
                    next((gw['id'] for gw in self.data['events'] if gw['is_next']), 1)
                )
                return self.data
        
        try:
            print("  Fetching fresh FPL data from API...")
            response = requests.get(f"{self.base_url}bootstrap-static/")
            response.raise_for_status()
            self.data = response.json()
            
            self.current_gameweek = next(
                (gw['id'] for gw in self.data['events'] if gw['is_next']),
                None
            )
            if not self.current_gameweek:
                self.current_gameweek = next(
                    (gw['id'] for gw in self.data['events'] if gw['is_next']), 
                    1
                )
            
            # Fetch fixtures separately
            print("  Fetching fixtures data...")
            fixtures_response = requests.get(f"{self.base_url}fixtures/")
            fixtures_response.raise_for_status()
            self.data['fixtures'] = fixtures_response.json()
            
            if use_cache:
                self._save_cache('fpl_data', self.data)
            
            return self.data
        except requests.exceptions.RequestException as e:
            print(f"Error fetching FPL data: {e}")
            return None
    
    def fetch_my_team(self, use_cache: bool = True) -> Dict:
        """Fetch user's current team data with caching"""
        if use_cache:
            cached_team = self._load_cache('my_team')
            if cached_team:
                self.current_team = cached_team
                self.budget = cached_team['budget']
                self.free_transfers = cached_team['free_transfers']
                return self.current_team
        
        try:
            print("  Fetching fresh team data from API...")
            response = requests.get(f"{self.base_url}entry/{self.team_id}/")
            response.raise_for_status()
            team_data = response.json()
            
            picks_response = requests.get(
                f"{self.base_url}entry/{self.team_id}/event/{self.current_gameweek}/picks/"
            )
            picks_response.raise_for_status()
            picks_data = picks_response.json()
            
            self.budget = picks_data['entry_history']['bank'] / 10
            self.free_transfers = picks_data['entry_history']['event_transfers_cost']
            
            current_squad_ids = [pick['element'] for pick in picks_data['picks']]
            
            self.current_team = {
                'info': team_data,
                'picks': picks_data,
                'squad_ids': current_squad_ids,
                'budget': self.budget,
                'free_transfers': self.free_transfers
            }
            
            if use_cache:
                self._save_cache('my_team', self.current_team)
            
            return self.current_team
        except requests.exceptions.RequestException as e:
            print(f"Error fetching team data: {e}")
            return None
    
    def get_fixtures_for_gameweek(self, gameweek: int = None) -> List[Dict]:
        """Get fixtures for a specific gameweek"""
        if gameweek is None:
            gameweek = self.current_gameweek
        
        if not self.data or 'fixtures' not in self.data:
            print("Warning: Fixtures data not available")
            return []
        
        return [f for f in self.data['fixtures'] if f['event'] == gameweek]
    
    def prepare_players_dataframe(self) -> pd.DataFrame:
        """Convert API data to pandas DataFrame"""
        if not self.data:
            self.fetch_fpl_data()
        
        players = self.data['elements']
        teams = {team['id']: team['name'] for team in self.data['teams']}
        
        position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        
        df = pd.DataFrame(players)
        df['position_name'] = df['element_type'].map(position_map)
        df['team_name'] = df['team'].map(teams)
        df['full_name'] = df['first_name'] + ' ' + df['second_name']
        df['web_name_clean'] = df['web_name'].str.strip()
        df['value'] = df['now_cost'] / 10
        df['form_numeric'] = pd.to_numeric(df['form'], errors='coerce')
        df['selected_by_percent_numeric'] = pd.to_numeric(df['selected_by_percent'], errors='coerce')
        df['ict_index_numeric'] = pd.to_numeric(df['ict_index'], errors='coerce')
        
        self.players_df = df
        return df
    
    def fuzzy_match_player(self, scraped_name: str, threshold: int = 80) -> Optional[pd.Series]:
        """
        Use fuzzy matching to find player in FPL database
        Returns player row if match found above threshold
        """
        if self.players_df is None:
            self.prepare_players_dataframe()
        
        # Try exact match first
        exact_match = self.players_df[
            (self.players_df['full_name'].str.lower() == scraped_name.lower()) |
            (self.players_df['web_name'].str.lower() == scraped_name.lower())
        ]
        
        if not exact_match.empty:
            return exact_match.iloc[0]
        
        # Fuzzy match on full names
        player_names = self.players_df['full_name'].tolist()
        web_names = self.players_df['web_name'].tolist()
        
        # Try full name matching
        best_match_full = process.extractOne(scraped_name, player_names, scorer=fuzz.token_sort_ratio)
        best_match_web = process.extractOne(scraped_name, web_names, scorer=fuzz.token_sort_ratio)
        
        # Pick the best match
        if best_match_full and best_match_web:
            if best_match_full[1] >= best_match_web[1] and best_match_full[1] >= threshold:
                matched_player = self.players_df[self.players_df['full_name'] == best_match_full[0]].iloc[0]
                return matched_player
            elif best_match_web[1] >= threshold:
                matched_player = self.players_df[self.players_df['web_name'] == best_match_web[0]].iloc[0]
                return matched_player
        elif best_match_full and best_match_full[1] >= threshold:
            matched_player = self.players_df[self.players_df['full_name'] == best_match_full[0]].iloc[0]
            return matched_player
        elif best_match_web and best_match_web[1] >= threshold:
            matched_player = self.players_df[self.players_df['web_name'] == best_match_web[0]].iloc[0]
            return matched_player
        
        return None
    
    def get_player_fixtures(self, player_id: int, num_fixtures: int = 5) -> List[Dict]:
        """Get upcoming fixtures for a player"""
        try:
            response = requests.get(f"{self.base_url}element-summary/{player_id}/")
            response.raise_for_status()
            fixtures = response.json()['fixtures'][:num_fixtures]
            return fixtures
        except:
            return []
    
    def get_player_history_vs_team(self, player_id: int, opponent_team: int) -> Dict:
        """Get player's historical performance against a specific opponent"""
        try:
            response = requests.get(f"{self.base_url}element-summary/{player_id}/")
            response.raise_for_status()
            history = response.json()['history']
            
            vs_opponent = [h for h in history if h['opponent_team'] == opponent_team]
            
            if not vs_opponent:
                return {'matches': 0, 'avg_points': 0}
            
            total_points = sum(match['total_points'] for match in vs_opponent)
            avg_points = total_points / len(vs_opponent)
            
            return {
                'matches': len(vs_opponent),
                'total_points': total_points,
                'avg_points': avg_points
            }
        except:
            return {'matches': 0, 'avg_points': 0}
    
    def calculate_fixture_difficulty_score(self, player_id: int, num_fixtures: int = 5) -> float:
        """Calculate fixture difficulty score for upcoming fixtures"""
        fixtures = self.get_player_fixtures(player_id, num_fixtures)
        
        if not fixtures:
            return 3.0
        
        total_difficulty = sum(fixture['difficulty'] for fixture in fixtures)
        avg_difficulty = total_difficulty / len(fixtures)
        return avg_difficulty
    
    def integrate_web_data(self, player_row: pd.Series) -> float:
        """
        Calculate web consensus score for a player
        Integrates recommendations, injury news, and lineup predictions
        """
        if not self.use_web_data or not self.web_aggregator:
            return 5.0  # Neutral score
        
        player_name = player_row['full_name']
        
        # Get consensus
        consensus = self.web_aggregator.get_player_consensus_score(player_name)
        injury_status = self.web_aggregator.get_injury_status(player_name)
        expected_start = self.web_aggregator.is_expected_to_start(player_name)
        
        # Base web score from consensus (0-10 scale)
        web_score = consensus['consensus_score']
        
        # Apply injury penalties
        if injury_status == 'out':
            web_score = 0.0  # Don't recommend injured players
        elif injury_status == 'doubtful':
            web_score *= 0.5  # Heavy penalty for doubts
        elif injury_status == 'suspended':
            web_score = 0.0  # Don't recommend suspended players
        
        # Bonus for expected starters
        if expected_start and injury_status not in ['out', 'suspended']:
            web_score += 1.5
        
        # Boost for high mention count
        if consensus['mention_count'] >= 3:
            web_score += 1.0
        
        return max(0, min(10, web_score))  # Clamp to 0-10
    
    def calculate_player_score(self, player_row: pd.Series, next_opponent: Optional[int] = None) -> float:
        """
        Calculate comprehensive player score
        Weights adjusted to include web data
        """
        player_id = player_row['id']
        
        # Form score (0-10 scale)
        form_score = float(player_row['form_numeric']) if player_row['form_numeric'] > 0 else 0
        
        # Fixture difficulty (invert so easier = higher score)
        fixture_diff = self.calculate_fixture_difficulty_score(player_id, num_fixtures=5)
        fixture_score = (6 - fixture_diff) / 5 * 10
        
        # Historical performance vs next opponent
        historical_score = 0
        if next_opponent:
            history = self.get_player_history_vs_team(player_id, next_opponent)
            historical_score = min(history['avg_points'] * 1.5, 10)
        
        # Overall points (normalize)
        total_points = player_row['total_points']
        points_score = min(total_points / 20, 10)
        
        # ICT Index (normalize)
        ict_score = min(player_row['ict_index_numeric'] / 20, 10) if player_row['ict_index_numeric'] > 0 else 0
        
        # Web consensus score
        web_score = self.integrate_web_data(player_row)
        
        # Weighted average with web data
        if self.use_web_data and self.web_aggregator:
            weighted_score = (
                form_score * 0.25 +
                fixture_score * 0.20 +
                historical_score * 0.15 +
                points_score * 0.12 +
                ict_score * 0.08 +
                web_score * 0.20  # Web consensus
            )
        else:
            # Without web data, redistribute weights
            weighted_score = (
                form_score * 0.30 +
                fixture_score * 0.25 +
                historical_score * 0.20 +
                points_score * 0.15 +
                ict_score * 0.10
            )
        
        return weighted_score
    
    def load_web_data(self, aggregator):
        """Load web scraper aggregator"""
        self.web_aggregator = aggregator
        print("  ✓ Web data integrated")
    
    def get_current_squad_df(self) -> pd.DataFrame:
        """Get DataFrame of current squad players"""
        if self.current_team is None:
            self.fetch_my_team()
        
        if self.players_df is None:
            self.prepare_players_dataframe()
        
        squad_ids = self.current_team['squad_ids']
        squad_df = self.players_df[self.players_df['id'].isin(squad_ids)].copy()
        
        return squad_df
    
    def suggest_transfers(self, num_transfers: int = 1, position_filter: Optional[str] = None) -> List[Dict]:
        """Suggest optimal transfers based on current squad"""
        if self.current_team is None:
            self.fetch_my_team()
        
        if self.players_df is None:
            self.prepare_players_dataframe()
        
        # Ensure we have fixtures data
        if not self.data or 'fixtures' not in self.data:
            print("Warning: Fixtures data not available, fetching...")
            self.fetch_fpl_data(use_cache=False)
        
        current_squad_df = self.get_current_squad_df()
        
        # Get next opponent for each team
        fixtures = self.get_fixtures_for_gameweek(self.current_gameweek)
        team_next_opponent = {}
        for fixture in fixtures:
            team_next_opponent[fixture['team_h']] = fixture['team_a']
            team_next_opponent[fixture['team_a']] = fixture['team_h']
        
        # Calculate scores for current squad
        current_squad_df['next_opponent'] = current_squad_df['team'].map(team_next_opponent)
        current_squad_df['player_score'] = current_squad_df.apply(
            lambda row: self.calculate_player_score(row, row['next_opponent']),
            axis=1
        )
        
        # Filter potential targets
        available_players = self.players_df[
            (~self.players_df['id'].isin(self.current_team['squad_ids'])) &
            (self.players_df['status'] == 'a')
        ].copy()
        
        if position_filter:
            available_players = available_players[available_players['position_name'] == position_filter]
        
        # Calculate scores for available players
        available_players['next_opponent'] = available_players['team'].map(team_next_opponent)
        available_players['player_score'] = available_players.apply(
            lambda row: self.calculate_player_score(row, row['next_opponent']),
            axis=1
        )
        
        # Find best transfer options
        transfer_suggestions = []
        
        for pos in ['GK', 'DEF', 'MID', 'FWD']:
            if position_filter and pos != position_filter:
                continue
            
            pos_current = current_squad_df[current_squad_df['position_name'] == pos].copy()
            pos_available = available_players[available_players['position_name'] == pos].copy()
            
            pos_current = pos_current.sort_values('player_score', ascending=True)
            
            for _, out_player in pos_current.iterrows():
                selling_price = out_player['now_cost'] / 10
                available_budget = self.budget + selling_price
                
                affordable = pos_available[pos_available['value'] <= available_budget].copy()
                
                if affordable.empty:
                    continue
                
                affordable = affordable.sort_values('player_score', ascending=False)
                
                team_counts = current_squad_df['team'].value_counts()
                
                for _, in_player in affordable.head(10).iterrows():
                    if in_player['team'] != out_player['team']:
                        current_team_count = team_counts.get(in_player['team'], 0)
                        if current_team_count >= 3:
                            continue
                    
                    score_improvement = in_player['player_score'] - out_player['player_score']
                    
                    if score_improvement > 0.5:
                        # Get web insights
                        web_mentions = 0
                        web_sentiment = 'neutral'
                        if self.web_aggregator:
                            consensus = self.web_aggregator.get_player_consensus_score(in_player['full_name'])
                            web_mentions = consensus['mention_count']
                            web_sentiment = consensus['sentiment']
                        
                        transfer_suggestions.append({
                            'out_player': out_player['full_name'],
                            'out_player_id': out_player['id'],
                            'out_team': out_player['team_name'],
                            'out_price': out_player['value'],
                            'out_score': out_player['player_score'],
                            'out_form': out_player['form_numeric'],
                            'in_player': in_player['full_name'],
                            'in_player_id': in_player['id'],
                            'in_team': in_player['team_name'],
                            'in_price': in_player['value'],
                            'in_score': in_player['player_score'],
                            'in_form': in_player['form_numeric'],
                            'position': pos,
                            'improvement': score_improvement,
                            'cost_diff': in_player['value'] - out_player['value'],
                            'web_mentions': web_mentions,
                            'web_sentiment': web_sentiment
                        })
        
        transfer_suggestions.sort(key=lambda x: x['improvement'], reverse=True)
        
        return transfer_suggestions[:num_transfers * 5]
    
    def display_transfer_suggestions(self, suggestions: List[Dict]):
        """Display transfer suggestions in a readable format"""
        if not suggestions:
            print("\nNo significant transfer improvements found!")
            return
        
        print("\n" + "="*120)
        print("TRANSFER RECOMMENDATIONS")
        print("="*120)
        
        print(f"\nShowing top {min(len(suggestions), 10)} transfer suggestions:\n")
        
        for i, transfer in enumerate(suggestions[:10], 1):
            web_badge = ""
            if transfer.get('web_mentions', 0) > 0:
                sentiment_emoji = {"positive": "✓", "negative": "✗", "neutral": "○"}
                emoji = sentiment_emoji.get(transfer.get('web_sentiment', 'neutral'), "○")
                web_badge = f" [{emoji} {transfer['web_mentions']} mentions]"
            
            print(f"{i}. [{transfer['position']}] Transfer Suggestion:{web_badge}")
            print(f"   OUT: {transfer['out_player']:25s} ({transfer['out_team']:12s}) "
                  f"£{transfer['out_price']:4.1f}m | Score: {transfer['out_score']:4.1f} | Form: {transfer['out_form']:4.1f}")
            print(f"   IN:  {transfer['in_player']:25s} ({transfer['in_team']:12s}) "
                  f"£{transfer['in_price']:4.1f}m | Score: {transfer['in_score']:4.1f} | Form: {transfer['in_form']:4.1f}")
            print(f"   Improvement: +{transfer['improvement']:.2f} points | Cost: £{transfer['cost_diff']:+.1f}m")
            print()
        
        print("="*120)
    
    def display_current_squad(self):
        """Display current squad with performance metrics"""
        current_squad_df = self.get_current_squad_df()
        
        # Ensure we have fixtures data
        if not self.data or 'fixtures' not in self.data:
            print("Warning: Fixtures data not available, fetching...")
            self.fetch_fpl_data(use_cache=False)
        
        print("\n" + "="*120)
        print(f"YOUR CURRENT SQUAD (Team ID: {self.team_id})")
        print("="*120)
        print(f"Budget in Bank: £{self.budget:.1f}m | Gameweek: {self.current_gameweek}")
        
        fixtures = [f for f in self.data['fixtures'] if f['event'] == self.current_gameweek]
        team_next_opponent = {}
        opponent_names = {}
        for fixture in fixtures:
            team_next_opponent[fixture['team_h']] = fixture['team_a']
            team_next_opponent[fixture['team_a']] = fixture['team_h']
            teams_dict = {team['id']: team['short_name'] for team in self.data['teams']}
            opponent_names[fixture['team_h']] = teams_dict[fixture['team_a']]
            opponent_names[fixture['team_a']] = teams_dict[fixture['team_h']]
        
        current_squad_df['next_opponent'] = current_squad_df['team'].map(team_next_opponent)
        current_squad_df['opponent_name'] = current_squad_df['team'].map(opponent_names)
        current_squad_df['player_score'] = current_squad_df.apply(
            lambda row: self.calculate_player_score(row, row['next_opponent']),
            axis=1
        )
        
        print("\n" + "-"*120)
        
        for pos in ['GK', 'DEF', 'MID', 'FWD']:
            pos_players = current_squad_df[current_squad_df['position_name'] == pos].sort_values(
                'player_score', ascending=False
            )
            print(f"\n{pos}:")
            for _, player in pos_players.iterrows():
                fixture_diff = self.calculate_fixture_difficulty_score(player['id'], 5)
                web_info = ""
                if self.web_aggregator:
                    consensus = self.web_aggregator.get_player_consensus_score(player['full_name'])
                    if consensus['mention_count'] > 0:
                        web_info = f" | Web: {consensus['sentiment'][:3].upper()}({consensus['mention_count']})"
                
                print(f"  {player['full_name']:25s} ({player['team_name']:12s}) "
                      f"£{player['value']:4.1f}m | Score: {player['player_score']:4.1f} | "
                      f"Form: {player['form_numeric']:4.1f} | Next: vs {player['opponent_name']:3s} | "
                      f"FDR(5): {fixture_diff:.1f}{web_info}")
        
        print("\n" + "="*120)
    
    def suggest_captain(self, top_n: int = 5) -> List[Dict]:
        """
        Suggest best captain options from current squad
        
        Captain scoring considers:
        - Next fixture difficulty (40%)
        - Current form (25%)
        - Historical performance vs opponent (20%)
        - Web consensus for captaincy (15%)
        
        Args:
            top_n: Number of captain options to return
            
        Returns:
            List of captain recommendations with detailed reasoning
        """
        if self.current_team is None:
            self.fetch_my_team()
        
        if self.players_df is None:
            self.prepare_players_dataframe()
        
        # Ensure we have fixtures data
        if not self.data or 'fixtures' not in self.data:
            print("Warning: Fixtures data not available, fetching...")
            self.fetch_fpl_data(use_cache=False)
        
        current_squad_df = self.get_current_squad_df()
        
        # Get next opponent for each team
        fixtures = self.get_fixtures_for_gameweek(self.current_gameweek)
        opponent_names = {}
        is_home = {}
        team_next_opponent = {}
        
        for fixture in fixtures:
            team_next_opponent[fixture['team_h']] = fixture['team_a']
            team_next_opponent[fixture['team_a']] = fixture['team_h']
            teams_dict = {team['id']: team['short_name'] for team in self.data['teams']}
            opponent_names[fixture['team_h']] = teams_dict[fixture['team_a']]
            opponent_names[fixture['team_a']] = teams_dict[fixture['team_h']]
            is_home[fixture['team_h']] = True
            is_home[fixture['team_a']] = False
        
        current_squad_df['next_opponent'] = current_squad_df['team'].map(team_next_opponent)
        current_squad_df['opponent_name'] = current_squad_df['team'].map(opponent_names)
        current_squad_df['is_home'] = current_squad_df['team'].map(is_home)
        
        captain_candidates = []
        
        for _, player in current_squad_df.iterrows():
            player_id = player['id']
            next_opponent = player['next_opponent']
            
            # 1. Next fixture difficulty (40% weight)
            next_fixture = self.get_player_fixtures(player_id, num_fixtures=1)
            if next_fixture:
                fixture_difficulty = next_fixture[0]['difficulty']
                # Invert: easier fixture = higher score
                fixture_score = (6 - fixture_difficulty) / 5 * 10
            else:
                fixture_score = 5.0  # Neutral
            
            # 2. Current form (25% weight)
            form_score = float(player['form_numeric']) if player['form_numeric'] > 0 else 0
            
            # 3. Historical vs opponent (20% weight)
            historical_score = 0
            if next_opponent:
                history = self.get_player_history_vs_team(player_id, next_opponent)
                historical_score = min(history['avg_points'] * 1.5, 10)
            
            # 4. Web consensus for captaincy (15% weight)
            web_captain_score = 5.0  # Neutral default
            is_web_captain = False
            
            if self.web_aggregator:
                player_name = player['full_name']
                recs_df = pd.DataFrame(self.web_aggregator.player_data['recommendations'])
                
                if not recs_df.empty:
                    # Check if mentioned as captain pick
                    captain_recs = recs_df[
                        (recs_df['player_name'].str.contains(player_name, case=False, na=False)) &
                        (recs_df['recommendation_type'] == 'captain')
                    ]
                    
                    if not captain_recs.empty:
                        is_web_captain = True
                        # High bonus for captain recommendations
                        captain_mentions = len(captain_recs)
                        web_captain_score = min(10, 7 + captain_mentions * 1.5)
                    else:
                        # Check general consensus
                        consensus = self.web_aggregator.get_player_consensus_score(player_name)
                        if consensus['mention_count'] > 0:
                            web_captain_score = min(consensus['consensus_score'] * 1.2, 10)
            
            # Calculate weighted captain score
            captain_score = (
                fixture_score * 0.40 +
                form_score * 0.25 +
                historical_score * 0.20 +
                web_captain_score * 0.15
            )
            
            # Home advantage bonus
            if player['is_home']:
                captain_score += 0.5
            
            # Position multiplier (forwards and mids more likely to return)
            position_multipliers = {'FWD': 1.2, 'MID': 1.1, 'DEF': 0.9, 'GK': 0.5}
            captain_score *= position_multipliers.get(player['position_name'], 1.0)
            
            # Premium player bonus (expensive players more consistent)
            if player['value'] >= 10.0:
                captain_score += 0.5
            
            # Calculate expected points
            # Simple model: form * (fixture_ease / 3) * position_multiplier
            fixture_ease = (6 - fixture_difficulty) / 5 if next_fixture else 0.5
            expected_points = (
                float(player['form_numeric']) * 
                fixture_ease * 
                position_multipliers.get(player['position_name'], 1.0) * 
                2  # Captain doubles points
            )
            
            captain_candidates.append({
                'player_name': player['full_name'],
                'player_id': player_id,
                'team': player['team_name'],
                'position': player['position_name'],
                'price': player['value'],
                'captain_score': captain_score,
                'form': player['form_numeric'],
                'opponent': player['opponent_name'],
                'is_home': player['is_home'],
                'fixture_difficulty': fixture_difficulty if next_fixture else 3,
                'expected_points': expected_points,
                'is_web_captain': is_web_captain,
                'total_points': player['total_points'],
                'selected_by': player['selected_by_percent_numeric']
            })
        
        # Sort by captain score
        captain_candidates.sort(key=lambda x: x['captain_score'], reverse=True)
        
        return captain_candidates[:top_n]
    
    def suggest_vice_captain(self, captain_choice: str = None) -> Dict:
        """
        Suggest vice captain (different from captain, high floor)
        
        Args:
            captain_choice: Name of chosen captain (to exclude)
            
        Returns:
            Vice captain recommendation
        """
        captain_options = self.suggest_captain(top_n=15)
        
        # Filter out captain if specified
        if captain_choice:
            captain_options = [
                opt for opt in captain_options 
                if opt['player_name'].lower() != captain_choice.lower()
            ]
        
        # For vice, prioritize consistency (high floor) over ceiling
        # Look for players with:
        # - Good fixtures
        # - Consistent form
        # - Less risky (not rotation prone)
        
        for option in captain_options:
            # Penalize very expensive differentials (rotation risk)
            if option['selected_by'] < 5.0:
                option['vice_score'] = option['captain_score'] * 0.8
            else:
                option['vice_score'] = option['captain_score']
            
            # Reward consistency (total points vs form ratio)
            consistency = option['total_points'] / max(option['form'], 1)
            if consistency > 15:  # Consistent performer
                option['vice_score'] += 0.5
        
        captain_options.sort(key=lambda x: x['vice_score'], reverse=True)
        
        return captain_options[0] if captain_options else None
    
    def display_captain_recommendations(self, captain_options: List[Dict]):
        """Display captain recommendations in a readable format"""
        if not captain_options:
            print("\nNo captain options available!")
            return
        
        print("\n" + "="*120)
        print("CAPTAIN RECOMMENDATIONS")
        print("="*120)
        
        print(f"\nTop {len(captain_options)} Captain Options for Gameweek {self.current_gameweek}:\n")
        
        for i, option in enumerate(captain_options, 1):
            badge = "⭐ WEB PICK" if option['is_web_captain'] else ""
            home_away = "H" if option['is_home'] else "A"
            
            print(f"{i}. {option['player_name']:25s} ({option['position']}) {badge}")
            print(f"   Team: {option['team']:15s} | Price: £{option['price']:.1f}m | "
                  f"Ownership: {option['selected_by']:.1f}%")
            print(f"   Fixture: vs {option['opponent']:3s} ({home_away}) | "
                  f"Difficulty: {option['fixture_difficulty']}/5")
            print(f"   Form: {option['form']:.1f} | Season Points: {option['total_points']}")
            print(f"   Captain Score: {option['captain_score']:.2f}/10 | "
                  f"Expected Points: {option['expected_points']:.1f}")
            
            # Add reasoning
            reasons = []
            if option['is_web_captain']:
                reasons.append("Expert captain pick")
            if option['fixture_difficulty'] <= 2:
                reasons.append("Great fixture")
            if option['is_home']:
                reasons.append("Home advantage")
            if option['form'] >= 7.0:
                reasons.append("Excellent form")
            if option['price'] >= 10.0:
                reasons.append("Premium option")
            if option['selected_by'] < 10.0:
                reasons.append("⚡ Differential")
            elif option['selected_by'] > 50.0:
                reasons.append("🔒 Template/Safe")
            
            if reasons:
                print(f"   Why: {' | '.join(reasons)}")
            
            print()
        
        print("="*120)
        
        # Add strategic advice
        top_pick = captain_options[0]
        print("\n📊 STRATEGIC ADVICE:")
        print(f"\n🎯 Recommended Captain: {top_pick['player_name']}")
        
        if top_pick['selected_by'] > 50:
            print("   Strategy: TEMPLATE PICK - Safe choice, won't gain/lose rank significantly")
        elif top_pick['selected_by'] < 10:
            print("   Strategy: DIFFERENTIAL - High risk/reward, can gain rank if successful")
        else:
            print("   Strategy: BALANCED - Good risk/reward ratio")
        
        # Vice captain suggestion
        vice = self.suggest_vice_captain(captain_choice=top_pick['player_name'])
        if vice:
            print(f"\n🔄 Recommended Vice Captain: {vice['player_name']}")
            print(f"   Reason: Consistent performer with safe floor")
        
        print("\n" + "="*120)
        """Display transfer suggestions"""
        if not suggestions:
            print("\nNo significant transfer improvements found!")
            return
        
        print("\n" + "="*120)
        print("TRANSFER RECOMMENDATIONS")
        print("="*120)
        
        print(f"\nShowing top {min(len(suggestions), 10)} transfer suggestions:\n")
        
        for i, transfer in enumerate(suggestions[:10], 1):
            web_badge = ""
            if transfer['web_mentions'] > 0:
                sentiment_emoji = {"positive": "✓", "negative": "✗", "neutral": "○"}
                emoji = sentiment_emoji.get(transfer['web_sentiment'], "○")
                web_badge = f" [{emoji} {transfer['web_mentions']} mentions]"
            
            print(f"{i}. [{transfer['position']}] Transfer Suggestion:{web_badge}")
            print(f"   OUT: {transfer['out_player']:25s} ({transfer['out_team']:12s}) "
                  f"£{transfer['out_price']:4.1f}m | Score: {transfer['out_score']:4.1f} | Form: {transfer['out_form']:4.1f}")
            print(f"   IN:  {transfer['in_player']:25s} ({transfer['in_team']:12s}) "
                  f"£{transfer['in_price']:4.1f}m | Score: {transfer['in_score']:4.1f} | Form: {transfer['in_form']:4.1f}")
            print(f"   Improvement: +{transfer['improvement']:.2f} points | Cost: £{transfer['cost_diff']:+.1f}m")
            print()
        
        print("="*120)


# Run with: python fpl_integrated_system.py
if __name__ == "__main__":
    print("Fantasy Premier League Integrated Transfer Recommender")
    print("="*120)
    
    # Configuration
    TEAM_ID = 1234578987 # <-- CHANGE THIS TO YOUR TEAM ID
    USE_WEB_DATA = False # TODO: Set to False to till web scraping devo is completed
    USE_CACHE = False # Set to False to force fresh data
    
    print(f"\nConfiguration:")
    print(f"  Team ID: {TEAM_ID}")
    print(f"  Web Data: {'Enabled' if USE_WEB_DATA else 'Disabled'}")
    print(f"  Caching: {'Enabled' if USE_CACHE else 'Disabled'}")
    
    # Initialize recommender
    print(f"\n{'='*120}")
    print("STEP 1: Initializing FPL Recommender")
    print(f"{'='*120}")
    recommender = FPLRecommender(team_id=TEAM_ID, use_web_data=False) #TODO: replace with USE_WEB_DATA boolean
    
    # Fetch FPL data
    print("\nFetching FPL data...")
    recommender.fetch_fpl_data(use_cache=USE_CACHE)
    print("Fetching your team data...")
    recommender.fetch_my_team(use_cache=USE_CACHE)
    print("Preparing player database...")
    recommender.prepare_players_dataframe()
    
    # Load web data if enabled
    if USE_WEB_DATA:
        print(f"\n{'='*120}")
        print("STEP 2: Scraping Expert Recommendations from Multiple Sources")
        print(f"{'='*120}")
        
        # Import web scrapers
        from fpl_web_scraper import (
            ScraperAggregator, 
            FantasyFootballScoutScraper,
        )
        
        # Check for cached web data
        web_cache_path = recommender._get_cache_path('web_data')
        
        if USE_CACHE and recommender._is_cache_valid(web_cache_path):
            print("\nLoading web data from cache...")
            aggregator = recommender._load_cache('web_data')
        else:
            print("\nScraping fresh data from expert sources...")
            print("This may take 2-3 minutes. Please wait...\n")
            
            aggregator = ScraperAggregator()
            
            # Add all scrapers
            scrapers = [
                FantasyFootballScoutScraper(),
            ]
            
            print("Sources to scrape:")
            for scraper in scrapers:
                aggregator.add_scraper(scraper)
                print(f"  • {scraper.source_name}")
            
            print()
            aggregator.scrape_all()
            
            if USE_CACHE:
                recommender._save_cache('web_data', aggregator)
        
        recommender.load_web_data(aggregator)
        
        # Show web data summary
        print("\n" + "-"*120)
        print("WEB SCRAPING SUMMARY")
        print("-"*120)
        
        total_recs = len(aggregator.player_data['recommendations'])
        total_injuries = len(aggregator.player_data['injury_news'])
        total_lineups = len(aggregator.player_data['lineups'])
        
        print(f"  ✓ Player Recommendations: {total_recs}")
        print(f"  ✓ Injury/Availability Updates: {total_injuries}")
        print(f"  ✓ Team Lineups: {total_lineups}")
        
        summary_df = aggregator.get_summary_dataframe()
        if not summary_df.empty and len(summary_df) > 0:
            print("\n  Top Recommended Players Across All Sources:")
            display_count = min(10, len(summary_df))
            for idx, (player_name, row) in enumerate(summary_df.head(display_count).iterrows(), 1):
                print(f"    {idx}. {player_name:25s} - {row['mention_count']} mentions ({row['sentiment']})")
        
        print("-"*120)
    
    # Display current squad
    print(f"\n{'='*120}")
    print("STEP 3: Analyzing Your Current Squad")
    print(f"{'='*120}")
    recommender.display_current_squad()
    
    # Get transfer suggestions
    print(f"\n{'='*120}")
    print("STEP 4: Generating Transfer Recommendations")
    print(f"{'='*120}")
    print("\nAnalyzing potential transfers...")
    suggestions = recommender.suggest_transfers(num_transfers=2)
    
    # Display suggestions
    recommender.display_transfer_suggestions(suggestions)
    
    # Get captain recommendations
    print(f"\n{'='*120}")
    print("STEP 5: Captain & Vice Captain Recommendations")
    print(f"{'='*120}")
    print("\nAnalyzing captain options from your squad...")
    captain_options = recommender.suggest_captain(top_n=5)
    recommender.display_captain_recommendations(captain_options)
    
    print("\n" + "="*120)
    print("Analysis complete!")
    print("\nFeatures:")
    print("  ✓ Fixture difficulty analysis (next 5 gameweeks)")
    print("  ✓ Player form tracking")
    print("  ✓ Historical performance vs opponents")
    print("  ✓ Captain & Vice Captain recommendations")
    if USE_WEB_DATA:
        print("  ✓ Expert recommendations from FPL websites")
        print("  ✓ Expert captain picks integration")
        print("  ✓ Injury/availability tracking")
        print("  ✓ Fuzzy player name matching")
    print("  ✓ Smart caching (6-hour refresh)")
    print("\nTo clear cache: recommender.clear_cache()")
    print("="*120)
