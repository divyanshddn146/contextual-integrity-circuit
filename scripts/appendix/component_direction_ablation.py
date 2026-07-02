"""
component_direction_ablation.py

Goal:
  Convert the final-token D-A direction result into a circuit-level test.

Question:
  Which component writes the causal D-A / violation / No direction?

For each layer L:
  1. Build final-token direction:
       d_L = mean(h_D_resid_post[L, final]) - mean(h_A_resid_post[L, final])
  2. Measure component projection:
       attention_output[L, final] · d_L
       mlp_output[L, final] · d_L
  3. Causally ablate component contribution:
       component_output_new = component_output - alpha * max(component_output · d_L, 0) * d_L
  4. Check whether D prompts flip from No to Yes.

Smoke test:
  python scripts/component_direction_ablation.py \
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \
    --filter-col patch_final_AD \
    --out-dir results/clean304/component_direction_ablation_smoke \
    --dtype float16 \
    --device cuda \
    --layers 18-27 \
    --components attn,mlp,resid_post \
    --alphas 1.0 \
    --modes remove_positive \
    --max-test 10 \
    --max-projection-test 10 \
    --random-controls 1

Full run:
  python scripts/component_direction_ablation.py \
    --seeds data/final/curated_candidate_pool_source_capped_CLEAN304.csv \
    --eligibility data/final/source_capped_CLEAN304_improvement_eligibility.csv \
    --filter-col patch_final_AD \
    --out-dir results/clean304/component_direction_ablation \
    --dtype float16 \
    --device cuda \
    --layers all \
    --components attn,mlp,resid_post \
    --alphas 0.5,1.0,1.5 \
    --modes remove_positive \
    --random-controls 1
"""

from __future__ import annotations

import argparse
import gc
import random
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import torch
from tqdm import tqdm

from ci_dataset import load_seeds, make_variants


CI_MODEL = "huseyinatahaninan/Qwen2.5-7B-Instruct-CI"

YES_VARIANTS = ["Yes", " Yes", "yes", " yes", "YES", " YES"]
NO_VARIANTS = ["No", " No", "no", " no", "NO", " NO"]


def get_yes_no_token_ids(tokenizer) -> Tuple[List[int], List[int]]:
    def collect(words):
        out = []
        for w in words:
            ids = tokenizer.encode(w, add_special_tokens=False)
            if len(ids) == 1:
                out.append(ids[0])
        return list(dict.fromkeys(out))

    yes_ids = collect(YES_VARIANTS)
    no_ids = collect(NO_VARIANTS)
    if not yes_ids or not no_ids:
        raise RuntimeError(f"Could not find one-token Yes/No IDs: yes={yes_ids}, no={no_ids}")
    return yes_ids, no_ids


def yes_no_margin(logits_last, yes_ids: List[int], no_ids: List[int]):
    yes_logit = max(logits_last[i].item() for i in yes_ids)
    no_logit = max(logits_last[i].item() for i in no_ids)
    margin = yes_logit - no_logit
    decision = "Yes" if margin > 0 else "No"
    return float(yes_logit), float(no_logit), float(margin), decision


def get_input_device(model):
    return model.get_input_embeddings().weight.device


def get_decoder_layers(model):
    if hasattr(model, "model") and hasattr(model.model, "layers"):
        return model.model.layers
    if hasattr(model, "transformer") and hasattr(model.transformer, "h"):
        return model.transformer.h
    raise RuntimeError("Could not find transformer decoder layers.")


def get_attn_module(layer_module):
    for name in ["self_attn", "attn", "attention"]:
        if hasattr(layer_module, name):
            return getattr(layer_module, name)
    raise RuntimeError("Could not find attention module inside decoder layer.")


def get_mlp_module(layer_module):
    for name in ["mlp", "feed_forward", "ffn"]:
        if hasattr(layer_module, name):
            return getattr(layer_module, name)
    raise RuntimeError("Could not find MLP module inside decoder layer.")


def load_model_and_tokenizer(model_id: str, device: str, dtype):
    from transformers import AutoTokenizer, AutoModelForCausalLM

    print(f"Loading tokenizer: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)

    print(f"Loading model: {model_id}")
    if device == "cuda":
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=dtype,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        )
        model = model.to(device)

    model.eval()
    print("Model loaded.")
    print("Input device:", get_input_device(model))
    print("Number of layers:", len(get_decoder_layers(model)))
    return model, tokenizer


def parse_layers(layer_arg: str, n_layers: int) -> List[int]:
    if layer_arg == "all":
        return list(range(n_layers))
    if "-" in layer_arg:
        a, b = layer_arg.split("-")
        layers = list(range(int(a), int(b) + 1))
    else:
        layers = [int(x.strip()) for x in layer_arg.split(",") if x.strip()]
    bad = [x for x in layers if x < 0 or x >= n_layers]
    if bad:
        raise ValueError(f"Invalid layers {bad}. Model has layers 0..{n_layers - 1}")
    return layers


def parse_csv_list(x: str) -> List[str]:
    return [p.strip() for p in x.split(",") if p.strip()]


def parse_float_list(x: str) -> List[float]:
    return [float(p.strip()) for p in x.split(",") if p.strip()]


def normalize_rows(x: torch.Tensor, eps: float = 1e-8):
    return x / (x.norm(dim=-1, keepdim=True) + eps)


def filter_seeds_by_eligibility(seeds: pd.DataFrame, eligibility_path: str, filter_col: str):
    elig = pd.read_csv(eligibility_path)
    if "scenario_id" not in elig.columns:
        raise ValueError("Eligibility file must contain scenario_id column.")
    if filter_col not in elig.columns:
        raise ValueError(
            f"Column {filter_col} not found in eligibility file.\n"
            f"Available columns: {list(elig.columns)}"
        )

    keep_ids = set(
        elig.loc[elig[filter_col].astype(bool), "scenario_id"].astype(int).tolist()
    )
    out = seeds[seeds["scenario_id"].astype(int).isin(keep_ids)].copy()
    print(f"Eligibility filter: {filter_col}")
    print(f"Kept scenarios: {len(out)} / {len(seeds)}")
    if len(out) < 20:
        raise RuntimeError("Too few scenarios after eligibility filtering.")
    return out


def split_train_test(sids: List[int], train_frac: float, seed: int):
    rng = random.Random(seed)
    sids = list(sids)
    rng.shuffle(sids)
    n_train = int(round(len(sids) * train_frac))
    train_sids = sorted(sids[:n_train])
    test_sids = sorted(sids[n_train:])
    return train_sids, test_sids


@torch.no_grad()
def forward_collect_resid_post_hiddens(model, tokenizer, text: str, yes_ids, no_ids):
    input_device = get_input_device(model)
    enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
    input_ids = enc["input_ids"].to(input_device)

    out = model(input_ids=input_ids, output_hidden_states=True, use_cache=False)

    # hidden_states[0] = embedding output
    # hidden_states[1:] = residual stream after each decoder layer
    hidden_by_layer = torch.stack(
        [h[0, -1, :].detach().float().cpu() for h in out.hidden_states[1:]],
        dim=0,
    )

    logits_last = out.logits[0, -1, :]
    y, n, margin, decision = yes_no_margin(logits_last, yes_ids, no_ids)
    return hidden_by_layer, {
        "yes_logit": y,
        "no_logit": n,
        "margin": margin,
        "decision": decision,
        "prompt_len_tokens": int(input_ids.shape[1]),
    }


def collect_A_D_cache(model, tokenizer, seeds: pd.DataFrame, yes_ids, no_ids):
    cache: Dict[int, Dict[str, Dict]] = {}
    for _, row in tqdm(seeds.iterrows(), total=len(seeds), desc="Collecting A/D residual states"):
        sid = int(row["scenario_id"])
        variants = make_variants(row, tokenizer=tokenizer)
        if "A" not in variants or "D" not in variants:
            raise RuntimeError(f"Scenario {sid} missing A or D variant.")

        cache[sid] = {}
        for version in ["A", "D"]:
            variant = variants[version]
            hidden, info = forward_collect_resid_post_hiddens(
                model=model,
                tokenizer=tokenizer,
                text=variant.text,
                yes_ids=yes_ids,
                no_ids=no_ids,
            )
            cache[sid][version] = {
                "hidden": hidden,
                "text": variant.text,
                "expected": variant.expected,
                "condition": variant.condition,
                "margin": info["margin"],
                "decision": info["decision"],
                "yes_logit": info["yes_logit"],
                "no_logit": info["no_logit"],
                "prompt_len_tokens": info["prompt_len_tokens"],
            }
    return cache


def build_D_minus_A_directions(cache: Dict[int, Dict], train_sids: List[int]):
    A = torch.stack([cache[sid]["A"]["hidden"] for sid in train_sids], dim=0)
    D = torch.stack([cache[sid]["D"]["hidden"] for sid in train_sids], dim=0)
    A_mean = A.mean(dim=0)
    D_mean = D.mean(dim=0)
    directions = normalize_rows(D_mean - A_mean)
    mus = torch.cat([A, D], dim=0).mean(dim=0)
    return directions, mus


def _extract_hidden_from_module_output(output):
    if isinstance(output, tuple):
        return output[0]
    return output


@torch.no_grad()
def capture_component_final_outputs(model, tokenizer, text: str,
                                    layers_to_run: List[int],
                                    components: List[str]):
    decoder_layers = get_decoder_layers(model)
    input_device = get_input_device(model)
    captured: Dict[Tuple[str, int], torch.Tensor] = {}
    handles = []

    def make_hook(component_name: str, layer_idx: int):
        def hook(module, inputs, output):
            hidden = _extract_hidden_from_module_output(output)
            captured[(component_name, layer_idx)] = hidden[0, -1, :].detach().float().cpu()
            return output
        return hook

    for L in layers_to_run:
        layer_module = decoder_layers[L]
        if "attn" in components:
            handles.append(get_attn_module(layer_module).register_forward_hook(make_hook("attn", L)))
        if "mlp" in components:
            handles.append(get_mlp_module(layer_module).register_forward_hook(make_hook("mlp", L)))
        if "resid_post" in components:
            handles.append(layer_module.register_forward_hook(make_hook("resid_post", L)))

    try:
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        input_ids = enc["input_ids"].to(input_device)
        _ = model(input_ids=input_ids, use_cache=False)
    finally:
        for h in handles:
            h.remove()
    return captured


def run_component_projection_scan(model, tokenizer, cache, test_sids,
                                  directions, layers_to_run, components,
                                  max_projection_test=None):
    sids_eval = test_sids[:max_projection_test] if max_projection_test is not None else test_sids
    rows = []
    for sid in tqdm(sids_eval, desc="Component projection scan"):
        for version in ["A", "D"]:
            captured = capture_component_final_outputs(
                model=model,
                tokenizer=tokenizer,
                text=cache[sid][version]["text"],
                layers_to_run=layers_to_run,
                components=components,
            )
            for (component, L), vec in captured.items():
                d = directions[L]
                score = float(vec @ d)
                rows.append({
                    "scenario_id": sid,
                    "version": version,
                    "component": component,
                    "layer": L,
                    "projection_onto_DA_direction": score,
                })

    detail_df = pd.DataFrame(rows)
    summary_rows = []
    for (component, L), g in detail_df.groupby(["component", "layer"]):
        gA = g[g["version"] == "A"]
        gD = g[g["version"] == "D"]
        summary_rows.append({
            "component": component,
            "layer": int(L),
            "n_A": len(gA),
            "n_D": len(gD),
            "A_projection_mean": gA["projection_onto_DA_direction"].mean(),
            "D_projection_mean": gD["projection_onto_DA_direction"].mean(),
            "D_minus_A_projection_gap": (
                gD["projection_onto_DA_direction"].mean()
                - gA["projection_onto_DA_direction"].mean()
            ),
        })
    summary_df = pd.DataFrame(summary_rows)
    return detail_df, summary_df


def make_component_direction_ablation_hook(component: str,
                                           direction_cpu: torch.Tensor,
                                           mu_cpu: torch.Tensor,
                                           alpha: float,
                                           mode: str):
    assert component in {"attn", "mlp", "resid_post"}
    assert mode in {"remove_positive", "remove_signed"}

    def hook(module, inputs, output):
        if isinstance(output, tuple):
            hidden = output[0]
            rest = output[1:]
            tuple_output = True
        else:
            hidden = output
            rest = None
            tuple_output = False

        d = direction_cpu.to(device=hidden.device, dtype=hidden.dtype)
        mu = mu_cpu.to(device=hidden.device, dtype=hidden.dtype)
        h_final = hidden[:, -1, :]

        # For resid_post, remove the centered projection of the residual state.
        # For attn/mlp, remove direct positive contribution written by that component.
        base_vec = h_final - mu if component == "resid_post" else h_final
        coeff = (base_vec * d).sum(dim=-1, keepdim=True)
        if mode == "remove_positive":
            coeff = torch.clamp(coeff, min=0.0)

        new_final = h_final - alpha * coeff * d
        hidden_new = hidden.clone()
        hidden_new[:, -1, :] = new_final

        if tuple_output:
            return (hidden_new,) + rest
        return hidden_new

    return hook


def register_component_hook(model, layer_idx: int, component: str, hook_fn):
    layer_module = get_decoder_layers(model)[layer_idx]
    if component == "attn":
        return get_attn_module(layer_module).register_forward_hook(hook_fn)
    if component == "mlp":
        return get_mlp_module(layer_module).register_forward_hook(hook_fn)
    if component == "resid_post":
        return layer_module.register_forward_hook(hook_fn)
    raise RuntimeError(f"Unknown component: {component}")


@torch.no_grad()
def forward_with_component_ablation(model, tokenizer, text: str,
                                    yes_ids, no_ids,
                                    layer: int,
                                    component: str,
                                    direction: torch.Tensor,
                                    mu: torch.Tensor,
                                    alpha: float,
                                    mode: str):
    hook_fn = make_component_direction_ablation_hook(
        component=component,
        direction_cpu=direction,
        mu_cpu=mu,
        alpha=alpha,
        mode=mode,
    )
    handle = register_component_hook(model, layer, component, hook_fn)
    try:
        input_device = get_input_device(model)
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        input_ids = enc["input_ids"].to(input_device)
        out = model(input_ids=input_ids, use_cache=False)
        logits_last = out.logits[0, -1, :]
        y, n, margin, decision = yes_no_margin(logits_last, yes_ids, no_ids)
        return {
            "yes_logit": y,
            "no_logit": n,
            "margin": margin,
            "decision": decision,
            "prompt_len_tokens": int(input_ids.shape[1]),
        }
    finally:
        handle.remove()


def random_unit_vector_like(d: torch.Tensor, seed: int):
    gen = torch.Generator(device="cpu")
    gen.manual_seed(seed)
    r = torch.randn(d.shape, generator=gen)
    return r / (r.norm() + 1e-8)


def run_component_ablation(model, tokenizer, cache, test_sids,
                           directions, mus, layers_to_run,
                           components, alphas, modes,
                           yes_ids, no_ids,
                           random_controls: int,
                           max_test=None):
    sids_eval = test_sids[:max_test] if max_test is not None else test_sids
    detail_rows = []
    jobs = [(L, component, mode, alpha)
            for L in layers_to_run
            for component in components
            for mode in modes
            for alpha in alphas]

    for L, component, mode, alpha in tqdm(jobs, desc="Component ablations"):
        d = directions[L]
        mu = mus[L]

        # Real D-A direction.
        for sid in sids_eval:
            normal_margin = float(cache[sid]["D"]["margin"])
            normal_decision = cache[sid]["D"]["decision"]
            out = forward_with_component_ablation(
                model=model,
                tokenizer=tokenizer,
                text=cache[sid]["D"]["text"],
                yes_ids=yes_ids,
                no_ids=no_ids,
                layer=L,
                component=component,
                direction=d,
                mu=mu,
                alpha=alpha,
                mode=mode,
            )
            detail_rows.append({
                "layer": L,
                "component": component,
                "mode": mode,
                "alpha": alpha,
                "scenario_id": sid,
                "control_type": "real_direction",
                "normal_margin": normal_margin,
                "intervened_margin": float(out["margin"]),
                "delta_toward_yes": float(out["margin"]) - normal_margin,
                "normal_decision": normal_decision,
                "intervened_decision": out["decision"],
                "no_to_yes_flip": normal_decision == "No" and out["decision"] == "Yes",
            })

        # Random controls.
        for rc in range(random_controls):
            rd = random_unit_vector_like(d, seed=500_000 + 10_000 * L + 100 * rc)
            for sid in sids_eval:
                normal_margin = float(cache[sid]["D"]["margin"])
                normal_decision = cache[sid]["D"]["decision"]
                out = forward_with_component_ablation(
                    model=model,
                    tokenizer=tokenizer,
                    text=cache[sid]["D"]["text"],
                    yes_ids=yes_ids,
                    no_ids=no_ids,
                    layer=L,
                    component=component,
                    direction=rd,
                    mu=mu,
                    alpha=alpha,
                    mode=mode,
                )
                detail_rows.append({
                    "layer": L,
                    "component": component,
                    "mode": mode,
                    "alpha": alpha,
                    "scenario_id": sid,
                    "control_type": f"random_direction_{rc}",
                    "normal_margin": normal_margin,
                    "intervened_margin": float(out["margin"]),
                    "delta_toward_yes": float(out["margin"]) - normal_margin,
                    "normal_decision": normal_decision,
                    "intervened_decision": out["decision"],
                    "no_to_yes_flip": normal_decision == "No" and out["decision"] == "Yes",
                })

    detail_df = pd.DataFrame(detail_rows)
    summary_rows = []
    for (component, L, mode, alpha, control_type), g in detail_df.groupby(
        ["component", "layer", "mode", "alpha", "control_type"]
    ):
        summary_rows.append({
            "component": component,
            "layer": int(L),
            "mode": mode,
            "alpha": float(alpha),
            "control_type": control_type,
            "n": int(len(g)),
            "normal_margin_mean": g["normal_margin"].mean(),
            "intervened_margin_mean": g["intervened_margin"].mean(),
            "delta_toward_yes_mean": g["delta_toward_yes"].mean(),
            "no_to_yes_flips": int(g["no_to_yes_flip"].sum()),
            "no_to_yes_flip_rate": g["no_to_yes_flip"].mean(),
        })
    summary_df = pd.DataFrame(summary_rows)
    return detail_df, summary_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--eligibility", required=True)
    parser.add_argument("--filter-col", default="patch_final_AD")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--model", default=CI_MODEL)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu", choices=["cuda", "cpu"])
    parser.add_argument("--dtype", default="float16", choices=["bfloat16", "float16", "float32"])
    parser.add_argument("--train-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--layers", default="all", help="all, 18-27, or comma list like 20,21,22")
    parser.add_argument("--components", default="attn,mlp,resid_post", help="comma list from: attn,mlp,resid_post")
    parser.add_argument("--alphas", default="1.0", help="comma list, e.g. 0.5,1.0,1.5")
    parser.add_argument("--modes", default="remove_positive", help="comma list from: remove_positive,remove_signed")
    parser.add_argument("--random-controls", type=int, default=1)
    parser.add_argument("--max-test", type=int, default=None)
    parser.add_argument("--max-projection-test", type=int, default=None,
                        help="Optional smaller sample for component projection scan.")
    args = parser.parse_args()

    dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[args.dtype]

    components = parse_csv_list(args.components)
    valid_components = {"attn", "mlp", "resid_post"}
    bad_components = [c for c in components if c not in valid_components]
    if bad_components:
        raise ValueError(f"Bad components: {bad_components}. Valid: {valid_components}")

    modes = parse_csv_list(args.modes)
    valid_modes = {"remove_positive", "remove_signed"}
    bad_modes = [m for m in modes if m not in valid_modes]
    if bad_modes:
        raise ValueError(f"Bad modes: {bad_modes}. Valid: {valid_modes}")

    alphas = parse_float_list(args.alphas)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("COMPONENT-WISE DIRECTION ABLATION")
    print("=" * 80)

    print("\nLoading seeds...")
    seeds = load_seeds(args.seeds)

    print("\nFiltering seeds...")
    seeds = filter_seeds_by_eligibility(seeds, args.eligibility, args.filter_col)

    sids = sorted(seeds["scenario_id"].astype(int).tolist())
    train_sids, test_sids = split_train_test(sids, args.train_frac, args.seed)
    print(f"\nTrain scenarios: {len(train_sids)}")
    print(f"Test scenarios:  {len(test_sids)}")

    pd.DataFrame({
        "scenario_id": train_sids + test_sids,
        "split": ["train"] * len(train_sids) + ["test"] * len(test_sids),
    }).to_csv(out_dir / "split.csv", index=False)

    model, tokenizer = load_model_and_tokenizer(args.model, args.device, dtype)
    n_layers = len(get_decoder_layers(model))
    layers_to_run = parse_layers(args.layers, n_layers)

    print(f"\nLayers to run: {layers_to_run}")
    print(f"Components: {components}")
    print(f"Modes: {modes}")
    print(f"Alphas: {alphas}")

    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)
    print("Yes token IDs:", yes_ids)
    print("No token IDs:", no_ids)

    print("\nCollecting A/D residual states for direction construction...")
    cache = collect_A_D_cache(model, tokenizer, seeds, yes_ids, no_ids)

    print("\nBuilding D-A residual directions...")
    directions, mus = build_D_minus_A_directions(cache, train_sids)

    torch.save(
        {
            "directions": directions,
            "mus": mus,
            "train_sids": train_sids,
            "test_sids": test_sids,
            "layers_to_run": layers_to_run,
            "components": components,
            "modes": modes,
            "alphas": alphas,
            "filter_col": args.filter_col,
        },
        out_dir / "directions_and_mus.pt",
    )

    print("\nRunning component projection scan...")
    proj_detail, proj_summary = run_component_projection_scan(
        model=model,
        tokenizer=tokenizer,
        cache=cache,
        test_sids=test_sids,
        directions=directions,
        layers_to_run=layers_to_run,
        components=components,
        max_projection_test=args.max_projection_test,
    )
    proj_detail.to_csv(out_dir / "component_projection_detail.csv", index=False)
    proj_summary.to_csv(out_dir / "component_projection_summary.csv", index=False)

    print("\nRunning component-wise causal ablation...")
    abl_detail, abl_summary = run_component_ablation(
        model=model,
        tokenizer=tokenizer,
        cache=cache,
        test_sids=test_sids,
        directions=directions,
        mus=mus,
        layers_to_run=layers_to_run,
        components=components,
        alphas=alphas,
        modes=modes,
        yes_ids=yes_ids,
        no_ids=no_ids,
        random_controls=args.random_controls,
        max_test=args.max_test,
    )
    abl_detail.to_csv(out_dir / "component_ablation_detail.csv", index=False)
    abl_summary.to_csv(out_dir / "component_ablation_summary.csv", index=False)

    print("\nSaved:")
    print(" ", out_dir / "split.csv")
    print(" ", out_dir / "directions_and_mus.pt")
    print(" ", out_dir / "component_projection_detail.csv")
    print(" ", out_dir / "component_projection_summary.csv")
    print(" ", out_dir / "component_ablation_detail.csv")
    print(" ", out_dir / "component_ablation_summary.csv")

    real = abl_summary[abl_summary["control_type"] == "real_direction"].copy()
    print("\nTop component ablations by No->Yes flip rate:")
    if len(real):
        print(
            real.sort_values(["no_to_yes_flip_rate", "delta_toward_yes_mean"], ascending=False)
            .head(30)
            .to_string(index=False)
        )

    print("\nTop component projection gaps D-A:")
    if len(proj_summary):
        print(
            proj_summary.sort_values("D_minus_A_projection_gap", ascending=False)
            .head(30)
            .to_string(index=False)
        )

    del model, tokenizer
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
