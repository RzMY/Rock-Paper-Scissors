"""Game engine: state machine and round resolution for RPS game."""
import math
import time
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from backend.config import COUNTDOWN_SECONDS, RESULT_DISPLAY_SECONDS
from backend.ai_strategy import Move, BEATS, AIStrategy
import backend.database as db


class GameState(Enum):
    WAITING = "waiting"
    COUNTDOWN = "countdown"
    SHOOT = "shoot"
    RESULT = "result"


MOVE_NAMES = {"Rock": Move.ROCK, "Paper": Move.PAPER, "Scissors": Move.SCISSORS}
MOVE_NAMES_REV = {Move.ROCK: "Rock", Move.PAPER: "Paper", Move.SCISSORS: "Scissors"}


@dataclass
class RoundResult:
    player_move: str
    computer_move: str
    predicted_player_move: str
    result: str  # 'win', 'lose', 'draw'
    confidence: float
    strategy_used: str


class GameEngine:
    def __init__(self):
        self.state = GameState.WAITING
        self.ai = AIStrategy()
        self.player_score = 0
        self.computer_score = 0
        self.draws = 0
        self.current_round = 0
        self.player_move_history: List[Move] = []
        self.last_result: Optional[RoundResult] = None
        self.countdown_start: float = 0
        self.result_start: float = 0
        self.round_active = False
        self.auto_play = False

    def start_round(self) -> dict:
        """Begin a new round countdown."""
        if self.state not in (GameState.WAITING, GameState.RESULT):
            return {"status": "error", "message": "Round already in progress"}

        self.round_active = True
        self.state = GameState.COUNTDOWN
        self.countdown_start = time.time()
        self.current_round += 1
        return {
            "type": "game_state",
            "state": "countdown",
            "count": COUNTDOWN_SECONDS,
            "round": self.current_round,
        }

    def tick(self) -> Optional[dict]:
        """Advance state machine based on elapsed time. Returns state update or None."""
        now = time.time()

        if self.state == GameState.COUNTDOWN:
            elapsed = now - self.countdown_start
            remaining = math.ceil(COUNTDOWN_SECONDS - elapsed)
            if remaining <= 0:
                self.state = GameState.SHOOT
                return {
                    "type": "game_state",
                    "state": "shoot",
                    "round": self.current_round,
                }
            return {
                "type": "game_state",
                "state": "countdown",
                "count": remaining,
                "round": self.current_round,
            }

        if self.state == GameState.RESULT:
            elapsed = now - self.result_start
            if elapsed >= RESULT_DISPLAY_SECONDS:
                if self.auto_play:
                    return self.start_round()
                self.state = GameState.WAITING
                return {"type": "game_state", "state": "waiting"}

        return None

    def toggle_auto_play(self) -> bool:
        self.auto_play = not self.auto_play
        return self.auto_play

    def resolve_round(self, player_move_name: Optional[str], confidence: float = 0.0) -> dict:
        """Called during SHOOT phase when YOLO detects or fails to detect a move."""
        if player_move_name is None or player_move_name not in MOVE_NAMES:
            self.state = GameState.WAITING
            return {
                "type": "game_state",
                "state": "no_detect",
                "message": "No hand detected. Try again!",
            }

        player_move = MOVE_NAMES[player_move_name]
        self.player_move_history.append(player_move)

        # AI chooses counter-move (returns reasoning dict as 4th element)
        try:
            computer_move, predicted_player_move, strategy, reasoning = (
                self.ai.get_computer_move(self.player_move_history[:-1])
            )
        except Exception:
            import traceback
            traceback.print_exc()
            # Fallback: pick a random move if AI fails
            import random
            predicted_player_move = random.choice(list(Move))
            strategy = "fallback"
            reasoning = {
                "candidates": {"frequency": MOVE_NAME[predicted_player_move]},
                "history": [],
                "strategy_selected": "fallback",
                "predicted_player_move": MOVE_NAME[predicted_player_move],
                "computer_move": MOVE_NAME[LOSES_TO[predicted_player_move]],
                "strategy_accuracies": {},
            }
            computer_move = LOSES_TO[predicted_player_move]

        # Determine result (all outcomes from player's perspective)
        if computer_move == player_move:
            outcome = "draw"
            self.draws += 1
        elif BEATS[player_move] == computer_move:
            outcome = "win"
            self.player_score += 1
        else:
            outcome = "lose"
            self.computer_score += 1

        # Record AI accuracy for ALL strategies (not just the selected one)
        all_candidates = {}
        for name, pred_name in reasoning.get("candidates", {}).items():
            if pred_name != "N/A" and pred_name in MOVE_NAMES:
                all_candidates[name] = MOVE_NAMES[pred_name]
        self.ai.record_result(strategy, predicted_player_move, player_move,
                              all_candidates)

        # Save to database
        db.insert_round(
            round_number=self.current_round,
            player_move=player_move_name,
            player_confidence=confidence,
            computer_move=MOVE_NAMES_REV[computer_move],
            predicted_player_move=MOVE_NAMES_REV[predicted_player_move],
            result=outcome,
            strategy_used=strategy,
        )

        self.last_result = RoundResult(
            player_move=player_move_name,
            computer_move=MOVE_NAMES_REV[computer_move],
            predicted_player_move=MOVE_NAMES_REV[predicted_player_move],
            result=outcome,
            confidence=confidence,
            strategy_used=strategy,
        )

        self.state = GameState.RESULT
        self.result_start = time.time()

        return {
            "type": "game_state",
            "state": "result",
            "player_move": player_move_name,
            "computer_move": MOVE_NAMES_REV[computer_move],
            "predicted_player_move": MOVE_NAMES_REV[predicted_player_move],
            "result": outcome,
            "confidence": confidence,
            "strategy": strategy,
            "reasoning": reasoning,
        }

    def shoot_with_frame_detection(self, predictions: list) -> dict:
        """Process frame predictions during SHOOT state."""
        if predictions:
            best = predictions[0]
            return self.resolve_round(best.class_name, best.confidence)
        return self.resolve_round(None)

    def get_score(self) -> dict:
        return {
            "type": "score_update",
            "player": self.player_score,
            "computer": self.computer_score,
            "draws": self.draws,
            "round": self.current_round,
        }

    def get_state(self) -> dict:
        return {
            "type": "game_state",
            "state": self.state.value,
            "round": self.current_round,
        }

    def reset(self):
        self.state = GameState.WAITING
        self.player_score = 0
        self.computer_score = 0
        self.draws = 0
        self.current_round = 0
        self.player_move_history.clear()
        self.last_result = None
        self.ai = AIStrategy()
        self.round_active = False
        self.auto_play = False
