"""FastAPI server with REST API and WebSocket for real-time RPS game."""
import base64
import json
import time
import asyncio
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from backend.config import MODEL_PATH, WS_FRAME_QUALITY
from backend.model import YOLOInference, annotate_frame, Prediction
from backend.game_engine import GameEngine, GameState
import backend.database as db

app = FastAPI(title="Rock-Paper-Scissors YOLO")

model: YOLOInference = None
game_engine: GameEngine = None


@app.on_event("startup")
async def startup():
    global model, game_engine
    if MODEL_PATH.exists():
        model = YOLOInference(str(MODEL_PATH))
        print(f"Model loaded from {MODEL_PATH}")
    else:
        print(f"WARNING: Model not found at {MODEL_PATH}. Game detection disabled.")
    game_engine = GameEngine()


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "model_path": str(MODEL_PATH),
        "game_state": game_engine.state.value if game_engine else "uninitialized",
    }


def _format_live_strategy_stats(engine) -> dict:
    """Build strategy_stats from in-memory MetaStrategy accuracies.
    These track ALL candidate strategies every round, not just the selected one.
    """
    result = {}
    if engine and engine.ai:
        acc = engine.ai.meta.get_accuracies()
        for name, val in acc.items():
            dq = engine.ai.meta.scores.get(name)
            total = len(dq) if dq else 0
            result[name] = {"total": total, "accuracy": val}
    return result


@app.get("/api/stats")
async def stats():
    s = db.get_stats()
    s["class_stats"] = db.get_class_stats()
    # Use live in-memory accuracies as primary source (they score ALL strategies)
    s["strategy_stats"] = _format_live_strategy_stats(game_engine)
    s["score"] = {
        "player": game_engine.player_score,
        "computer": game_engine.computer_score,
        "draws": game_engine.draws,
    }
    return s


@app.get("/api/history")
async def history(limit: int = 20):
    return db.get_recent_rounds(limit)


@app.get("/api/state")
async def state():
    if game_engine:
        return {
            "state": game_engine.state.value,
            "round": game_engine.current_round,
            "score": {
                "player": game_engine.player_score,
                "computer": game_engine.computer_score,
                "draws": game_engine.draws,
            },
        }
    return {"state": "unknown"}


@app.post("/api/reset")
async def reset():
    if game_engine:
        game_engine.reset()
    db.reset_history()
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Track game tick loop
    tick_task = None

    async def tick_loop():
        """Send game state updates as countdown progresses."""
        while True:
            try:
                update = game_engine.tick()
                if update:
                    await websocket.send_json(update)
                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception:
                import traceback
                traceback.print_exc()
                # Brief pause then retry so one bad send doesn't kill the countdown
                await asyncio.sleep(0.5)

    try:
        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            msg_type = data.get("type", "")

            if msg_type == "frame":
                if model is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Model not loaded. Train first or check model path.",
                    })
                    continue

                # Decode frame
                frame_b64 = data.get("data", "")
                frame_bytes = base64.b64decode(frame_b64)
                nparr = np.frombuffer(frame_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    continue

                # Run inference
                predictions = model.predict(frame)
                annotated = annotate_frame(frame.copy(), predictions)

                # Encode annotated frame
                _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, WS_FRAME_QUALITY])
                b64_annotated = base64.b64encode(buffer).decode('utf-8')

                await websocket.send_json({
                    "type": "annotated_frame",
                    "data": b64_annotated,
                    "predictions": [
                        {"class_name": p.class_name, "confidence": round(p.confidence, 3),
                         "bbox": p.bbox}
                        for p in predictions
                    ],
                })

                # If in SHOOT state, resolve the round
                if game_engine.state == GameState.SHOOT:
                    result = game_engine.shoot_with_frame_detection(predictions)
                    await websocket.send_json(result)

                    # Send score update
                    await websocket.send_json(game_engine.get_score())

                    # Ensure tick loop is alive.
                    # Auto mode: needed for RESULT → auto-restart.
                    # Manual mode: needed for RESULT → WAITING transition.
                    if tick_task is None or tick_task.done():
                        tick_task = asyncio.create_task(tick_loop())

            elif msg_type == "start_round":
                response = game_engine.start_round()
                await websocket.send_json(response)

                # Start tick loop for countdown
                if tick_task and not tick_task.done():
                    tick_task.cancel()
                tick_task = asyncio.create_task(tick_loop())

            elif msg_type == "reset":
                game_engine.reset()
                db.reset_history()
                await websocket.send_json({"type": "reset_ok"})

            elif msg_type == "get_state":
                await websocket.send_json(game_engine.get_state())

            elif msg_type == "toggle_auto":
                auto_on = game_engine.toggle_auto_play()
                await websocket.send_json({"type": "auto_play", "enabled": auto_on})

                if not auto_on:
                    # Disabling auto: stop tick loop if not needed
                    if tick_task and not tick_task.done():
                        tick_task.cancel()
                    continue

                # Auto enabled — ensure tick_task is running for state transitions
                need_tick = (tick_task is None or tick_task.done())

                if game_engine.state == GameState.WAITING:
                    # Start a new round immediately
                    response = game_engine.start_round()
                    await websocket.send_json(response)
                    if tick_task and not tick_task.done():
                        tick_task.cancel()
                    tick_task = asyncio.create_task(tick_loop())
                elif game_engine.state in (GameState.RESULT, GameState.COUNTDOWN, GameState.SHOOT):
                    # Mid-round: ensure tick_task exists to handle the next transition.
                    # If auto was OFF when the last round resolved, tick_task was
                    # cancelled and we must recreate it for the RESULT→auto-restart path.
                    if need_tick:
                        tick_task = asyncio.create_task(tick_loop())

            elif msg_type == "get_stats":
                s = db.get_stats()
                s["class_stats"] = db.get_class_stats()
                s["strategy_stats"] = _format_live_strategy_stats(game_engine)
                s["score"] = {
                    "player": game_engine.player_score,
                    "computer": game_engine.computer_score,
                    "draws": game_engine.draws,
                }
                s["history"] = db.get_recent_rounds(20)
                await websocket.send_json({"type": "stats", **s})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if tick_task and not tick_task.done():
            tick_task.cancel()


# Serve static frontend
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
