"""AI strategy module for Rock-Paper-Scissors computer opponent.

Combines 4 strategies into an ensemble:
  - MarkovChainPredictor: n-gram pattern matching
  - FrequencyAnalyzer: decay-weighted frequency analysis
  - AntiRotator: detects Rock->Paper->Scissors cycling patterns
  - MetaStrategy: picks the best-performing predictor based on recent accuracy
"""
from enum import Enum
from collections import defaultdict, Counter, deque
from typing import Optional, List, Dict, Tuple

from backend.config import MARKOV_ORDER, FREQUENCY_DECAY, RECENT_WINDOW, META_WINDOW


class Move(Enum):
    ROCK = 0
    PAPER = 1
    SCISSORS = 2


MOVE_NAME = {Move.ROCK: "Rock", Move.PAPER: "Paper", Move.SCISSORS: "Scissors"}

BEATS = {Move.ROCK: Move.SCISSORS, Move.PAPER: Move.ROCK, Move.SCISSORS: Move.PAPER}
LOSES_TO = {Move.SCISSORS: Move.ROCK, Move.ROCK: Move.PAPER, Move.PAPER: Move.SCISSORS}


class MarkovChainPredictor:
    """N-gram Markov chain: predicts next move based on pattern of last N-1 moves."""

    def __init__(self, order: int = MARKOV_ORDER):
        self.order = order
        self.transitions: Dict[Tuple[Move, ...], Counter] = defaultdict(Counter)

    def train(self, history: List[Move]):
        self.transitions.clear()
        if len(history) < self.order:
            return
        for i in range(len(history) - self.order + 1):
            key = tuple(history[i:i + self.order - 1])
            next_move = history[i + self.order - 1]
            self.transitions[key][next_move] += 1

    def predict(self, history: List[Move]) -> Optional[Move]:
        if len(history) < self.order - 1:
            return None
        key = tuple(history[-(self.order - 1):])
        counter = self.transitions.get(key)
        if counter:
            return counter.most_common(1)[0][0]
        return None

    @property
    def name(self):
        return "markov"


class FrequencyAnalyzer:
    """Weighted frequency analysis with exponential decay on recent moves."""

    def __init__(self, decay: float = FREQUENCY_DECAY):
        self.decay = decay

    def predict(self, history: List[Move]) -> Move:
        weights = {Move.ROCK: 0.0, Move.PAPER: 0.0, Move.SCISSORS: 0.0}
        n = len(history)
        for i, move in enumerate(history):
            weight = self.decay ** (n - 1 - i)
            weights[move] += weight
        return max(weights, key=weights.get)

    @property
    def name(self):
        return "frequency"


class AntiRotator:
    """Detects cyclic rotation patterns (clockwise or counter-clockwise)."""

    ROTATION = [Move.ROCK, Move.PAPER, Move.SCISSORS]

    def __init__(self, window: int = 6):
        self.window = window

    def predict(self, history: List[Move]) -> Optional[Move]:
        recent = history[-self.window:] if len(history) >= self.window else history
        if len(recent) < 3:
            return None

        cw_count = 0
        ccw_count = 0
        for i in range(len(recent) - 1):
            curr_idx = self.ROTATION.index(recent[i])
            if self.ROTATION[(curr_idx + 1) % 3] == recent[i + 1]:
                cw_count += 1
            elif self.ROTATION[(curr_idx - 1) % 3] == recent[i + 1]:
                ccw_count += 1

        total = len(recent) - 1
        if cw_count >= total * 0.7:
            return self.ROTATION[(self.ROTATION.index(recent[-1]) + 1) % 3]
        elif ccw_count >= total * 0.7:
            return self.ROTATION[(self.ROTATION.index(recent[-1]) - 1) % 3]
        return None

    @property
    def name(self):
        return "anti_rotate"


class MetaStrategy:
    """Tracks each predictor's recent accuracy and selects the best one.
    Uses epsilon-greedy exploration to ensure all strategies get tried.
    """

    def __init__(self, eval_window: int = META_WINDOW):
        self.window = eval_window
        self.scores: Dict[str, deque] = {
            "markov": deque(maxlen=eval_window),
            "frequency": deque(maxlen=eval_window),
            "anti_rotate": deque(maxlen=eval_window),
        }
        self.round_count = 0

    def select(self, available_strategies: list) -> str:
        """Select best strategy. Explore 20% of the time for the first 30 rounds."""
        self.round_count += 1

        # Exploration: occasionally try a random available strategy
        if self.round_count <= 30 and len(available_strategies) > 1:
            import random
            if random.random() < 0.2:
                return random.choice(available_strategies)

        # Exploitation: pick best based on tracked accuracy
        best_strategy = available_strategies[0] if available_strategies else "frequency"
        best_accuracy = -1.0
        for name in available_strategies:
            dq = self.scores[name]
            if dq:
                accuracy = sum(dq) / len(dq)
            else:
                accuracy = 0.5  # prior for untested strategies (optimistic)
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_strategy = name
        return best_strategy

    def record(self, strategy_name: str, correct: bool):
        # Ignore untracked strategy names (e.g. the "fallback" pseudo-strategy)
        dq = self.scores.get(strategy_name)
        if dq is not None:
            dq.append(1 if correct else 0)

    def get_accuracies(self) -> Dict[str, float]:
        return {
            name: round(sum(dq) / len(dq), 3) if dq else 0.0
            for name, dq in self.scores.items()
        }


class AIStrategy:
    """Composite ensemble strategy."""

    def __init__(self):
        self.markov = MarkovChainPredictor()
        self.frequency = FrequencyAnalyzer()
        self.anti_rotator = AntiRotator()
        self.meta = MetaStrategy()
        self.last_reasoning: Dict = {}

    def predict_player_move(self, history: List[Move]) -> Tuple[Move, str, Dict]:
        """Predict what move the player will make next.
        Returns (predicted_move, strategy_name, reasoning_dict).
        """
        # Train Markov chain on current history
        self.markov.train(history)

        # Get predictions from each sub-strategy
        candidates = {}
        reasoning = {"candidates": {}, "history": [MOVE_NAME[m] for m in history[-10:]]}

        if len(history) >= 2:
            markov_pred = self.markov.predict(history)
            if markov_pred is not None:
                candidates["markov"] = markov_pred
                reasoning["candidates"]["markov"] = MOVE_NAME[markov_pred]
            else:
                reasoning["candidates"]["markov"] = "N/A (no matching pattern)"

        freq_pred = self.frequency.predict(history)
        candidates["frequency"] = freq_pred
        reasoning["candidates"]["frequency"] = MOVE_NAME[freq_pred]

        anti_pred = self.anti_rotator.predict(history)
        if anti_pred is not None:
            candidates["anti_rotate"] = anti_pred
            reasoning["candidates"]["anti_rotate"] = MOVE_NAME[anti_pred]
        else:
            reasoning["candidates"]["anti_rotate"] = "N/A (no rotation detected)"

        # Select strategy
        available = list(candidates.keys())
        strategy = self.meta.select(available)
        if strategy not in candidates:
            strategy = "frequency"

        predicted = candidates[strategy]

        reasoning["strategy_selected"] = strategy
        reasoning["predicted_player_move"] = MOVE_NAME[predicted]
        reasoning["computer_move"] = MOVE_NAME[LOSES_TO[predicted]]
        reasoning["strategy_accuracies"] = self.meta.get_accuracies()

        self.last_reasoning = reasoning
        return predicted, strategy, reasoning

    def get_computer_move(self, history: List[Move]) -> Tuple[Move, Move, str, Dict]:
        """Returns (computer_move, predicted_player_move, strategy_name, reasoning).
        Computer plays the move that beats the predicted player move.
        """
        predicted_player_move, strategy, reasoning = self.predict_player_move(history)
        computer_move = LOSES_TO[predicted_player_move]
        return computer_move, predicted_player_move, strategy, reasoning

    def record_result(self, strategy_name: str, predicted: Move, actual: Move,
                      all_candidates: Dict[str, Move] = None):
        """Record accuracy for the selected strategy AND all other strategies."""
        self.meta.record(strategy_name, predicted == actual)
        # Also record how other strategies would have done
        if all_candidates:
            for name, cand_pred in all_candidates.items():
                if name != strategy_name:
                    self.meta.record(name, cand_pred == actual)
