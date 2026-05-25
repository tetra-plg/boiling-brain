#!/usr/bin/env python3
"""
backfill-summaries.py — Backfill summary_l0 / summary_l1 sur les pages wiki.

Pour chaque page wiki/**/*.md sans summary_l0 :
  1. Lit la page
  2. Invoque `claude --print --model claude-haiku-4-5-20251001 --output-format json`
  3. Parse la réponse JSON {"l0", "l1"}
  4. Insère les deux champs dans le frontmatter YAML (préserve le formatting)
  5. Logue dans cache/backfill-summaries.log

Idempotent : skip les pages déjà munies de summary_l0 (sauf --force).
"""

import argparse
import datetime as dt
import glob
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "cache"
LOG_FILE = LOG_DIR / "backfill-summaries.log"
FAIL_FILE = LOG_DIR / "backfill-failed.log"

MODEL = "claude-haiku-4-5-20251001"
PROMPT_TEMPLATE = """Tu lis une page d'un wiki LLM. Produis exactement deux champs :
- summary_l0 : UNE seule ligne, 140 caractères MAX, ton télégraphique, scannable, sans saut de ligne, sans retour à la ligne. Donne le sujet net.
- summary_l1 : 2-5 phrases, ~50-150 mots, description structurée du contenu. Pas d'hallucination — base-toi strictement sur la page.

Réponds en JSON STRICT, AUCUN autre texte avant ou après :
{{"l0": "...", "l1": "..."}}

Page à résumer :

---
{page_content}
---
"""


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def log_fail(path: Path, reason: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().isoformat(timespec="seconds")
    with FAIL_FILE.open("a") as f:
        f.write(f"[{ts}] {path}\t{reason}\n")


FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def split_frontmatter(content: str):
    """Returns (frontmatter_text, body_text) or (None, content) if no frontmatter."""
    m = FRONT_RE.match(content)
    if not m:
        return None, content
    fm = m.group(1)
    body = content[m.end():]
    return fm, body


def has_summary_l0(frontmatter: str) -> bool:
    return bool(re.search(r"^summary_l0\s*:", frontmatter, re.MULTILINE))


def call_claude(page_content: str, retries: int = 1) -> tuple[str, str] | None:
    """Returns (l0, l1) or None on failure."""
    prompt = PROMPT_TEMPLATE.format(page_content=page_content)

    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                ["claude", "--print", "--model", MODEL, "--output-format", "json"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log(f"  timeout (tentative {attempt + 1})")
            continue

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:300]
            log(f"  claude exit={proc.returncode}: {err}")
            continue

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            log(f"  envelope JSON invalide (tentative {attempt + 1})")
            continue

        if envelope.get("is_error"):
            log(f"  claude is_error: {envelope.get('result', '')[:200]}")
            continue

        result_text = envelope.get("result", "").strip()
        # Le modèle peut entourer son JSON de markdown — extraire le bloc
        result_text = re.sub(r"^```(?:json)?\s*", "", result_text)
        result_text = re.sub(r"\s*```$", "", result_text)

        try:
            parsed = json.loads(result_text)
        except json.JSONDecodeError:
            # Tenter d'extraire un objet JSON via regex
            m = re.search(r"\{.*\}", result_text, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except json.JSONDecodeError:
                    log(f"  result JSON invalide (tentative {attempt + 1})")
                    continue
            else:
                log(f"  result sans objet JSON (tentative {attempt + 1})")
                continue

        l0 = parsed.get("l0")
        l1 = parsed.get("l1")
        if not isinstance(l0, str) or not isinstance(l1, str):
            log(f"  champs l0/l1 manquants ou non-string")
            continue

        l0 = l0.strip().replace("\n", " ").replace("\r", "")
        l1 = l1.strip()

        if len(l0) > 140:
            if attempt < retries:
                log(f"  l0 trop long ({len(l0)} chars), retry")
                continue
            # Tronquer en dernier recours
            l0 = l0[:137] + "..."
            log(f"  l0 tronqué (était {len(parsed['l0'])} chars)")

        return l0, l1

    return None


def yaml_escape_l0(text: str) -> str:
    """Escape pour valeur scalaire YAML inline (entre guillemets doubles)."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def format_summary_block(l0: str, l1: str) -> str:
    """Format les deux champs en YAML, summary_l1 en literal block scalar."""
    l0_escaped = yaml_escape_l0(l0)
    # Indenter l1 pour le block scalar (2 espaces sous le |)
    l1_lines = l1.split("\n")
    l1_indented = "\n".join(f"  {line}" if line else "" for line in l1_lines)
    return f'summary_l0: "{l0_escaped}"\nsummary_l1: |\n{l1_indented}'


def insert_summaries(content: str, l0: str, l1: str) -> str:
    """Insère summary_l0 / summary_l1 juste avant la fermeture du frontmatter."""
    m = FRONT_RE.match(content)
    if not m:
        raise ValueError("Frontmatter introuvable")

    frontmatter = m.group(1).rstrip()
    block = format_summary_block(l0, l1)

    new_fm = f"{frontmatter}\n{block}\n"
    rest = content[m.end():]
    return f"---\n{new_fm}---\n{rest}"


def expand_paths(args_paths: list[str]) -> list[Path]:
    """Étend les arguments en liste de fichiers .md."""
    if not args_paths:
        return sorted((ROOT / "wiki").rglob("*.md"))

    paths: list[Path] = []
    for arg in args_paths:
        p = Path(arg)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_dir():
            paths.extend(sorted(p.rglob("*.md")))
        elif p.is_file():
            paths.append(p)
        else:
            # Glob
            matches = sorted(Path(g) for g in glob.glob(str(p)))
            if not matches:
                log(f"!! aucun fichier ne correspond à {arg}")
            paths.extend(matches)
    return paths


def process_page(path: Path, force: bool, dry_run: bool) -> str:
    """Returns one of: 'done', 'skipped', 'no-frontmatter', 'too-short', 'failed'."""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        log_fail(path, f"read error: {e}")
        return "failed"

    fm, body = split_frontmatter(content)
    if fm is None:
        log(f"  pas de frontmatter — skip ({path.relative_to(ROOT)})")
        return "no-frontmatter"

    if not force and has_summary_l0(fm):
        return "skipped"

    body_lines = [l for l in body.splitlines() if l.strip()]
    if len(body_lines) < 10:
        log(f"  body trop court ({len(body_lines)} lignes non-vides) — skip ({path.relative_to(ROOT)})")
        return "too-short"

    if dry_run:
        log(f"  DRY-RUN traiterait {path.relative_to(ROOT)}")
        return "done"

    # Limiter la taille en input pour éviter de saturer (rare)
    page_content = content
    if len(page_content) > 60_000:
        page_content = page_content[:60_000] + "\n[...tronqué...]"

    t0 = time.time()
    result = call_claude(page_content)
    dt_ms = int((time.time() - t0) * 1000)

    if result is None:
        log(f"  ÉCHEC ({dt_ms}ms) {path.relative_to(ROOT)}")
        log_fail(path, "claude call failed")
        return "failed"

    l0, l1 = result

    try:
        new_content = insert_summaries(content, l0, l1)
    except Exception as e:
        log_fail(path, f"insert error: {e}")
        return "failed"

    path.write_text(new_content, encoding="utf-8")
    log(f"  OK ({dt_ms}ms) l0={len(l0)}c l1={len(l1)}c {path.relative_to(ROOT)}")
    return "done"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="Régénère même si summary_l0 existe déjà")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit rien, affiche juste les pages qui seraient traitées")
    parser.add_argument("paths", nargs="*",
                        help="Fichiers, dossiers ou globs (défaut : wiki/**/*.md)")
    args = parser.parse_args()

    paths = expand_paths(args.paths)
    log(f"=== backfill-summaries: {len(paths)} pages à examiner ===")

    counts = {"done": 0, "skipped": 0, "no-frontmatter": 0, "too-short": 0, "failed": 0}
    t_start = time.time()
    consecutive_failures = 0
    aborted = False

    for i, path in enumerate(paths, 1):
        if i % 25 == 0:
            log(f"--- progression : {i}/{len(paths)} ({counts}) ---")
        status = process_page(path, force=args.force, dry_run=args.dry_run)
        counts[status] = counts.get(status, 0) + 1

        if status == "failed":
            consecutive_failures += 1
            if consecutive_failures >= 3:
                log("!! 3 échecs consécutifs — arrêt anticipé (rate limit Claude probable).")
                log("!! Relance le même script plus tard : il est idempotent et reprendra où il s'est arrêté.")
                aborted = True
                break
        else:
            consecutive_failures = 0

    elapsed = int(time.time() - t_start)
    log(f"=== {'INTERROMPU' if aborted else 'terminé'} en {elapsed}s : {counts} ===")

    if counts["failed"] > 0:
        log(f"!! {counts['failed']} échecs — voir {FAIL_FILE.relative_to(ROOT)}")
    if aborted or counts["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
