"""Recount Phase 3 matched comparisons and Phase 4 results from request rows."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent.parent / "inference-bench"
SLO = {"chat":(1.5,4.),"coding":(2.5,8.),"rag":(3.,5.),"agent":(1.5,4.5)}
ARMS = ("A1","B1","B2","A2")


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def recount(directory):
    plan = load(directory/"schedule.json")
    verification = load(directory/"verification.json")
    if not verification["integrity_pass"]:
        raise ValueError("Comparison run did not pass its original integrity gate.")
    raw = defaultdict(list)
    for text in (directory/"requests.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(text)
        raw[row["schedule_id"]].append(row)
    designs = [plan[a] for a in ARMS]
    assert all(data==designs[0] for data in designs)
    summaries = []
    for stage in ARMS:
        window = load(directory/"runs"/f"{stage}-window.json")
        assert window["complete"] and abs(window["wall_seconds"]-window["duration"])<=3
        assert load(directory/"runs"/stage/"shutdown.json")["exited"]
        for i in range(3):
            families = defaultdict(list)
            for j,event in enumerate(plan[stage]):
                if event["window"]!=i:
                    continue
                chain = sorted(raw[f"{stage}-{j}"],key=lambda x:x["step"])
                assert chain and len({x["step"] for x in chain})==len(chain)
                assert sum(x["transaction_end"] for x in chain)==1
                assert chain[-1]["transaction_end"]
                errors = [x.get("error_type","stream") for x in chain if not x["ok"]]
                streamed = [x for x in chain if x["ok"]]
                for step in streamed:
                    assert step["arrival"] <= step["send"] <= step["first"] <= step["end"]
                    assert step["output_tokens"]==step["timings"]["predicted_n"]
                    assert step["prompt_tokens"]==step["timings"]["prompt_n"]+step["cached"]
                token_counts = tuple(sum(x[k] for x in streamed) for k in ("output_tokens","prompt_tokens","cached"))
                if errors:
                    data = (False,False,None,None,*token_counts,errors,None,False,False)
                else:
                    complete = len(chain)==len(event["items"])
                    nonempty = complete and all(x["quality_pass"] for x in chain)
                    ttft = chain[0]["first"]-chain[0]["arrival"] if complete else None
                    elapsed = chain[-1]["end"]-chain[0]["arrival"] if complete else None
                    a,b = SLO[event["family"]]
                    gate = nonempty and all(x["first"]-x["step_ready"]<=a and x["end"]-x["step_ready"]<=b for x in chain)
                    assert all(x["on_time"] for x in chain)==gate
                    normal_stop = all(x["finish"]=="stop" for x in chain)
                    data = (nonempty,gate,ttft,elapsed,*token_counts,[],
                            max(x["send"]-x["step_ready"] for x in chain),nonempty and normal_stop,gate and normal_stop)
                families[event["family"]].append(data)
            groups = {"all":[x for examples in families.values() for x in examples],**families}
            duration = window["duration"]/3
            for family,batch in groups.items():
                good = sum(x[1] for x in batch)
                def pct(arr, p):
                    return sorted(arr)[math.ceil(p * len(arr)) - 1] if len(arr) >= (40 if p == .95 else 1) else None

                prompts = sum(x[5] for x in batch)
                summaries.append({"stage":stage,"window":i+1,"family":family,"offered":len(batch),
                      "valid":sum(x[0] for x in batch),"on_time":good,"share":good/len(batch),"goodput_rps":good/duration,
                      "output_tps":sum(x[4] for x in batch)/duration,
                      "cache_share":sum(x[6] for x in batch)/prompts if prompts else None,
                      "ttft_p50":pct([x[2] for x in batch if x[2] is not None],.5),
                      "ttft_p95":pct([x[2] for x in batch if x[2] is not None],.95),
                      "e2e_p95":pct([x[3] for x in batch if x[3] is not None],.95),
                      "dispatch_p95":pct([x[8] for x in batch if x[8] is not None],.95),
                      "errors":dict(Counter(k for x in batch for k in x[7])),
                      "valid_stop_only":sum(x[9] for x in batch),"on_time_stop_only":sum(x[10] for x in batch)})
    return summaries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replication",type=Path)
    args = parser.parse_args()
    directory = args.replication or SOURCE/"phase3/results/endurance-segmented"
    rows = recount(directory)
    if not args.replication:
        sleep = load(SOURCE/"phase3/results/endurance-02/runs/A2-window.json")
        assert sleep["wall_seconds"]>sleep["duration"]+3
        prior = list(csv.DictReader((directory/"summary.csv").open(encoding="utf-8-sig")))
        prior_index = {(x["stage"],int(x["window"]),x["family"]):x for x in prior}
        for row in rows:
            old = prior_index[row["stage"],row["window"],row["family"]]
            assert all(int(old[k])==row[k] for k in ("offered","valid","on_time"))
            assert all(math.isclose(float(old[k]),row[k]) for k in ("goodput_rps","output_tps"))
            for observed, prior_key in (("ttft_p50","ttft_p50"),("ttft_p95","ttft_p95"),("e2e_p95","e2e_p95")):
                if row[observed] is not None:
                    assert abs(float(old[prior_key])-row[observed]) <= .000051
    name = "replication-recount.json" if args.replication else "phase3-recount.json"
    (HERE/name).write_text(json.dumps(rows,indent=2)+"\n",encoding="utf-8")
    print(f"{len(rows)} verified strata; {name}")


if __name__=="__main__":
    main()

