"""Run the vendored Maia-3 engine with move probabilities in UCI info."""
import json
from pathlib import Path
import os
import sys

import torch
from torch.amp import autocast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "maia3"))
os.environ.setdefault("HF_HOME", str(ROOT / "data" / "maia-cache"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from maia3.dataset import get_legal_moves_mask  # noqa: E402
from maia3.uci import Maia3UCIEngine, parse_args, seed_everything  # noqa: E402


class PolicyUCIEngine(Maia3UCIEngine):
    @torch.no_grad()
    def move_policy(self):
        # One policy pass evaluates all legal moves. The value head on the
        # resulting positions isn't needed when matching Stockfish candidates.
        legal_mask = get_legal_moves_mask(self.board, self.all_moves_dict)
        count = int(legal_mask.sum().item())
        if not count:
            return {}
        tokens = self._tokens_from_history(self.history).unsqueeze(0).to(self.cfg.device)
        self_elo = torch.tensor([self.self_elo], device=self.cfg.device)
        opponent_elo = torch.tensor([self.oppo_elo], device=self.cfg.device)
        with autocast("cuda", enabled=self.cfg.use_amp and self.cfg.device.startswith("cuda")):
            logits, _, _ = self.model(tokens, self_elo, opponent_elo)
        logits = logits[0].float().masked_fill(~legal_mask.to(logits.device), float("-inf"))
        probabilities, indexes = torch.softmax(logits, dim=-1).topk(count)
        policy = {}
        for index, probability in zip(indexes.tolist(), probabilities.tolist()):
            move = self._move_from_index(index)
            if move is not None:
                policy[move] = probability
        return policy

    def cmd_go(self, line):
        self.ensure_model_loaded()
        policy = self.move_policy()
        serialized = {move.uci(): probability for move, probability in policy.items()}
        print("info string maia_policy " + json.dumps(serialized, separators=(",", ":")), flush=True)
        for rank, move in enumerate(list(policy)[:self.multipv], 1):
            print(f"info depth 1 multipv {rank} pv {move.uci()}", flush=True)
        top_move = next(iter(policy), None)
        if "infinite" in line.split():
            self.pending_bestmove = top_move
            self.pending_search = True
        else:
            self.print_bestmove(top_move)


if __name__ == "__main__":
    config = parse_args()
    torch.set_num_threads(max(1, int(os.environ.get("MAIA_THREADS", "2"))))
    seed_everything(config.seed)
    PolicyUCIEngine(config).run()
