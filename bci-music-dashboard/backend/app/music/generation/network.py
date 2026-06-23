from __future__ import annotations


def require_torch():
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required for melody model training and inference") from exc
    return torch


class MelodyTransformer:
    def __new__(cls, *args, **kwargs):
        torch = require_torch()

        class _Model(torch.nn.Module):
            def __init__(self, vocab_size=512, d_model=256, nhead=8, layers=6, max_length=2048, dropout=0.1):
                super().__init__()
                self.config = {
                    "vocab_size": vocab_size,
                    "d_model": d_model,
                    "nhead": nhead,
                    "layers": layers,
                    "max_length": max_length,
                    "dropout": dropout,
                }
                self.token_embedding = torch.nn.Embedding(vocab_size, d_model)
                self.position_embedding = torch.nn.Embedding(max_length, d_model)
                block = torch.nn.TransformerEncoderLayer(
                    d_model=d_model,
                    nhead=nhead,
                    dim_feedforward=d_model * 4,
                    dropout=dropout,
                    batch_first=True,
                    norm_first=True,
                    activation="gelu",
                )
                self.transformer = torch.nn.TransformerEncoder(block, num_layers=layers)
                self.norm = torch.nn.LayerNorm(d_model)
                self.output = torch.nn.Linear(d_model, vocab_size)

            def forward(self, tokens):
                positions = torch.arange(tokens.shape[1], device=tokens.device).unsqueeze(0)
                hidden = self.token_embedding(tokens) + self.position_embedding(positions)
                mask = torch.nn.Transformer.generate_square_subsequent_mask(tokens.shape[1], device=tokens.device)
                hidden = self.transformer(hidden, mask=mask, is_causal=True)
                return self.output(self.norm(hidden))

            @classmethod
            def from_config(inner_cls, config):
                model_config = config.get("model", config)
                return inner_cls(**{
                    key: model_config[key]
                    for key in ("vocab_size", "d_model", "nhead", "layers", "max_length", "dropout")
                    if key in model_config
                })

            @torch.inference_mode()
            def sample(self, prompt, max_new_tokens=384, temperature=0.9, top_k=32):
                tokens = prompt
                for _ in range(max_new_tokens):
                    if tokens.shape[1] >= self.config["max_length"]:
                        break
                    logits = self(tokens)[:, -1, :] / max(0.05, temperature)
                    values, indices = torch.topk(logits, min(top_k, logits.shape[-1]))
                    probabilities = torch.softmax(values, dim=-1)
                    selected = torch.multinomial(probabilities, 1)
                    next_token = indices.gather(-1, selected)
                    tokens = torch.cat([tokens, next_token], dim=1)
                    if int(next_token[0, 0]) == 2:
                        break
                return tokens

        return _Model(*args, **kwargs)

    @staticmethod
    def from_config(config):
        model_config = config.get("model", config)
        return MelodyTransformer(**{
            key: model_config[key]
            for key in ("vocab_size", "d_model", "nhead", "layers", "max_length", "dropout")
            if key in model_config
        })
