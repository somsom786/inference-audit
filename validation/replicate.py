"""Phase 4 research runner. All writes go to the product validation directory."""
import argparse
import copy
from importlib import import_module
import msvcrt
from pathlib import Path
import random
import signal
import sys

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent.parent / "inference-bench"
sys.dont_write_bytecode = True
sys.path.insert(0, str(RESEARCH / "phase3/scripts"))
source = import_module("endurance")
analysis = import_module("report")

SEED = 430407
RATES = (0.8, 1.0, 1.15)
# No carry-over from Phase 3; use the established safety watchdog and SSE transport.
source.PHASE = HERE
source.bench.PORT = 18084

def fixtures(count):
    rng = random.Random(SEED)
    family_mix = ["chat"] * 8 + ["coding"] * 5 + ["rag"] * 5 + ["agent"] * 2
    items, events = {}, []
    for window, rate in enumerate(RATES):
        mix = []
        while len(mix) < round(count * rate):
            block = family_mix[:]
            rng.shuffle(block)
            mix += block
        for j, family in enumerate(mix[:round(count * rate)]):
            token = f"R{rng.getrandbits(44):011X}"
            key = f"{family}-{window}-{j}" if family != "agent" else f"agent-plan-{window}-{j}"
            cap = 32
            checks = [token]
            start = f"Case {token}. "
            topic = rng.choice(["incident response", "inventory", "release planning", "tenant migration", "warehouse intake"])
            if family == "chat":
                prompt = start + f"Write a practical {rng.randint(97, 153)}-word note about {topic}. Include the case ID {token}, and describe a check and a rollback action."
                cap = rng.choice([176, 192, 224])
            elif family == "coding":
                utilities = [f"normalize_{j}_{i}" for i in range(2)]
                assertions = [[fn, val, val.strip().casefold()] for fn in utilities for val in (" Pear ", " CHERRY ", "17-AB ")]
                context = "\n".join(f"Route {rng.randrange(10**6)} prepares a {topic} report and records a checksum." for _ in range(rng.randrange(24, 62)))
                prompt = start + context + "\nReturn only Python defining test_normalizers with exactly these assertions, each on its own line. The functions already exist.\n" + "\n".join(f"assert {fn}({arg!r}) == {value!r}" for fn,arg,value in assertions)
                cap, checks = 240, []
            elif family == "rag":
                lines = [f"ID {rng.randrange(10**7):07d} hosts {rng.choice(['east depot','west relay','north plant','south office'])}; reviewed {rng.randrange(20,999)} {topic} items." for _ in range(rng.randrange(64, 140))]
                lines.insert(rng.randrange(len(lines)), f"The verified ticket for the current case is {token}.")
                prompt = f"Document {window}-{j}.\n" + "\n".join(lines) + "\nReturn only the verified ticket for the current case."
            else:
                prompt = start + f"For {topic}, choose lookup_status when the evidence is incomplete. This event's evidence is incomplete. Return only lookup_status."
                checks = ["lookup_status"]
            fixture = source.bench.fixture(key, family, source.bench.messages(prompt), cap, True, checks)
            if family == "coding":
                fixture["required_assertions"] = assertions
            items[key] = fixture
            chain = [key]
            if family == "agent":
                follow = f"agent-receipt-{window}-{j}"
                items[follow] = source.bench.fixture(follow, family, [
                    {"role":"user", "content":prompt},
                    {"role":"assistant", "content":"lookup_status"},
                    {"role":"user", "content":f"The verified tool result is {token}. Return the receipt only."},
                ], 32, True, [token])
                chain.append(follow)
            events.append({"at": window*count+(j+rng.uniform(.12,.80))/rate, "window":window,
                           "family":family, "items":chain})
    return items, events

class Replication(source.Study):
    pilot = True
    def prepare_fixtures(self, stage, folder):
        if (self.base/"fixtures.json").exists():
            return
        for item in self.fixtures.values():
            item["tokens"] = source.bench.count(item["messages"])
            if item["tokens"] + item["cap"] > 3800:
                raise RuntimeError(f"Context budget breached by {item['id']}")
        source.atomic(self.base/"fixtures.json", self.fixtures)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("id")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if not args.id.replace("-", "").isalnum():
        parser.error("Use a simple run ID.")
    seconds = 20 if args.smoke else 300
    arms = (("A1","prod"),("B1","four"),("B2","four"),("A2","prod"))
    if args.smoke:
        arms = arms[:1]
    windows = [[name,case,[seconds]*3,list(RATES)] for name,case in arms]
    base = HERE/"runs"/args.id
    base.mkdir(parents=True)
    with (RESEARCH/"phase2/data/gpu.lock").open("r+b") as lock:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        if source.sha(source.bench.MODEL)!=source.MODEL_HASH:
            raise RuntimeError("Model hash mismatch")
        items, arrivals = fixtures(seconds)
        schedule = {arm:copy.deepcopy(arrivals) for arm,_ in arms}
        source.atomic(base/"environment.json", {
            "utc":source.utc(), "dry":args.smoke, "seed":SEED, "model_sha256":source.MODEL_HASH,
            "engine_sha256":source.sha(source.bench.ENGINE), "engine_version":source.command([str(source.bench.ENGINE),"--version"]),
        })
        source.atomic(base/"schedule.json", schedule)
        source.atomic(base/"plan.json", {**source.PLAN, "dry_windows":windows,"windows":windows})
        study = Replication(base,args.smoke,windows,schedule,items)
        signal.signal(signal.SIGINT, lambda *_:study.fail("Console interrupt"))
        study.progress("starting")
        study.execute()
        return 0 if analysis.generate(base) else 1

if __name__ == "__main__":
    raise SystemExit(main())

