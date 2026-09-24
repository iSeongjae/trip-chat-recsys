#!/usr/bin/env python3
"""일본 음식점 카테고리 분류 CLI.

1차: 이름 + OSM 태그만 보고 few-shot 분류 (GPT-5 nano)
2차: 1차에서 conf=low 이거나 unknown 인 가게만 네이버 블로그 검색 snippet 을 붙여 재분류

few-shot 은 fewshot.jsonl 만 바꿔 끼우면 되고, 프롬프트/예시가 바뀌면 캐시 키(prompt hash)가
바뀌어서 자동으로 다시 분류된다. 블로그 본문은 저장하지 않고 카테고리와 참고 URL 만 남긴다.

사용 예:
  python classify.py estimate --input shops.csv
  python classify.py run      --input gold_100.csv --out gold_pred.jsonl --refine
  python classify.py eval     --gold gold_100.csv --pred gold_pred.jsonl
  python classify.py batch-submit  --input shops.csv
  python classify.py batch-collect --out labels.jsonl
  python classify.py refine   --input shops.csv --out labels.jsonl

입력 CSV 컬럼: id, name, tags (필수) / area (선택: 시·구 이름. 없으면 tags 의 addr:city 등에서 추출)
환경변수: OPENAI_API_KEY, (2차용) NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
"""
import argparse, csv, hashlib, html, json, os, re, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

MODEL = "gpt-5-nano"
EFFORT = "minimal"     # --effort 로 변경 가능: minimal / low / medium / high
CHUNK = 25            # 1차: 한 요청당 가게 수
REFINE_CHUNK = 8      # 2차: snippet 이 길어서 적게 묶음
SNIPPETS = 4          # 2차: 가게당 블로그 결과 수
PRICE = {"in": 0.05, "cached_in": 0.005, "out": 0.40}   # $/1M tokens (gpt-5-nano, 일반 호출). Batch 는 절반
STATE = ".classify_state.json"


# ---------------------------------------------------------------- prompt
def load_prompt(prompt_path, fewshot_path):
    rules = open(prompt_path, encoding="utf-8").read().split("## Examples")[0].rstrip()
    cats = re.findall(r"^([a-z_]+):", rules, flags=re.M)
    shots = [json.loads(l) for l in open(fewshot_path, encoding="utf-8") if l.strip()]
    bad = [s for s in shots if s.get("cat") not in cats]
    if bad:
        sys.exit(f"few-shot 에 카테고리 목록에 없는 코드가 있어요: {[s.get('cat') for s in bad]}")
    lines = [f'{json.dumps({k: s[k] for k in ("id", "name", "tags")}, ensure_ascii=False)} -> {s["cat"]}' for s in shots]
    system = (rules + "\n\n## Examples\n" + "\n".join(lines) +
              "\n\n## Output\nReturn every input id exactly once. conf is high only if the name, a tag, or the evidence clearly shows the type.")
    phash = hashlib.sha1(system.encode()).hexdigest()[:10]
    cover = Counter(s["cat"] for s in shots)
    return system, cats, phash, cover


def schema(cats, with_evidence=False):
    item = {"id": {"type": "string"}, "cat": {"type": "string", "enum": cats},
            "conf": {"type": "string", "enum": ["high", "low"]}}
    req = ["id", "cat", "conf"]
    if with_evidence:
        item["evidence"] = {"type": "integer", "description": "근거로 쓴 snippet 번호, 없으면 -1"}
        req.append("evidence")
    return {"type": "object", "additionalProperties": False, "required": ["results"],
            "properties": {"results": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": req, "properties": item}}}}


REFINE_NOTE = ("\n\n## Evidence mode\nSome shops come with blog search snippets (Korean or Japanese). "
               "Use a snippet ONLY if it clearly talks about the same shop in the same area. "
               "Set evidence to the snippet number you relied on, or -1. "
               "If the snippets are about other shops or say nothing about the food, answer unknown.")


def body(system, cats, shops, model, refine=False):
    if refine:
        user = "\n\n".join(
            json.dumps({k: s[k] for k in ("id", "name", "tags")}, ensure_ascii=False) + "\n" +
            ("\n".join(f"  [{i}] {t}" for i, t in enumerate(s.get("snips", []))) or "  (no search results)")
            for s in shops)
    else:
        user = "\n".join(json.dumps({k: s[k] for k in ("id", "name", "tags")}, ensure_ascii=False) for s in shops)
    return {"model": model, "reasoning_effort": EFFORT,
            "messages": [{"role": "system", "content": system + (REFINE_NOTE if refine else "")},
                         {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "labels", "strict": True, "schema": schema(cats, refine)}}}


# ---------------------------------------------------------------- io
def read_shops(path):
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["id"], r["name"], r["tags"] = str(r["id"]), r.get("name", ""), r.get("tags", "") or ""
        if not r.get("area"):
            m = re.search(r"addr:(?:city|suburb|province)=([^;,\s]+)", r["tags"])
            r["area"] = m.group(1) if m else ""
    return rows


def read_labels(path, phash=None):
    """id -> 마지막 라벨. phash 가 주어지면 같은 프롬프트로 만든 것만."""
    out = {}
    if os.path.exists(path):
        for l in open(path, encoding="utf-8"):
            if l.strip():
                d = json.loads(l)
                if phash is None or d.get("phash") == phash:
                    out[d["id"]] = d
    return out


def append_labels(path, recs):
    with open(path, "a", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def chunks(xs, n):
    return [xs[i:i + n] for i in range(0, len(xs), n)]


# ---------------------------------------------------------------- openai
def client():
    from openai import OpenAI
    return OpenAI()


def call(cl, b, tries=5):
    for t in range(tries):
        try:
            r = cl.chat.completions.create(**b)
            return json.loads(r.choices[0].message.content)["results"], r.usage
        except Exception as e:           # 레이트리밋·일시 오류는 재시도
            if t == tries - 1:
                raise
            print(f"  재시도 {t + 1}: {str(e)[:120]}", file=sys.stderr)
            time.sleep(2 ** t)


def collect(ids_expected, results, extra):
    """모델 응답을 기록용 레코드로. 빠지거나 모르는 id 는 버린다(다음 실행에서 다시 시도됨)."""
    ok = set(ids_expected)
    return [{"id": x["id"], "cat": x["cat"], "conf": x["conf"], **extra(x)} for x in results if x["id"] in ok]


def run_sync(cl, system, cats, phash, shops, out, model, refine=False, workers=4):
    groups = chunks(shops, REFINE_CHUNK if refine else CHUNK)
    usage = Counter()

    def job(g):
        res, u = call(cl, body(system, cats, g, model, refine))
        by = {s["id"]: s for s in g}

        def extra(x):
            e = {"stage": 2 if refine else 1, "phash": phash, "model": model}
            if refine:
                i = x.get("evidence", -1)
                urls = by[x["id"]].get("urls", [])
                e["evidence_url"] = urls[i] if 0 <= i < len(urls) else ""
            return e
        return collect([s["id"] for s in g], res, extra), u

    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for recs, u in ex.map(job, groups):
            append_labels(out, recs)
            done += len(recs)
            if u is not None:
                usage["in"] += getattr(u, "prompt_tokens", 0)
                usage["out"] += getattr(u, "completion_tokens", 0)
                cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
                usage["cached"] += cached
    cost = ((usage["in"] - usage["cached"]) * PRICE["in"] + usage["cached"] * PRICE["cached_in"] + usage["out"] * PRICE["out"]) / 1e6
    print(f"{'2차' if refine else '1차'} 완료: {done}/{len(shops)}개 | 토큰 in {usage['in']:,} (캐시 {usage['cached']:,}) out {usage['out']:,} | 약 ${cost:.4f}")


# ---------------------------------------------------------------- naver blog search
def blog_search(query, n=SNIPPETS):
    import urllib.parse, urllib.request
    url = "https://openapi.naver.com/v1/search/blog.json?" + urllib.parse.urlencode({"query": query, "display": n})
    req = urllib.request.Request(url, headers={"X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
                                               "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"]})
    with urllib.request.urlopen(req, timeout=10) as r:
        items = json.load(r).get("items", [])
    clean = lambda t: html.unescape(re.sub(r"<[^>]+>", "", t))
    return [clean(i["title"]) + " / " + clean(i["description"])[:160] for i in items], [i["link"] for i in items]


def attach_snippets(shops, search=blog_search, pause=0.12):
    """검색 결과는 메모리에서만 쓰고 저장하지 않는다."""
    for s in shops:
        snips, urls = [], []
        for q in ([f'{s["name"]} {s["area"]}'.strip()] + ([s["name"]] if s["area"] else [])):
            try:
                snips, urls = search(q)
            except Exception as e:
                print(f"  검색 실패 {s['id']}: {str(e)[:80]}", file=sys.stderr)
            if snips:
                break
            time.sleep(pause)
        s["snips"], s["urls"] = snips, urls
        time.sleep(pause)
    return shops


# ---------------------------------------------------------------- commands
def cmd_estimate(a, system, cats, phash, cover):
    shops = read_shops(a.input)
    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base"); tok = lambda t: len(enc.encode(t))
    except Exception:
        tok = lambda t: int(len(t) / 1.6)          # tiktoken 없을 때 대략치
    sys_t = tok(system)
    per = sum(tok(json.dumps({k: s[k] for k in ("id", "name", "tags")}, ensure_ascii=False)) for s in shops[:500]) / max(1, min(500, len(shops)))
    n = len(shops); calls = -(-n // CHUNK)
    inp = calls * sys_t + n * per; cached = calls * sys_t * 0.9; out = n * 18 + calls * 40
    full = (inp * PRICE["in"] + out * PRICE["out"]) / 1e6
    withcache = ((inp - cached) * PRICE["in"] + cached * PRICE["cached_in"] + out * PRICE["out"]) / 1e6
    print(f"카테고리 {len(cats)}개 | few-shot {sum(cover.values())}개 (예시 없는 카테고리: {[c for c in cats if c not in cover] or '없음'})")
    print(f"고정 프롬프트 {sys_t:,} tok | 가게당 {per:.0f} tok | {n:,}개 → {calls:,}회 호출")
    print(f"1차 예상 비용: 일반 ${full:.2f} / 캐시 적중 시 ${withcache:.2f} / Batch 약 ${full / 2:.2f}")
    r2 = int(n * a.refine_ratio)
    ref = (-(-r2 // REFINE_CHUNK) * sys_t + r2 * (per + SNIPPETS * 90)) * PRICE["in"] / 1e6 + r2 * 20 * PRICE["out"] / 1e6
    print(f"2차(가정: {a.refine_ratio:.0%} = {r2:,}개 블로그 검색) 예상 비용: 약 ${ref:.2f} + 네이버 검색 {r2 * 2:,}회 이내")


def cmd_run(a, system, cats, phash, cover):
    shops = read_shops(a.input)
    have = read_labels(a.out, phash)
    todo = [s for s in shops if s["id"] not in have]
    print(f"프롬프트 {phash} | 전체 {len(shops)} / 이미 분류 {len(shops) - len(todo)} / 이번 {len(todo)}")
    cl = a._client or client()
    if todo:
        run_sync(cl, system, cats, phash, todo, a.out, a.model)
    if a.refine:
        cmd_refine(a, system, cats, phash, cover, cl=cl)


def cmd_refine(a, system, cats, phash, cover, cl=None):
    shops = {s["id"]: s for s in read_shops(a.input)}
    labs = read_labels(a.out, phash)
    todo = [shops[i] for i, d in labs.items()
            if i in shops and d["stage"] == 1 and (d["conf"] == "low" or d["cat"] == "unknown")]
    if a.limit:
        todo = todo[:a.limit]
    print(f"2차 대상: {len(todo)}개 (conf=low 또는 unknown)")
    if not todo:
        return
    attach_snippets(todo, search=a._search or blog_search)
    run_sync(cl or a._client or client(), system, cats, phash, todo, a.out, a.model, refine=True, workers=2)


def cmd_batch_submit(a, system, cats, phash, cover):
    shops = read_shops(a.input)
    have = read_labels(a.out, phash)
    todo = [s for s in shops if s["id"] not in have]
    cl = a._client or client()
    ids = []
    for part_i, part in enumerate(chunks(chunks(todo, CHUNK), a.per_file)):   # 파일 크기 한도 대비 분할
        path = f"batch_{phash}_{part_i}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for gi, g in enumerate(part):
                f.write(json.dumps({"custom_id": f"{part_i}-{gi}", "method": "POST", "url": "/v1/chat/completions",
                                    "body": body(system, cats, g, a.model)}, ensure_ascii=False) + "\n")
        fid = cl.files.create(file=open(path, "rb"), purpose="batch").id
        b = cl.batches.create(input_file_id=fid, endpoint="/v1/chat/completions", completion_window="24h")
        ids.append(b.id)
        print(f"배치 제출: {b.id} ({len(part)}개 요청)")
    json.dump({"batches": ids, "phash": phash, "model": a.model}, open(STATE, "w"))


def cmd_batch_collect(a, system, cats, phash, cover):
    st = json.load(open(STATE))
    cl = a._client or client()
    pending = []
    for bid in st["batches"]:
        b = cl.batches.retrieve(bid)
        print(f"{bid}: {b.status}")
        if b.status != "completed":
            pending.append(bid); continue
        recs = []
        for line in cl.files.content(b.output_file_id).text.splitlines():
            d = json.loads(line)
            try:
                res = json.loads(d["response"]["body"]["choices"][0]["message"]["content"])["results"]
            except Exception:
                continue
            recs += [{"id": x["id"], "cat": x["cat"], "conf": x["conf"], "stage": 1,
                      "phash": st["phash"], "model": st["model"]} for x in res]
        append_labels(a.out, recs)
        print(f"  {len(recs)}개 저장")
    st["batches"] = pending
    json.dump(st, open(STATE, "w"))
    if pending:
        print("아직 안 끝난 배치가 있어요. 나중에 다시 실행하세요.")
    else:
        print("완료. 빠진 id 는 `run` 으로 다시 돌리면 채워져요.")


def cmd_eval(a, system, cats, phash, cover):
    gold = {r["id"]: r[a.gold_col] for r in read_shops(a.gold)}
    pred = read_labels(a.pred, None if a.any_prompt else phash)
    ids = [i for i in gold if i in pred]
    if not ids:
        sys.exit("겹치는 id 가 없어요. 이 프롬프트로 run 을 먼저 돌렸는지 확인하세요 (--any-prompt 로 무시 가능).")
    y, p = [gold[i] for i in ids], [pred[i]["cat"] for i in ids]
    acc = sum(g == q for g, q in zip(y, p)) / len(ids)
    labels = sorted(set(y) | set(p))
    f1s = {}
    for c in labels:
        tp = sum(g == c and q == c for g, q in zip(y, p)); fp = sum(g != c and q == c for g, q in zip(y, p))
        fn = sum(g == c and q != c for g, q in zip(y, p))
        f1s[c] = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0
    present = [c for c in labels if c in set(y)]
    print(f"프롬프트 {phash} | 평가 {len(ids)}/{len(gold)}개 | 정확도 {acc:.3f} | macro-F1 {sum(f1s[c] for c in present) / len(present):.3f}")
    conf = Counter(pred[i]["conf"] for i in ids)
    hi = [i for i in ids if pred[i]["conf"] == "high"]
    if hi:
        print(f"conf=high {len(hi)}개 정확도 {sum(gold[i] == pred[i]['cat'] for i in hi) / len(hi):.3f} | conf 분포 {dict(conf)}")
    print("카테고리별 F1 (정답셋에 있는 것):")
    for c in sorted(present, key=lambda c: f1s[c]):
        print(f"  {c:15s} n={y.count(c):3d}  F1={f1s[c]:.2f}")
    mis = Counter((g, q) for g, q in zip(y, p) if g != q)
    if mis:
        print("자주 틀리는 쌍 (정답 → 예측):")
        for (g, q), n in mis.most_common(8):
            print(f"  {g} → {q}: {n}")
    if a.show_errors:
        names = {r["id"]: r for r in read_shops(a.gold)}
        for i in ids:
            if gold[i] != pred[i]["cat"]:
                print(f"  ✗ {names[i]['name']} | {names[i]['tags'][:40]} | 정답 {gold[i]} / 예측 {pred[i]['cat']} ({pred[i]['conf']})")


def main(argv=None, _client=None, _search=None):
    global EFFORT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["estimate", "run", "refine", "batch-submit", "batch-collect", "eval"])
    ap.add_argument("--input"); ap.add_argument("--out", default="labels.jsonl")
    ap.add_argument("--prompt", default="prompt.txt"); ap.add_argument("--fewshot", default="fewshot.jsonl")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default=EFFORT, choices=["minimal", "low", "medium", "high"], help="추론 강도")
    ap.add_argument("--refine", action="store_true", help="run 뒤에 2차(블로그 검색) 까지")
    ap.add_argument("--limit", type=int, default=0, help="2차 대상 최대 개수 (검색 한도 관리용)")
    ap.add_argument("--refine-ratio", type=float, default=0.25, help="estimate: 2차로 갈 비율 가정")
    ap.add_argument("--per-file", type=int, default=2000, help="batch: 파일 하나당 요청 수")
    ap.add_argument("--gold"); ap.add_argument("--pred", default="labels.jsonl")
    ap.add_argument("--gold-col", default="cat"); ap.add_argument("--any-prompt", action="store_true")
    ap.add_argument("--show-errors", action="store_true")
    a = ap.parse_args(argv)
    a._client, a._search = _client, _search
    EFFORT = a.effort
    system, cats, phash, cover = load_prompt(a.prompt, a.fewshot)
    {"estimate": cmd_estimate, "run": cmd_run, "refine": cmd_refine, "batch-submit": cmd_batch_submit,
     "batch-collect": cmd_batch_collect, "eval": cmd_eval}[a.cmd](a, system, cats, phash, cover)


if __name__ == "__main__":
    main()
