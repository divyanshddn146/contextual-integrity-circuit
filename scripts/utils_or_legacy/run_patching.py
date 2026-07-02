#!/usr/bin/env python
"""
run_patching.py

Comprehensive activation patching runner for the CI patching pilot.

Runs:
  1. Final-token patching:
       A↔D = full allowed/disallowed decision
       A↔B = recipient-only final decision
       A↔C = purpose-only final decision

  2. Slot last-token patching:
       recipient-last A↔B
       purpose-last A↔C
       recipient-last + purpose-last A↔D

  3. Strict-span patching:
       recipient-span A↔B
       purpose-span A↔C
       recipient-span + purpose-span A↔D

  4. Controls:
       self final-token patch
       sender-last control
       information-last control

Inputs:
  - data/processed/manual_seed_selection.csv
  - data/patching_eligibility.csv
  - scripts/ci_dataset.py

Outputs:
  - results/patching_results.csv
  - results/patching_summary_by_layer.csv
  - results/patching_peaks.csv

Example smoke test:
  python scripts/run_patching.py \
    --seeds data/processed/manual_seed_selection.csv \
    --eligibility data/patching_eligibility.csv \
    --base-only \
    --layers 0,8,16,24,31 \
    --max-scenarios 2 \
    --experiments final_AD,recipient_last_AB,purpose_last_AC \
    --dtype float16

Example full run:
  python scripts/run_patching.py \
    --seeds data/processed/manual_seed_selection.csv \
    --eligibility data/patching_eligibility.csv \
    --layers all \
    --dtype float16
"""

from __future__ import annotations

import argparse
import gc
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Optional

import pandas as pd
import torch
from tqdm import tqdm

from ci_dataset import load_seeds, build_tokenized_scenario


BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
CI_MODEL = "huseyinatahaninan/Qwen2.5-7B-Instruct-CI"

YES_VARIANTS = ["Yes", " Yes", "yes", " yes", "YES", " YES"]
NO_VARIANTS = ["No", " No", "no", " no", "NO", " NO"]


# -------------------------------------------------------------------------
# Utility: Yes/No margin
# -------------------------------------------------------------------------

def get_yes_no_token_ids(tokenizer):
    def collect(words):
        out = []
        for w in words:
            ids = tokenizer.encode(w, add_special_tokens=False)
            if len(ids) == 1:
                out.append(ids[0])
        return list(dict.fromkeys(out))

    yes_ids = collect(YES_VARIANTS)
    no_ids = collect(NO_VARIANTS)

    if len(yes_ids) == 0 or len(no_ids) == 0:
        raise ValueError(f"Could not find single-token Yes/No IDs. yes={yes_ids}, no={no_ids}")

    return yes_ids, no_ids


def yes_no_margin(logits_last, yes_ids, no_ids):
    yes_max = max(logits_last[i].item() for i in yes_ids)
    no_max = max(logits_last[i].item() for i in no_ids)
    return yes_max, no_max, yes_max - no_max


def decision_from_margin(margin: float) -> str:
    return "Yes" if margin > 0 else "No"


def expected_direction(source_expected: str, target_expected: str) -> int:
    """
    +1 means patch should increase Yes-No margin.
    -1 means patch should decrease Yes-No margin.
     0 means same expected label / control / ambiguous.
    """
    if source_expected == "Yes" and target_expected == "No":
        return +1
    if source_expected == "No" and target_expected == "Yes":
        return -1
    return 0


# -------------------------------------------------------------------------
# Model/layer helpers
# -------------------------------------------------------------------------

def get_decoder_layers(model):
    """
    Qwen2.5 CausalLM uses model.model.layers.
    This helper also supports common fallback names.
    """
    if hasattr(model, "model") and hasattr(model.model, "layers"):
        return model.model.layers
    if hasattr(model, "transformer") and hasattr(model.transformer, "h"):
        return model.transformer.h
    if hasattr(model, "gpt_neox") and hasattr(model.gpt_neox, "layers"):
        return model.gpt_neox.layers

    raise ValueError("Could not locate decoder layers on this model.")


def first_param_device(model):
    return next(model.parameters()).device


def parse_layers(layer_spec: str, n_layers: int) -> List[int]:
    """
    Supports:
      all
      0,1,2
      0-31
      0:32:2
    """
    if layer_spec == "all":
        return list(range(n_layers))

    layers = []
    for part in layer_spec.split(","):
        part = part.strip()
        if not part:
            continue

        if ":" in part:
            bits = [int(x) if x else None for x in part.split(":")]
            if len(bits) == 2:
                start, stop = bits
                step = 1
            elif len(bits) == 3:
                start, stop, step = bits
            else:
                raise ValueError(f"Bad layer slice: {part}")
            start = 0 if start is None else start
            stop = n_layers if stop is None else stop
            step = 1 if step is None else step
            layers.extend(list(range(start, stop, step)))

        elif "-" in part:
            a, b = part.split("-")
            layers.extend(list(range(int(a), int(b) + 1)))

        else:
            layers.append(int(part))

    layers = sorted(set(layers))
    bad = [l for l in layers if l < 0 or l >= n_layers]
    if bad:
        raise ValueError(f"Layer(s) out of range 0..{n_layers - 1}: {bad}")

    return layers


# -------------------------------------------------------------------------
# Slot span helpers for sender/information controls
# -------------------------------------------------------------------------

def _find_slot_chars(prompt: str, label: str, value: str) -> Tuple[int, int]:
    anchor = f"{label}: {value}\n"
    first = prompt.find(anchor)
    if first == -1:
        raise ValueError(f"Anchor not found: {anchor!r}")
    if prompt.find(anchor, first + 1) != -1:
        raise ValueError(f"Anchor occurs more than once: {anchor!r}")
    value_start = first + len(label) + 2
    value_end = value_start + len(value)
    return value_start, value_end


def _char_to_token_range(offsets: List[Tuple[int, int]], char_start: int, char_end: int) -> Tuple[int, int]:
    matches = [
        i for i, (cs, ce) in enumerate(offsets)
        if cs != ce and ce > char_start and cs < char_end
    ]
    if not matches:
        raise ValueError(f"No tokens cover characters [{char_start}, {char_end})")
    return matches[0], matches[-1] + 1


def label_token_span(text: str, tokenizer, label: str, value: str) -> Tuple[int, int]:
    enc = tokenizer(text, return_offsets_mapping=True, add_special_tokens=False)
    offsets = enc["offset_mapping"]
    cs, ce = _find_slot_chars(text, label, value)
    return _char_to_token_range(offsets, cs, ce)


def make_position_dict(tokenized_prompt, tokenizer) -> Dict[str, List[int]]:
    """
    Position names used by patch specs.
    """
    tp = tokenized_prompt
    text = tp.variant.text

    sender_start, sender_end = label_token_span(text, tokenizer, "Sender", tp.variant.sender)
    info_start, info_end = label_token_span(text, tokenizer, "Information", tp.variant.information)

    return {
        "final": [tp.final_answer_idx],

        "recipient_last": [tp.recipient_last_idx],
        "purpose_last": [tp.purpose_last_idx],
        "sender_last": [sender_end - 1],
        "information_last": [info_end - 1],

        "recipient_span": list(range(tp.recipient_token_start, tp.recipient_token_end)),
        "purpose_span": list(range(tp.purpose_token_start, tp.purpose_token_end)),
        "sender_span": list(range(sender_start, sender_end)),
        "information_span": list(range(info_start, info_end)),
    }


# -------------------------------------------------------------------------
# Patch specifications
# -------------------------------------------------------------------------

@dataclass(frozen=True)
class PatchSpec:
    experiment: str
    patch_family: str
    source_version: str
    target_version: str
    source_sites: Tuple[str, ...]
    target_sites: Tuple[str, ...]
    eligibility_cols: Tuple[str, ...]
    is_control: bool = False


def build_patch_specs(include_controls: bool) -> List[PatchSpec]:
    specs: List[PatchSpec] = []

    # ----------------------------
    # Final-token patching
    # ----------------------------
    for name, v1, v2, flag in [
        ("final_AD", "A", "D", "patch_final_AD"),
        ("final_AB", "A", "B", "both_clean_AB"),
        ("final_AC", "A", "C", "both_clean_AC"),
    ]:
        specs.append(PatchSpec(
            experiment=f"{name}_{v1}_to_{v2}",
            patch_family=name,
            source_version=v1,
            target_version=v2,
            source_sites=("final",),
            target_sites=("final",),
            eligibility_cols=(flag,),
        ))
        specs.append(PatchSpec(
            experiment=f"{name}_{v2}_to_{v1}",
            patch_family=name,
            source_version=v2,
            target_version=v1,
            source_sites=("final",),
            target_sites=("final",),
            eligibility_cols=(flag,),
        ))

    # ----------------------------
    # Slot last-token patching
    # Does not require length matching.
    # ----------------------------
    specs.extend([
        PatchSpec(
            experiment="recipient_last_AB_A_to_B",
            patch_family="recipient_last_AB",
            source_version="A",
            target_version="B",
            source_sites=("recipient_last",),
            target_sites=("recipient_last",),
            eligibility_cols=("patch_recipient_AB_lasttok", "both_clean_AB"),
        ),
        PatchSpec(
            experiment="recipient_last_AB_B_to_A",
            patch_family="recipient_last_AB",
            source_version="B",
            target_version="A",
            source_sites=("recipient_last",),
            target_sites=("recipient_last",),
            eligibility_cols=("patch_recipient_AB_lasttok", "both_clean_AB"),
        ),
        PatchSpec(
            experiment="purpose_last_AC_A_to_C",
            patch_family="purpose_last_AC",
            source_version="A",
            target_version="C",
            source_sites=("purpose_last",),
            target_sites=("purpose_last",),
            eligibility_cols=("patch_purpose_AC_lasttok", "both_clean_AC"),
        ),
        PatchSpec(
            experiment="purpose_last_AC_C_to_A",
            patch_family="purpose_last_AC",
            source_version="C",
            target_version="A",
            source_sites=("purpose_last",),
            target_sites=("purpose_last",),
            eligibility_cols=("patch_purpose_AC_lasttok", "both_clean_AC"),
        ),
        PatchSpec(
            experiment="both_last_AD_A_to_D",
            patch_family="both_last_AD",
            source_version="A",
            target_version="D",
            source_sites=("recipient_last", "purpose_last"),
            target_sites=("recipient_last", "purpose_last"),
            eligibility_cols=("patch_final_AD", "both_clean_AD"),
        ),
        PatchSpec(
            experiment="both_last_AD_D_to_A",
            patch_family="both_last_AD",
            source_version="D",
            target_version="A",
            source_sites=("recipient_last", "purpose_last"),
            target_sites=("recipient_last", "purpose_last"),
            eligibility_cols=("patch_final_AD", "both_clean_AD"),
        ),
    ])

    # ----------------------------
    # Strict-span patching
    # Requires source/target span lengths to match.
    # ----------------------------
    specs.extend([
        PatchSpec(
            experiment="recipient_span_AB_A_to_B",
            patch_family="recipient_span_AB",
            source_version="A",
            target_version="B",
            source_sites=("recipient_span",),
            target_sites=("recipient_span",),
            eligibility_cols=("patch_recipient_AB_strictspan",),
        ),
        PatchSpec(
            experiment="recipient_span_AB_B_to_A",
            patch_family="recipient_span_AB",
            source_version="B",
            target_version="A",
            source_sites=("recipient_span",),
            target_sites=("recipient_span",),
            eligibility_cols=("patch_recipient_AB_strictspan",),
        ),
        PatchSpec(
            experiment="purpose_span_AC_A_to_C",
            patch_family="purpose_span_AC",
            source_version="A",
            target_version="C",
            source_sites=("purpose_span",),
            target_sites=("purpose_span",),
            eligibility_cols=("patch_purpose_AC_strictspan",),
        ),
        PatchSpec(
            experiment="purpose_span_AC_C_to_A",
            patch_family="purpose_span_AC",
            source_version="C",
            target_version="A",
            source_sites=("purpose_span",),
            target_sites=("purpose_span",),
            eligibility_cols=("patch_purpose_AC_strictspan",),
        ),
        PatchSpec(
            experiment="both_span_AD_A_to_D",
            patch_family="both_span_AD",
            source_version="A",
            target_version="D",
            source_sites=("recipient_span", "purpose_span"),
            target_sites=("recipient_span", "purpose_span"),
            eligibility_cols=("patch_both_AD_strictspan",),
        ),
        PatchSpec(
            experiment="both_span_AD_D_to_A",
            patch_family="both_span_AD",
            source_version="D",
            target_version="A",
            source_sites=("recipient_span", "purpose_span"),
            target_sites=("recipient_span", "purpose_span"),
            eligibility_cols=("patch_both_AD_strictspan",),
        ),
    ])

    # ----------------------------
    # Controls
    # ----------------------------
    if include_controls:
        specs.extend([
            PatchSpec(
                experiment="control_self_final_A_to_A",
                patch_family="control_self_final",
                source_version="A",
                target_version="A",
                source_sites=("final",),
                target_sites=("final",),
                eligibility_cols=("patch_final_AD", "both_clean_AD"),
                is_control=True,
            ),
            PatchSpec(
                experiment="control_self_final_D_to_D",
                patch_family="control_self_final",
                source_version="D",
                target_version="D",
                source_sites=("final",),
                target_sites=("final",),
                eligibility_cols=("patch_final_AD", "both_clean_AD"),
                is_control=True,
            ),
            PatchSpec(
                experiment="control_sender_last_AD_A_to_D",
                patch_family="control_sender_last_AD",
                source_version="A",
                target_version="D",
                source_sites=("sender_last",),
                target_sites=("sender_last",),
                eligibility_cols=("patch_final_AD", "both_clean_AD"),
                is_control=True,
            ),
            PatchSpec(
                experiment="control_info_last_AD_A_to_D",
                patch_family="control_information_last_AD",
                source_version="A",
                target_version="D",
                source_sites=("information_last",),
                target_sites=("information_last",),
                eligibility_cols=("patch_final_AD", "both_clean_AD"),
                is_control=True,
            ),
        ])

    return specs


def row_has_any_flag(row: pd.Series, candidates: Iterable[str]) -> bool:
    """
    Some files may use patch_* columns, some may only have both_clean_*.
    This helper accepts any matching candidate column.
    """
    for col in candidates:
        if col in row.index:
            return bool(row[col])
    raise KeyError(f"None of these eligibility columns exist: {list(candidates)}")


def filter_specs(specs: List[PatchSpec], experiment_arg: str) -> List[PatchSpec]:
    if experiment_arg == "all":
        return specs

    wanted = {x.strip() for x in experiment_arg.split(",") if x.strip()}
    out = []
    for s in specs:
        if s.patch_family in wanted or s.experiment in wanted:
            out.append(s)

    if not out:
        valid = sorted({s.patch_family for s in specs} | {s.experiment for s in specs})
        raise ValueError(f"No experiments matched {wanted}. Valid names include:\n{valid}")

    return out


# -------------------------------------------------------------------------
# Activation extraction and patching
# -------------------------------------------------------------------------

@dataclass
class CachedPrompt:
    scenario_id: int
    version: str
    expected: str
    input_ids: List[int]
    positions: Dict[str, List[int]]
    yes_logit: float
    no_logit: float
    margin: float
    decision: str
    activations: Dict[str, Dict[int, torch.Tensor]]
    prompt_len: int


def concat_positions(positions: Dict[str, List[int]], sites: Tuple[str, ...]) -> List[int]:
    out: List[int] = []
    for site in sites:
        if site not in positions:
            raise KeyError(f"Unknown site {site}. Available: {list(positions.keys())}")
        out.extend(positions[site])
    return out


def concat_activations(
    activation_cache: Dict[str, Dict[int, torch.Tensor]],
    sites: Tuple[str, ...],
    layer: int,
) -> torch.Tensor:
    chunks = []
    for site in sites:
        if site not in activation_cache:
            raise KeyError(f"Unknown activation site {site}. Available: {list(activation_cache.keys())}")
        chunks.append(activation_cache[site][layer])
    return torch.cat(chunks, dim=0)


def extract_prompt_cache(
    model,
    tokenizer,
    tokenized_prompt,
    layers_to_run: List[int],
    yes_ids: List[int],
    no_ids: List[int],
) -> CachedPrompt:
    positions = make_position_dict(tokenized_prompt, tokenizer)
    input_ids_list = tokenized_prompt.input_ids

    device = first_param_device(model)
    input_ids = torch.tensor([input_ids_list], dtype=torch.long, device=device)

    with torch.no_grad():
        out = model(
            input_ids=input_ids,
            output_hidden_states=True,
            use_cache=False,
        )

    logits_last = out.logits[0, -1, :]
    y, n, m = yes_no_margin(logits_last, yes_ids, no_ids)

    hidden_states = out.hidden_states
    activations: Dict[str, Dict[int, torch.Tensor]] = {}

    for site_name, idxs in positions.items():
        activations[site_name] = {}
        for layer in layers_to_run:
            # hidden_states[0] = embeddings; hidden_states[layer+1] = output after layer
            h = hidden_states[layer + 1][0, idxs, :].detach().to("cpu")
            activations[site_name][layer] = h

    del out
    return CachedPrompt(
        scenario_id=tokenized_prompt.variant.scenario_id,
        version=tokenized_prompt.variant.version,
        expected=tokenized_prompt.variant.expected,
        input_ids=input_ids_list,
        positions=positions,
        yes_logit=float(y),
        no_logit=float(n),
        margin=float(m),
        decision=decision_from_margin(float(m)),
        activations=activations,
        prompt_len=len(input_ids_list),
    )


def run_patched_forward(
    model,
    layers,
    target_input_ids: List[int],
    layer_idx: int,
    source_activation_cpu: torch.Tensor,
    target_positions: List[int],
    yes_ids: List[int],
    no_ids: List[int],
) -> Tuple[float, float, float]:
    """
    Patch output of decoder layer `layer_idx` at target positions.
    Source activation shape must be [n_positions, hidden_dim].
    """
    if len(target_positions) != source_activation_cpu.shape[0]:
        raise ValueError(
            f"Patch length mismatch: target positions={len(target_positions)}, "
            f"source activations={source_activation_cpu.shape[0]}"
        )

    device = first_param_device(model)
    input_ids = torch.tensor([target_input_ids], dtype=torch.long, device=device)

    def hook_fn(module, module_inputs, module_output):
        if isinstance(module_output, tuple):
            hidden = module_output[0]
            rest = module_output[1:]
            patched = hidden.clone()
            src = source_activation_cpu.to(device=patched.device, dtype=patched.dtype)
            idx = torch.tensor(target_positions, dtype=torch.long, device=patched.device)
            patched[0, idx, :] = src
            return (patched,) + rest
        else:
            hidden = module_output
            patched = hidden.clone()
            src = source_activation_cpu.to(device=patched.device, dtype=patched.dtype)
            idx = torch.tensor(target_positions, dtype=torch.long, device=patched.device)
            patched[0, idx, :] = src
            return patched

    handle = layers[layer_idx].register_forward_hook(hook_fn)
    try:
        with torch.no_grad():
            out = model(input_ids=input_ids, use_cache=False)
        logits_last = out.logits[0, -1, :]
        y, n, m = yes_no_margin(logits_last, yes_ids, no_ids)
        del out
        return float(y), float(n), float(m)
    finally:
        handle.remove()


# -------------------------------------------------------------------------
# Model-level runner
# -------------------------------------------------------------------------

def load_model_and_tokenizer(model_id: str, dtype, device: str):
    from transformers import AutoTokenizer, AutoModelForCausalLM

    print(f"\nLoading tokenizer: {model_id}")
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
    return model, tokenizer


def build_all_prompt_caches(
    model,
    tokenizer,
    seeds_df: pd.DataFrame,
    layers_to_run: List[int],
    yes_ids: List[int],
    no_ids: List[int],
) -> Dict[Tuple[int, str], CachedPrompt]:
    """
    For each scenario A/B/C/D, cache:
      - clean margin
      - selected source activations for every layer
      - token positions
    """
    cache: Dict[Tuple[int, str], CachedPrompt] = {}

    pbar = tqdm(total=len(seeds_df) * 4, desc="Caching clean activations", unit="prompt")
    for _, row in seeds_df.iterrows():
        tok_scenario = build_tokenized_scenario(row, tokenizer)
        for v in ["A", "B", "C", "D"]:
            tp = tok_scenario[v]
            cache[(int(row["scenario_id"]), v)] = extract_prompt_cache(
                model=model,
                tokenizer=tokenizer,
                tokenized_prompt=tp,
                layers_to_run=layers_to_run,
                yes_ids=yes_ids,
                no_ids=no_ids,
            )
            pbar.update(1)
    pbar.close()
    return cache


def run_model_patching(
    model_id: str,
    seeds_df: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    specs: List[PatchSpec],
    layers_arg: str,
    dtype,
    device: str,
    max_scenarios: Optional[int],
) -> pd.DataFrame:
    model_short = model_id.split("/")[-1]

    model, tokenizer = load_model_and_tokenizer(model_id, dtype=dtype, device=device)
    yes_ids, no_ids = get_yes_no_token_ids(tokenizer)
    print(f"Yes token IDs: {yes_ids}")
    print(f"No token IDs:  {no_ids}")

    decoder_layers = get_decoder_layers(model)
    n_layers = len(decoder_layers)
    layers_to_run = parse_layers(layers_arg, n_layers)
    print(f"Model layers: {n_layers}")
    print(f"Running layers: {layers_to_run}")

    # Restrict seeds to those present in eligibility file.
    eligibility_df = eligibility_df.copy()
    eligibility_df["scenario_id"] = eligibility_df["scenario_id"].astype(int)
    elig_by_sid = {int(r["scenario_id"]): r for _, r in eligibility_df.iterrows()}

    valid_sids = sorted(set(seeds_df["scenario_id"].astype(int)) & set(elig_by_sid.keys()))
    if max_scenarios is not None:
        valid_sids = valid_sids[:max_scenarios]

    seeds_run = seeds_df[seeds_df["scenario_id"].astype(int).isin(valid_sids)].copy()
    print(f"Scenarios available for this run: {len(seeds_run)}")

    # Cache clean activations and margins.
    prompt_cache = build_all_prompt_caches(
        model=model,
        tokenizer=tokenizer,
        seeds_df=seeds_run,
        layers_to_run=layers_to_run,
        yes_ids=yes_ids,
        no_ids=no_ids,
    )

    rows = []

    # Count total patch jobs for progress.
    jobs = []
    for _, seed in seeds_run.iterrows():
        sid = int(seed["scenario_id"])
        erow = elig_by_sid[sid]
        for spec in specs:
            try:
                ok = row_has_any_flag(erow, spec.eligibility_cols)
            except KeyError:
                ok = False
            if ok:
                jobs.append((sid, spec))

    total_for_pbar = len(jobs) * len(layers_to_run)
    pbar = tqdm(total=total_for_pbar, desc=f"Patching {model_short}", unit="patch")

    for sid, spec in jobs:
        source_key = (sid, spec.source_version)
        target_key = (sid, spec.target_version)

        source = prompt_cache[source_key]
        target = prompt_cache[target_key]

        source_positions = concat_positions(source.positions, spec.source_sites)
        target_positions = concat_positions(target.positions, spec.target_sites)

        # Strict safety check. Last-token/final patches are also one-to-one here.
        if len(source_positions) != len(target_positions):
            print(
                f"SKIP length mismatch sid={sid} exp={spec.experiment}: "
                f"source_positions={len(source_positions)}, target_positions={len(target_positions)}"
            )
            pbar.update(len(layers_to_run))
            continue

        exp_dir = expected_direction(source.expected, target.expected)

        for layer in layers_to_run:
            src_act = concat_activations(source.activations, spec.source_sites, layer)

            patched_y, patched_n, patched_m = run_patched_forward(
                model=model,
                layers=decoder_layers,
                target_input_ids=target.input_ids,
                layer_idx=layer,
                source_activation_cpu=src_act,
                target_positions=target_positions,
                yes_ids=yes_ids,
                no_ids=no_ids,
            )

            effect = patched_m - target.margin
            aligned_effect = effect * exp_dir if exp_dir != 0 else effect

            rows.append({
                "model": model_id,
                "model_short": model_short,
                "scenario_id": sid,
                "experiment": spec.experiment,
                "patch_family": spec.patch_family,
                "is_control": spec.is_control,
                "layer": layer,

                "source_version": spec.source_version,
                "target_version": spec.target_version,
                "source_expected": source.expected,
                "target_expected": target.expected,
                "expected_direction": exp_dir,

                "source_sites": "+".join(spec.source_sites),
                "target_sites": "+".join(spec.target_sites),
                "n_patched_tokens": len(target_positions),

                "source_margin": source.margin,
                "target_original_margin": target.margin,
                "patched_margin": patched_m,
                "patch_effect": effect,
                "aligned_effect": aligned_effect,

                "source_decision": source.decision,
                "target_original_decision": target.decision,
                "patched_decision": decision_from_margin(patched_m),

                "source_yes_logit": source.yes_logit,
                "source_no_logit": source.no_logit,
                "target_original_yes_logit": target.yes_logit,
                "target_original_no_logit": target.no_logit,
                "patched_yes_logit": patched_y,
                "patched_no_logit": patched_n,

                "source_prompt_len": source.prompt_len,
                "target_prompt_len": target.prompt_len,
            })

            pbar.update(1)

    pbar.close()

    del model, tokenizer, prompt_cache
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()

    return pd.DataFrame(rows)


# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------

def summarize_results(results: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if len(results) == 0:
        return pd.DataFrame(), pd.DataFrame()

    summary = (
        results
        .groupby(["model", "model_short", "patch_family", "experiment", "layer"], as_index=False)
        .agg(
            n=("scenario_id", "nunique"),
            mean_patch_effect=("patch_effect", "mean"),
            median_patch_effect=("patch_effect", "median"),
            mean_aligned_effect=("aligned_effect", "mean"),
            median_aligned_effect=("aligned_effect", "median"),
            mean_abs_effect=("patch_effect", lambda x: x.abs().mean()),
            flip_rate=("patched_decision", lambda x: float("nan")),
        )
    )

    # Add flip rate manually: target decision changed after patch.
    flip_rows = []
    for keys, g in results.groupby(["model", "model_short", "patch_family", "experiment", "layer"]):
        flip_rate = (g["patched_decision"] != g["target_original_decision"]).mean()
        flip_rows.append((*keys, flip_rate))
    flip_df = pd.DataFrame(
        flip_rows,
        columns=["model", "model_short", "patch_family", "experiment", "layer", "flip_rate_real"],
    )
    summary = summary.drop(columns=["flip_rate"]).merge(
        flip_df,
        on=["model", "model_short", "patch_family", "experiment", "layer"],
        how="left",
    ).rename(columns={"flip_rate_real": "flip_rate"})

    # Peak by mean aligned effect for interpretable directional experiments.
    peak_rows = []
    for keys, g in summary.groupby(["model", "model_short", "patch_family", "experiment"]):
        # For controls, aligned_effect may be arbitrary, so also keep abs peak.
        idx_aligned = g["mean_aligned_effect"].abs().idxmax()
        idx_abs = g["mean_abs_effect"].idxmax()

        pa = g.loc[idx_aligned]
        pb = g.loc[idx_abs]
        peak_rows.append({
            "model": keys[0],
            "model_short": keys[1],
            "patch_family": keys[2],
            "experiment": keys[3],

            "peak_layer_by_abs_aligned": int(pa["layer"]),
            "peak_mean_patch_effect_at_that_layer": float(pa["mean_patch_effect"]),
            "peak_mean_aligned_effect": float(pa["mean_aligned_effect"]),
            "peak_flip_rate_at_that_layer": float(pa["flip_rate"]),
            "n_at_peak": int(pa["n"]),

            "peak_layer_by_mean_abs_effect": int(pb["layer"]),
            "peak_mean_abs_effect": float(pb["mean_abs_effect"]),
        })

    peaks = pd.DataFrame(peak_rows)
    return summary, peaks


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run CI activation patching experiments.")

    parser.add_argument("--seeds", default="data/processed/manual_seed_selection.csv")
    parser.add_argument("--eligibility", default="data/patching_eligibility.csv")

    parser.add_argument("--out-detail", default="results/patching_results.csv")
    parser.add_argument("--out-summary", default="results/patching_summary_by_layer.csv")
    parser.add_argument("--out-peaks", default="results/patching_peaks.csv")

    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--ci-model", default=CI_MODEL)
    parser.add_argument("--base-only", action="store_true")

    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu",
                        choices=["cuda", "cpu"])
    parser.add_argument("--dtype", default="float16",
                        choices=["float16", "bfloat16", "float32"])

    parser.add_argument("--layers", default="all",
                        help="all, comma list e.g. 0,8,16, or range 0-31, or slice 0:32:2")

    parser.add_argument("--experiments", default="all",
                        help=(
                            "all or comma list of patch_family / experiment names. "
                            "Examples: final_AD,recipient_last_AB,purpose_last_AC,both_span_AD"
                        ))

    parser.add_argument("--include-controls", action="store_true",
                        help="Run self-patch and unchanged-field controls.")
    parser.add_argument("--max-scenarios", type=int, default=None,
                        help="Smoke-test on first N scenarios after eligibility matching.")

    args = parser.parse_args()

    dtype = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[args.dtype]

    print("=" * 80)
    print("CI PATCHING RUN")
    print("=" * 80)
    print(f"Device:       {args.device}")
    print(f"dtype:        {args.dtype}")
    print(f"seeds:        {args.seeds}")
    print(f"eligibility:  {args.eligibility}")
    print(f"layers:       {args.layers}")
    print(f"experiments:  {args.experiments}")
    print(f"controls:     {args.include_controls}")
    print()

    if args.device == "cuda":
        print(f"CUDA device: {torch.cuda.get_device_name(0)} "
              f"({torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB)")
        print()

    seeds_df = load_seeds(args.seeds)
    eligibility_df = pd.read_csv(args.eligibility)

    all_specs = build_patch_specs(include_controls=args.include_controls)
    specs = filter_specs(all_specs, args.experiments)

    print("Patch specs to run:")
    for s in specs:
        print(f"  - {s.experiment:35s}  {s.source_version}->{s.target_version}  "
              f"{'+'.join(s.source_sites)} -> {'+'.join(s.target_sites)}")
    print()

    models = [args.base_model]
    if not args.base_only:
        models.append(args.ci_model)

    all_results = []
    for model_id in models:
        df = run_model_patching(
            model_id=model_id,
            seeds_df=seeds_df,
            eligibility_df=eligibility_df,
            specs=specs,
            layers_arg=args.layers,
            dtype=dtype,
            device=args.device,
            max_scenarios=args.max_scenarios,
        )
        all_results.append(df)

    results = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()

    Path(args.out_detail).parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out_detail, index=False)
    print(f"\nSaved detailed patching results: {args.out_detail} ({len(results)} rows)")

    summary, peaks = summarize_results(results)
    summary.to_csv(args.out_summary, index=False)
    peaks.to_csv(args.out_peaks, index=False)

    print(f"Saved layer summary:            {args.out_summary} ({len(summary)} rows)")
    print(f"Saved peak summary:             {args.out_peaks} ({len(peaks)} rows)")

    print("\n" + "=" * 80)
    print("QUICK PEAK VIEW")
    print("=" * 80)
    if len(peaks):
        cols = [
            "model_short",
            "experiment",
            "peak_layer_by_abs_aligned",
            "peak_mean_aligned_effect",
            "peak_flip_rate_at_that_layer",
            "n_at_peak",
        ]
        print(peaks[cols].to_string(index=False))
    else:
        print("No peak rows produced.")

    print("\nDone.")


if __name__ == "__main__":
    main()