# Video-like $100 — books vs the ad

## What the video does
Gold (XAU), many same-size stacked legs, lot size up as equity grows, hold through huge floating DD, balance rockets in a short clip.

## What the books say
| Book | Verdict on that style |
|------|------------------------|
| **Brown** | Same-dir **DCA/grid** = **highest ruin risk** — do not default |
| **Fuller** | Only add to **winners**; aggregate risk ≤ **1R**. Adding without trail = “stupid pyramid” |
| **Windsor** | Escalate after losses — ruin unless capped |
| **Thomas** | Compound winners — hypothetical 10R tables ≠ live costs |
| **Ponsi / Silvani / Elder** | No holy grail; spread + leverage marketing ≠ edge |

**Conclusion:** The library does **not** contain a safe recipe to “do exactly the video.” Closest book path = Fuller pyramid + Thomas compound (still high risk).

## What we ran (`config_video_like_100.yaml`)
- Symbol **GC=F** (gold proxy), 15m, $100 start  
- Fuller pyramid + Thomas growth (unsafe cage open)

| Metric | Result |
|--------|--------|
| Trades | 60 |
| WR | 18% |
| Final | **$2.46** (from $100) |
| Best any **5h** pocket | **+$14.73** |
| Typical 5h | **about $0 or negative** (~−$1 to −$3) |

## 5-hour answer (honest)
With $100, book-backed closest-to-video: **expect ~$0 in 5 hours** (lucky window maybe **tens of dollars**, not thousands). The video’s multi-thousand jump is **not** reproduced on measured data.
